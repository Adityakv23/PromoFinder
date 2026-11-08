"""Compare tool output with hand-picked gold promos. usage: python evaluate.py outputs/promos.json eval/gold_picks.json"""
import json, sys
def iou(a, b):
    i = max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return i / ((a["end"] - a["start"]) + (b["end"] - b["start"]) - i)
promos = json.load(open(sys.argv[1])); gold = json.load(open(sys.argv[2]))
def report(name, sel):
    g = [x for x in gold if sel(x["ep"])]; p = [x for x in promos if sel(x["ep"])]
    hit = lambda a, bs, t: any(a["ep"] == b["ep"] and iou(a, b) >= t for b in bs)
    for tier in "AB":
        gt = [x for x in g if x["tier"] == tier]
        print(f"{name:10s} recall tier {tier}: {sum(hit(x, p, .4) for x in gt)}/{len(gt)}")
    print(f"{name:10s} precision (tool pick matches any gold, IoU>=.4): {sum(hit(x, g, .4) for x in p)}/{len(p)}")
    print(f"{name:10s} loose overlap (IoU>=.15): {sum(hit(x, g, .15) for x in p)}/{len(p)}")
for n in (15, 25, 40):
    top = [x for x in promos if x["rank"] <= n]
    print(f"top-{n}: {sum(any(x['ep']==b['ep'] and iou(x,b)>=.15 for b in gold) for x in top)}/{n} overlap a gold promo; "
          f"{sum(any(x['ep']==b['ep'] and iou(x,b)>=.15 for b in gold if b['tier']=='A') for x in top)} overlap a tier-A")
report("eps 1-25", lambda e: e <= 25); report("eps 26-50", lambda e: e > 25); report("all", lambda e: True)
print("\ntool picks with NO overlap with any gold promo (IoU<.15):")
for x in promos:
    if not any(x["ep"] == b["ep"] and iou(x, b) >= .15 for b in gold):
        print(f'  #{x["rank"]} ep{x["ep"]} {x["start"]:.1f}-{x["end"]:.1f}  {x["hook"][:70]}')
