"""Builds outputs/curated_promos.{md,csv}: the hand-reviewed final list (gold_picks.json) with hook/cliffhanger lines
pulled from the screenplay by the tool's own parser. usage: python eval/make_curated.py PACK_DIR"""
import csv, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import promo_finder as pf
eps = {e["ep"]: e for e in pf.load_pack(sys.argv[1])}
gold = json.load(open(os.path.join(os.path.dirname(__file__), "gold_picks.json")))
order = [3, 15, 12, 26, 23, 41, 34, 47, 39, 45, 36, 27, 43, 42, 28]   # tier-A posting order (early/low-spoiler first)
a = sorted([g for g in gold if g["tier"] == "A"], key=lambda g: order.index(g["ep"]))
rest = sorted([g for g in gold if g["tier"] != "A"], key=lambda g: (g["tier"], g["ep"], g["start"]))
rows = []
for i, g in enumerate(a + rest, 1):
    win = [e for e in eps[g["ep"]]["events"] if g["start"] - .01 <= e["start"] <= g["end"] + .01]
    d = pf.describe(dict(events=win)); rows.append(dict(rank=i, tier=g["tier"], **{k: g[k] for k in ("ep", "start", "end", "why")}, **d))
os.makedirs("outputs", exist_ok=True)
with open("outputs/curated_promos.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["rank", "tier", "episode", "start", "end", "length_s", "hook", "cliffhanger", "why"])
    for r in rows: w.writerow([r["rank"], r["tier"], r["ep"], pf.mmss(r["start"]), pf.mmss(r["end"]), round(r["end"] - r["start"], 1), r["hook"], r["cliffhanger"], r["why"]])
with open("outputs/curated_promos.md", "w", encoding="utf-8") as f:
    f.write("# Curated promos (tool candidates, reviewed by reading all 50 scripts)\nTier A = post first; B = good; C = filler/backup.\n\n")
    for r in rows:
        f.write(f"**#{r['rank']} [{r['tier']}] Ep {r['ep']}  {pf.mmss(r['start'])} - {pf.mmss(r['end'])}** ({r['end']-r['start']:.0f}s)  \n"
                f"Hook: {r['hook']}  \nCliffhanger: {r['cliffhanger']}  \nWhy: {r['why']}\n\n")
print(len(rows), "curated promos written")
