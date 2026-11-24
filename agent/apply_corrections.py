"""Human-in-the-loop step: apply reviewed corrections to pass 1 -> pass 2 (final)."""
import csv, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.DictReader(open(f"{ROOT}/data/pass1_seed.csv"), delimiter="|"))
by_id = {r["id"]: r for r in rows}
for c in csv.DictReader(open(f"{ROOT}/data/corrections.csv"), delimiter="|"):
    assert c["field"] in by_id[c["id"]], c  # a typo in a field name must not silently add a column
    by_id[c["id"]][c["field"]] = c["new"]
with open(f"{ROOT}/data/pass2_final.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter="|")
    w.writeheader(); w.writerows(rows)
print("wrote pass2_final.csv")
