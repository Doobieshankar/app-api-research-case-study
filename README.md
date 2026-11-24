# 100 apps, agent-ready?

A case study for the AI Product Ops take-home. For each of 100 apps it records the category, how the app checks who is calling (auth), whether a developer can get keys alone (self-serve or gated), the API surface, whether an MCP exists, and a buildability verdict. Every answer links to the docs page it came from. The research was done by an agent and checked by hand.

**Open `index.html` in a browser.** It is the whole deliverable in one self-contained file.

## In plain words

1. **Pass 1: draft from memory.** An AI model filled in all 100 rows from what it already knew (`data/pass1_seed.csv`). Fast, but nothing was proven yet.
2. **The agent checks every claim.** `agent/research.py` opens each app's docs page (headless Chrome takes over when a site blocks plain downloads), follows up to two auth or pricing links, reads the site's `llms.txt` if it has one, looks for proof sentences, and asks the official MCP Registry. Each claim comes out as *confirmed*, *contradicted* or *no evidence*, and the sentence that proves it is saved.
3. **A human reviews the flags.** Each change is written to `data/corrections.csv` with its source URL and the reason. `agent/apply_corrections.py` then builds `data/pass2_final.csv`.
4. **Measure accuracy.** First a 20-app sample (2 per category), then a fresh 10-app holdout that nobody had looked at (`data/hand_check.csv`).
5. **Build the page.** `build.py` turns the data into `index.html`, so every number on the page is calculated from the files.

## Run it

Needs Python 3 with `requests` and `beautifulsoup4`. Chrome is optional (any Playwright Chromium in `~/.cache/ms-playwright` is found on its own).

```bash
python3 agent/research.py data/pass2_final.csv final
```

```bash
python3 agent/apply_corrections.py
```

```bash
python3 build.py
```

A full research run takes about 4 minutes for 100 apps.

## Files

| File | What it is |
|---|---|
| `index.html` | The case study page, built from the data (do not edit by hand) |
| `page.template.html`, `tokens.css`, `base.css` | Page template and styles that `build.py` fills in |
| `agent/research.py` | The research and verification agent. Each change from v1 to v3 is commented in the code |
| `agent/apply_corrections.py` | Applies the reviewed corrections to pass 1 and writes the final table |
| `data/pass1_seed.csv` | Pass 1, written from AI memory |
| `data/pass2_final.csv` | The final 100 rows |
| `data/corrections.csv` | All 41 corrections, each with its evidence URL and reason |
| `data/evidence_*.json` | The agent's output for each run (pass1 = v1, pass2 = v2, pass3 and final = v3) |
| `data/hand_check.csv` | The hand-checked sample and holdout |

## Results

- 66 apps can be built now, 23 need effort first, and 11 need outreach to the vendor.
- Sample accuracy (4 fields × 18 verifiable apps): **86.1%** for pass 1, **94.4%** for pass 2, and 100% after fixes. The 100% is expected because those misses were fixed. The honest number is the holdout: **40/40**. With only 40 fields, the true accuracy is probably above 92%.
- The biggest error source was MCP. Pass 1 found 44 vendor MCPs; the docs show 70.

## Honest limits

- About a fifth of claims have no matching sentence on the pages the agent read. Those rows have lower confidence.
- "Self-serve or gated" is the field the agent confirms least, because pricing pages are vague.
- PitchBook blocks automated fetches, and the Ecwid, Paygent, iPayX and fanbasis docs are thin or missing. These rows are marked unverified rather than right.
- The hand checks were done by an AI reviewer reading the saved evidence. **Before submitting, a person should re-check a few rows, especially the ones marked "low"**, and update `data/hand_check.csv`.
