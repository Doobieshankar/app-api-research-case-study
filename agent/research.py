"""Research agent: checks every claim in a research CSV against the live docs.

Loop per app:
  1. fetch the docs page (plain HTTP)          -> if blocked/empty, 2. render it in headless Chromium
  3. follow up to 2 in-site links about auth/pricing/getting-started
  4. regex the text for auth, API-style, MCP and gating signals (keeps a snippet as proof)
  5. ask the official MCP Registry whether a server exists for the app
  6. compare every claim in the input CSV -> confirmed / contradicted / no-evidence
Output: data/evidence_<label>.json   (run: python3 agent/research.py data/pass1_seed.csv pass1)
"""
import csv, json, re, subprocess, sys, glob, os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}  # v2: bot-looking UA got blocked
CHROME = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")) or ["chromium"])[-1]

AUTH = {  # signal group -> regex
    "oauth2": r"oauth\s?2|oauth 2\.0|authorization[_ ]code|client[_ ]credentials|\boauth\b",
    "oauth1": r"oauth\s?1(\.0a?)?\b",
    "key": r"api[\s_-]?keys?\b|x-api-key|application key|developer token|secret key|api password",
    "token": r"api[\s_-]?tokens?|access[\s_-]?tokens?|bearer|personal access token|private app|bot token|auth token|integration token",
    "basic": r"basic auth|http basic|basic authentication|authorization: basic",
    "jwt": r"\bjwt\b|json web token|key[- ]pair",
    "hmac": r"\bhmac\b|signed request|signature",
    "webhook": r"webhooks?",
}
LABEL_GROUP = {  # seed label -> which signal groups count as evidence
    "OAuth2": ["oauth2"], "OAuth1": ["oauth1"], "JWT": ["jwt"], "Basic": ["basic"],
    "HMAC signature": ["hmac"], "Webhook": ["webhook"], "None": [],
}
KEY_TOKEN = ["key", "token"]  # every other label (API key, PAT, Bot token...) is a key/token family
API = {"REST": r"\brest\b|restful|https?://[a-z0-9.-]+/(api|v\d)", "GraphQL": r"graphql", "MCP": r"\bmcp\b|model context protocol",
       "CLI": r"\bnpm install|pip install|\bcli\b", "WebSocket": r"websocket", "gRPC": r"\bgrpc\b", "SOAP": r"\bsoap\b", "Webhook": r"webhook"}
# v2: dropped bare "approval"/"apply for"/"waitlist" - they matched nav menus and OAuth scope text (false gates)
GATED = r"contact (our )?sales to|talk to (our )?sales|request api access|enterprise (plan|customers) only|available on (the )?enterprise|app review|business verification|must be an? (existing )?customer|developer token"
SELF = r"free (plan|tier|trial|account|developer|sandbox)|sign up (for )?free|\bsandbox\b|developer edition|test mode|no credit card|free credits|trial"
FOLLOW = re.compile(r"auth|oauth|api[-_]?key|token|getting[-_]started|quickstart|pricing|access", re.I)


def fetch(url):
    """HTTP first; headless browser when the page is blocked or rendered by JS."""
    best = ""
    for _ in range(2):  # v2: one retry; v1 lost Xero/QuickBooks to transient timeouts
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.ok:
                best = r.text
                if len(BeautifulSoup(r.text, "html.parser").get_text()) > 1500:
                    return r.text, "http"
            break
        except requests.RequestException:
            pass
    try:
        out = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--timeout=15000",
                              f"--user-agent={UA['User-Agent']}", "--dump-dom", url],
                             capture_output=True, text=True, timeout=45)
        if len(out.stdout) > 500:
            return out.stdout, "browser"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return (best, "http-thin") if best else ("", "failed")  # v2: keep thin HTTP text instead of throwing it away


def snippet(text, rx):
    m = re.search(rx, text, re.I)
    if not m:
        return None
    s = max(0, m.start() - 90)
    return " ".join(text[s:m.end() + 90].split())


def mcp_registry(app):
    q = re.sub(r"\(.*?\)|\.com|\.io", "", app).strip().split()[0].lower()
    try:
        r = requests.get("https://registry.modelcontextprotocol.io/v0/servers", params={"search": q, "limit": 30}, timeout=15)
        names = [s["server"]["name"] for s in r.json().get("servers", [])]
    except Exception:
        return {"query": q, "hits": [], "vendor_hit": None}
    # vendor-published = the namespace (before "/") carries the vendor's name, e.g. com.stripe/mcp or io.github.stripe/...
    # v2: exact reverse-DNS match only. v1 used substring and matched "copperline-labs" for Copper, "princezoho" for Zoho
    def is_vendor(ns):
        p = ns.lower().split(".")
        return (len(p) >= 2 and p[1] == q and p[0] != "app") or (p[:2] == ["io", "github"] and len(p) > 2 and (p[2] == q or p[2].startswith(q + "-")))
    vendor = [n for n in names if is_vendor(n.split("/")[0])]
    return {"query": q, "hits": names[:8], "vendor_hit": vendor[0] if vendor else None}


def research(row):
    url = row["docs"]
    html, how = fetch(url)
    soup = BeautifulSoup(html, "html.parser")
    pages = [{"url": url, "via": how}]
    text = soup.get_text(" ")
    host = urlparse(url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        u = urljoin(url, a["href"]).split("#")[0]
        if urlparse(u).netloc == host and u != url and FOLLOW.search(u) and u not in links:
            links.append(u)
    llms = f"{urlparse(url).scheme}://{host}/llms.txt"  # v2: machine-readable docs index many docs sites now publish
    try:
        r = requests.get(llms, headers=UA, timeout=15)
        if r.ok and "html" not in r.headers.get("content-type", ""):
            text += " " + r.text[:200000]
            pages.append({"url": llms, "via": "llms.txt"})
    except requests.RequestException:
        pass
    for u in links[:2]:
        h, w = fetch(u)
        text += " " + BeautifulSoup(h, "html.parser").get_text(" ")
        pages.append({"url": u, "via": w})

    # v3: Mintlify docs boilerplate ("search this documentation through its MCP server") is a docs MCP, not a product MCP
    text = re.sub(r"Agents\s+can\s+also\s+search\s+and\s+read\s+this\s+documentation\s+through\s+its\s+MCP\s+server", " ", text)
    sig = {g: snippet(text, rx) for g, rx in AUTH.items()}
    api = {k: snippet(text, rx) for k, rx in API.items()}
    gated, selfserve = snippet(text, GATED), snippet(text, SELF)
    reg = mcp_registry(row["app"])

    checks = {}
    for label in filter(None, row["auth"].split(";")):
        groups = LABEL_GROUP.get(label, KEY_TOKEN)
        hit = next((sig[g] for g in groups if sig.get(g)), None)
        checks[f"auth:{label}"] = ("confirmed", hit) if hit or label == "None" else ("no-evidence", None)
    for label in filter(None, row["api"].split(";")):
        checks[f"api:{label}"] = ("confirmed", api[label]) if api.get(label) else ("no-evidence", None)
    acc = row["access"]
    if acc in ("free", "trial"):
        checks["access"] = ("confirmed", selfserve) if selfserve else (("contradicted", gated) if gated else ("no-evidence", None))
    elif acc in ("sales", "approval", "paid"):
        checks["access"] = ("confirmed", gated) if gated else ("no-evidence", None)
    else:
        checks["access"] = ("confirmed", "local tool, no credentials")
    m = row["mcp"]
    if m == "official":
        checks["mcp"] = ("confirmed", reg["vendor_hit"]) if reg["vendor_hit"] else (("confirmed", api["MCP"]) if api["MCP"] else ("no-evidence", None))
    elif m == "none" and reg["vendor_hit"]:
        checks["mcp"] = ("contradicted", f"registry lists {reg['vendor_hit']}")
    elif m == "community" and (api["MCP"] or reg["vendor_hit"]):
        # v3: the hand-check showed "community" claims hid vendor MCPs (Front, Meta Ads, Smartsheet) -> make a human look
        checks["mcp"] = ("contradicted", reg["vendor_hit"] or api["MCP"])
    else:
        checks["mcp"] = ("confirmed" if m != "none" or not api["MCP"] else "contradicted", api["MCP"] or "registry: no vendor server")
    # auth methods the page shows that the claim missed (only strong, specific signals)
    missed = [g for g in ("oauth2", "basic", "jwt", "oauth1") if sig[g] and not any(g in LABEL_GROUP.get(l, []) for l in row["auth"].split(";"))]

    return {"id": int(row["id"]), "app": row["app"], "pages": pages, "fetched": any(p["via"] != "failed" for p in pages),
            "chars": len(text), "checks": {k: {"status": s, "evidence": e} for k, (s, e) in checks.items()},
            "possibly_missed_auth": missed, "gated_cue": gated, "selfserve_cue": selfserve, "mcp_registry": reg}


def main(csv_path, label):
    rows = list(csv.DictReader(open(csv_path), delimiter="|"))
    with ThreadPoolExecutor(10) as ex:
        out = list(ex.map(research, rows))
    c = [v["status"] for r in out for v in r["checks"].values()]
    summary = {k: c.count(k) for k in ("confirmed", "no-evidence", "contradicted")}
    summary["fetch_failed"] = [r["app"] for r in out if not r["fetched"]]
    summary["needed_browser"] = [r["app"] for r in out if any(p["via"] == "browser" for p in r["pages"])]
    json.dump({"label": label, "summary": summary, "apps": out}, open(f"{ROOT}/data/evidence_{label}.json", "w"), indent=1)
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}))
    print("fetch failed:", summary["fetch_failed"])


if __name__ == "__main__":
    assert not re.search(GATED, "Some scopes require approval from Discord", re.I)
    assert re.search(AUTH["oauth2"], "Uses OAuth 2.0 authorization code", re.I) and not re.search(AUTH["basic"], "basically", re.I)
    main(sys.argv[1], sys.argv[2])
