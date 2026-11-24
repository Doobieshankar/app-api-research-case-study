"""Builds index.html (one self-contained file) from the data files. Run: python3 build.py"""
import csv, json, html, os, collections as C

ROOT = os.path.dirname(os.path.abspath(__file__))
rd = lambda p: list(csv.DictReader(open(f"{ROOT}/data/{p}"), delimiter="|"))
apps, p1, corr, hand = rd("pass2_final.csv"), {r["id"]: r for r in rd("pass1_seed.csv")}, rd("corrections.csv"), rd("hand_check.csv")
ev = {str(a["id"]): a for a in json.load(open(f"{ROOT}/data/evidence_final.json"))["apps"]}
runs = [(lbl, json.load(open(f"{ROOT}/data/evidence_{lbl}.json"))["summary"]) for lbl in ("pass1", "pass2", "pass3", "final")]
import re
e = lambda x: html.escape(re.sub(r'"([^"]*)"', r"“\1”", str(x).replace("...", "…")), quote=True).replace("&#x27;", "’")  # typographic quotes in prose

ACCESS = {"free": "Yes, free", "trial": "Yes, free trial", "paid": "Pay first", "approval": "Apply and wait", "sales": "Talk to sales", "none": "No keys needed"}
VERDICT = {"ready": "Build now", "friction": "Build with effort", "blocked": "Needs outreach"}
MCP = {"official": "Vendor MCP", "community": "Community only", "none": "None found"}

def fam(label):
    return label if label in ("OAuth2", "Basic", "None", "OAuth1", "JWT", "Webhook") else "Key/Token"

fams = {r["id"]: {fam(x) for x in r["auth"].split(";")} for r in apps}
n = len(apps)
verdicts = C.Counter(r["verdict"] for r in apps)
key_n = sum("Key/Token" in f for f in fams.values()); oauth_n = sum("OAuth2" in f for f in fams.values())
both_n = sum({"Key/Token", "OAuth2"} <= f for f in fams.values()); basic_n = sum("Basic" in f for f in fams.values())
two_cover = sum(bool(f & {"Key/Token", "OAuth2"}) for f in fams.values())
mcp_off = sum(r["mcp"] == "official" for r in apps)
mcp_p1 = sum(r["mcp"] == "official" for r in p1.values())
mcp_fix = sum(c["field"] == "mcp" for c in corr)
selfserve = sum(r["access"] in ("free", "trial", "none") for r in apps)
graphql = sum("GraphQL" in r["api"] for r in apps)

def blocker_type(r):
    return {"paid": "A paid plan first", "sales": "Must be a customer or talk to sales", "approval": "An app review or approval"}.get(r["access"], "A review, verification or real-money risk")
not_ready = [r for r in apps if r["verdict"] != "ready"]
btypes = C.Counter(blocker_type(r) for r in not_ready).most_common()
outreach = [r["app"] for r in apps if r["verdict"] == "blocked"]
apply_now = [r["app"] for r in apps if r["access"] == "approval" or (r["verdict"] == "friction" and r["access"] in ("free", "trial"))]

cats = list(dict.fromkeys(r["category"] for r in apps))
by_cat = {c: C.Counter(r["verdict"] for r in apps if r["category"] == c) for c in cats}
cat_rank = sorted(cats, key=lambda c: (-by_cat[c]["ready"], by_cat[c]["blocked"]))

# accuracy from the hand-check log
def acc(sample, col):
    rows = [h for h in hand if h["sample"] == sample and h["fields_checked"] != "-"]
    checked = sum(len(h["fields_checked"].split(";")) for h in rows)
    wrong = sum(len([x for x in h[col].split(";") if x]) for h in rows)
    return checked - wrong, checked, len(rows)
a1, a2, a3, b3 = acc("A", "pass1_wrong"), acc("A", "pass2_wrong"), acc("A", "final_wrong"), acc("B", "final_wrong")
pct = lambda t: f"{100 * t[0] / t[1]:.1f}%"
p1_misses = [h for h in hand if h["sample"] == "A" and h["pass1_wrong"]]
excluded = [h for h in hand if h["fields_checked"] == "-"]
assert a1[1] == a2[1] == a3[1] and a1[0] <= a2[0] <= a3[0], "accuracy must be measured on the same fields"

def run_row(lbl, s, agent, data):
    tot = s["confirmed"] + s["no-evidence"] + s["contradicted"]
    return (f"<tr><td>{e(agent)}</td><td>{e(data)}</td><td class='num'>{s['confirmed']}/{tot}</td><td class='num'>{100*s['confirmed']/tot:.1f}%</td>"
            f"<td class='num'>{s['contradicted']}</td><td class='num'>{len(s['fetch_failed'])}</td><td class='num'>{len(s['needed_browser'])}</td></tr>")
run_rows = "".join([run_row(*runs[0], "v1", "Pass 1 (memory only)"), run_row(*runs[1], "v2", "Pass 2 (after 1st review)"),
                    run_row(*runs[2], "v3", "Pass 2 + sample fixes"), run_row(*runs[3], "v3", "Final")])

def evidence_note(i):
    ch = ev[i]["checks"].values()
    ok = sum(c["status"] == "confirmed" for c in ch)
    return ok, len(ch)

rows = []
for r in apps:
    ok, tot = evidence_note(r["id"])
    conf = "high" if ok == tot else ("low" if ok <= tot / 2 else "medium")
    changed = [c["field"] for c in corr if c["id"] == r["id"]]
    rows.append(
        f"<tr data-cat='{e(r['category'])}' data-verdict='{r['verdict']}' data-text='{e((r['app'] + ' ' + r['what']).lower())}'>"
        f"<td class='num'>{r['id']}</td><th scope='row'>{e(r['app'])}<span class='what'>{e(r['what'])}</span></th>"
        f"<td>{e(r['category'])}</td><td>{e(r['auth'].replace(';', ', '))}</td><td>{ACCESS[r['access']]}</td>"
        f"<td>{e(r['api'].replace(';', ', '))} <span class='what'>{r['breadth']}</span></td><td>{MCP[r['mcp']]}</td>"
        f"<td><span class='v v-{r['verdict']}'>{VERDICT[r['verdict']]}</span></td><td>{e(r['blocker']) or '<span class=\"what\">None</span>'}</td>"
        f"<td><a href='{e(r['docs'])}' rel='noopener'>Docs</a><span class='what'>{ok} of {tot} claims seen on page, {conf}"
        f"{', fixed: ' + e(', '.join(sorted(set(changed)))) if changed else ''}</span></td></tr>")

bars = []
for c in cat_rank:
    b = by_cat[c]; t = sum(b.values())
    seg = "".join(f"<span class='seg seg-{k}' style='flex-grow:{b[k]}'>{b[k] if b[k] else ''}</span>" for k in ("ready", "friction", "blocked") if b[k])
    bars.append(f"<li><span class='bar-name'>{e(c)}</span><span class='bar' role='img' aria-label='{e(c)}: {b['ready']} build now, {b['friction']} with effort, {b['blocked']} need outreach, of {t}'>{seg}</span></li>")

miss_rows = "".join(
    f"<tr><td>{e(h['app'])}</td><td>{e(h['pass1_wrong'].replace(';', ', '))}</td><td>{'Still wrong' if h['pass2_wrong'] else 'Fixed'}</td><td>{e(h['note'])}</td></tr>"
    for h in p1_misses)
fix_rows = "".join(f"<tr><td>{e(next(a['app'] for a in apps if a['id']==c['id']))}</td><td>{e(c['field'])}</td><td>{e(c['new'] or '(cleared)')}</td><td>{e(c['why'])}</td></tr>" for c in corr)
blk_rows = "".join(f"<tr><td>{e(k)}</td><td class='num'>{v}</td></tr>" for k, v in btypes)
cat_opts = "".join(f"<option>{e(c)}</option>" for c in cats)

machine = {"generated": "2026-11-24", "fields": list(apps[0].keys()), "apps": apps,
           "accuracy": {"sample_A_pass1": a1[:2], "sample_A_pass2": a2[:2], "sample_A_final": a3[:2], "holdout_B_final": b3[:2]}}

css = open(f"{ROOT}/tokens.css").read() + open(f"{ROOT}/base.css").read()
page = open(f"{ROOT}/page.template.html").read()
for k, v in {
    "CSS_SCAFFOLD": css, "N": n, "READY": verdicts["ready"], "FRICTION": verdicts["friction"], "BLOCKED": verdicts["blocked"],
    "KEY_N": key_n, "OAUTH_N": oauth_n, "BOTH_N": both_n, "BASIC_N": basic_n, "TWO_COVER": two_cover, "MCP_OFF": mcp_off, "MCP_P1": mcp_p1,
    "MCP_FIX": mcp_fix, "CORR_N": len(corr), "CORR_APPS": len({c["id"] for c in corr}), "SELFSERVE": selfserve, "GRAPHQL": graphql,
    "TOP_BLOCKER": btypes[0][0].lower(), "TOP_BLOCKER_N": btypes[0][1], "NOT_READY": len(not_ready),
    "DEV_READY": by_cat["Developer & Infra"]["ready"], "PM_READY": by_cat["Productivity & PM"]["ready"],
    "FIN_BLOCKED": by_cat["Finance & Fintech"]["blocked"], "ADS_APPROVAL": sum(r["access"] == "approval" for r in apps if r["category"] == "Marketing & Ads"),
    "OUTREACH": e(", ".join(outreach)), "APPLY_NOW": e(", ".join(apply_now)),
    "A1": pct(a1), "A2": pct(a2), "A3": pct(a3), "B3": pct(b3), "A1N": f"{a1[0]}/{a1[1]}", "A2N": f"{a2[0]}/{a2[1]}", "A3N": f"{a3[0]}/{a3[1]}",
    "B3N": f"{b3[0]}/{b3[1]}", "A_APPS": a1[2], "B_APPS": b3[2], "EXCLUDED": e(", ".join(h["app"] for h in excluded)),
    "RUN_ROWS": run_rows, "BARS": "".join(bars), "ROWS": "".join(rows), "MISS_ROWS": miss_rows, "FIX_ROWS": fix_rows, "BLK_ROWS": blk_rows,
    "CAT_OPTS": cat_opts, "MACHINE": json.dumps(machine).replace("</", "<\\/"),
}.items():
    page = page.replace("{{" + k + "}}", str(v))
assert "{{" not in page, page[page.index("{{"):page.index("{{") + 40]
open(f"{ROOT}/index.html", "w").write(page)
print(f"index.html written: {n} apps, sample A {pct(a1)} -> {pct(a2)} -> {pct(a3)}, holdout {pct(b3)}")
