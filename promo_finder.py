#!/usr/bin/env python3
"""Find promo clips (20-60s, hook -> cliffhanger) in microdrama screenplays.

Stage 1 (free, offline, stdlib only): parse screenplays, generate every 20-60s window
that starts/ends on a line boundary, score it for hook / cliffhanger / conflict / length.
Stage 2 (optional, --llm): send the best few windows per episode to ANY OpenAI-compatible
chat model (Gemini free tier, Groq, OpenRouter, local Ollama...) to pick, rank and explain.

    python promo_finder.py PACK_DIR --out outputs                 # heuristics only
    LLM_API_KEY=... python promo_finder.py PACK_DIR --out outputs --llm   # + model re-rank
"""
import argparse, csv, glob, json, os, re, sys, urllib.request

MIN_LEN, MAX_LEN, IDEAL_LEN = 20.0, 60.0, 38.0

# ---------------------------------------------------------------- parsing
def _fix(s):  # the pack is double-encoded (UTF-8 read as cp1252)
    try: return s.encode("cp1252").decode("utf-8")
    except Exception: return s

def _secs(t):
    m, s = t.split(":"); return float(m) * 60 + float(s)

def parse_episode(path):
    raw = _fix(open(path, encoding="utf-8", errors="replace").read())
    num = int(re.search(r"episode-(\d+)", os.path.basename(path)).group(1))
    log = re.search(r"EPISODE LOGLINE:\s*(.*)", raw)
    ev = []
    for blk in re.split(r"\n(?=\*\*)", raw):
        m = re.match(r"\*\*(.+?):\*\*\s*\nStart: \(([\d:.]+)\) \| End: \(([\d:.]+)\)\s*\n(.*)", blk.strip(), re.S)
        if not m: continue
        who, a, b, txt = m.groups()
        who = who.strip(); txt = " ".join(txt.split()).replace("--- SCRIPT END ---", "").strip()
        if who == "CAMERA": continue                      # shot directions are noise for this task
        kind = "sfx" if who == "SOUND FX" else "action" if who == "ACTION" else "line"
        ev.append(dict(kind=kind, who=re.sub(r"\s*\(.*", "", who), start=_secs(a), end=_secs(b), text=txt))
    ev.sort(key=lambda e: e["start"])
    return dict(ep=num, logline=log.group(1) if log else "", events=ev, end=max(e["end"] for e in ev))

def load_pack(pack_dir):
    files = sorted(glob.glob(os.path.join(pack_dir, "**", "episode-*.txt"), recursive=True))
    if not files: sys.exit(f"no episode-*.txt files under {pack_dir}")
    return [parse_episode(f) for f in files]

# ---------------------------------------------------------------- scoring
HOOK_WORDS = ("slap|strike|struck|kill|dead|die|poison|arsenic|witch|hang|execut|gallows|secret|truth|lie|betray|"
              "divorce|pregnan|who are you|how dare|your grace|duke|impossible|explo|burst|gasp|blood|fire|"
              "arrest|disown|crawl|scream|shoot|gun|knife|blade|steal|stole|imposter|alive|wife|husband|baby|"
              "marry|wedding|ring|scar|prisoner|dungeon|thrown|drag")
CONFLICT_RE = re.compile(HOOK_WORDS, re.I)
VIOLENT_ACTION = re.compile(r"strik|slap|slam|burst|snatch|shov|drag|kick|explo|collaps|lung|grab|fling|hurl|"
                            r"smash|shatter|draw[s]? a|kneel|rip|punch|crash|kick", re.I)
CLIFF_SFX = re.compile(r"cliffhanger|sting|crescendo|swell|gasp|crash|bang|explo|slam|latch|creak|scream|toll|"
                       r"thud|boom|silence|cut to black|freez", re.I)
CALM = re.compile(r"\b(thank you|goodnight|rest now|safe now|peace|sleep|forgive)\b", re.I)
STRONG_END = re.compile(r"cliffhanger|ominous|sting|crescendo|dramatic|tension|thunder|unresolved|boom|slam|gasp|"
                        r"explo|bolt|door|creak|latch|toll", re.I)
SOFT_END = re.compile(r"warm|gentle|tender|triumphant|peace|fad(e|ing)|melanchol|serene|soft|lullaby|hearth", re.I)

def _words(t): return len(re.findall(r"\w+", t))

def hook_score(win):
    """Strength of what happens in the first 3 seconds."""
    t0 = win[0]["start"]
    first = [e for e in win if e["start"] - t0 < 3.0 and e["kind"] != "sfx"][:2]
    s, why = 0.0, []
    for e in first:
        txt = e["text"]
        if e["kind"] == "line":
            if "!" in txt: s += 1.5; why.append("shouted line")
            if "?" in txt: s += 1.0; why.append("opens on a question")
            if _words(txt) <= 9: s += 0.5
            if _words(txt) <= 2 and not re.search(r"[!?]", txt): s -= 1.5   # "Yes." "Please..."
            if txt.startswith(("And ", "But ", "Then ", "So ", "...")): s -= 1.0  # continuation: needs context
        elif VIOLENT_ACTION.search(txt): s += 2.0; why.append("physical action")
        s += min(2.0, 0.7 * len(CONFLICT_RE.findall(txt)))
    return s, why

def cliff_score(win, ep):
    """Does the clip stop on an unresolved beat?"""
    last = win[-1]; tail = [e for e in win if e["end"] >= last["end"] - 4.0]
    s, why = 0.0, []
    if last["end"] >= ep["end"] - 5.0:   # episode finale: only a cliffhanger if the closing beat sounds like one
        end_sfx = " ".join(e["text"] for e in ep["events"] if e["end"] >= ep["end"] - 6 and e["kind"] == "sfx")
        if STRONG_END.search(end_sfx) and not SOFT_END.search(end_sfx): s += 3.0; why.append("ends at the episode's own cliffhanger")
        elif SOFT_END.search(end_sfx): s -= 1.0; why.append("episode ends on a soft/resolved beat")
        else: s += 1.0
    for e in tail:
        if e["kind"] == "sfx" and CLIFF_SFX.search(e["text"]): s += 1.5; why.append("sound sting at the cut"); break
    lines = [e for e in tail if e["kind"] == "line"]
    if lines:
        txt = lines[-1]["text"]
        if "?" in txt: s += 1.5; why.append("last line is a question")
        elif txt.rstrip().endswith(("...", "—", "-")): s += 1.0; why.append("last line cut off")
        if CONFLICT_RE.search(txt): s += 0.8
    if any(CALM.search(e["text"]) for e in tail): s -= 1.5; why.append("ends calm/resolved")
    return s, why

def score_window(win, ep):
    dur = win[-1]["end"] - win[0]["start"]
    lines = [e for e in win if e["kind"] == "line"]
    h, hw = hook_score(win); c, cw = cliff_score(win, ep)
    conflict = min(3.0, 0.25 * sum(len(CONFLICT_RE.findall(e["text"])) for e in win))
    speakers = len({e["who"] for e in lines})
    standalone = (0.5 if speakers >= 2 else -1.0) + (0.5 if len(lines) >= 4 else -1.0)
    length = 1.5 * max(0.0, 1 - abs(dur - IDEAL_LEN) / 25)
    total = 1.0 * h + 1.4 * c + conflict + standalone + length
    return total, dict(hook=round(h, 2), cliff=round(c, 2), conflict=round(conflict, 2),
                       standalone=round(standalone, 2), length=round(length, 2)), hw, cw

# ---------------------------------------------------------------- candidates
def candidates(ep):
    ev = [e for e in ep["events"] if e["kind"] != "sfx" or e["start"] > 0]
    out = []
    for i, a in enumerate(ev):
        if a["kind"] == "sfx" or a["text"].startswith(("...", "(")) or a["text"][:1].islower(): continue
        for j in range(i, len(ev)):
            b = ev[j]; dur = b["end"] - a["start"]
            if dur > MAX_LEN: break
            if dur < MIN_LEN: continue
            if j + 1 < len(ev) and ev[j + 1]["text"].startswith("..."): continue   # mid-sentence cut
            win = ev[i:j + 1]
            total, parts, hw, cw = score_window(win, ep)
            out.append(dict(ep=ep["ep"], start=a["start"], end=max(e["end"] for e in win), score=round(total, 2),
                            parts=parts, flags=hw + cw, events=win))
    return out

def overlap(a, b):
    inter = max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    return inter / (min(a["end"] - a["start"], b["end"] - b["start"]) or 1)

def top_per_episode(cands, k):
    cands = sorted(cands, key=lambda c: -c["score"]); picked = []
    for c in cands:
        if all(overlap(c, p) < 0.3 for p in picked): picked.append(c)
        if len(picked) == k: break
    return picked

# ---------------------------------------------------------------- optional LLM stage
def clip_text(c):
    return "\n".join(f"[{e['start']:.1f}] {e['who'] + ': ' if e['kind']=='line' else '('+e['kind']+') '}{e['text'][:200]}"
                     for e in c["events"])

def llm_rerank(ep, picks, base_url, key, model):
    """Ask any OpenAI-compatible chat model to choose/rank/explain among `picks`. Raises on any failure."""
    body = "\n\n".join(f"### CANDIDATE {i}  ({p['start']:.1f}s-{p['end']:.1f}s)\n{clip_text(p)}" for i, p in enumerate(picks))
    prompt = (f"Episode {ep['ep']} of a vertical microdrama. Logline: {ep['logline']}\n"
              "A promo is a 20-60s clip that opens on a hook in the first 3s, ends on an unresolved cliffhanger, "
              "and makes sense to someone who has never seen the show. Score each candidate 1-10 on that, "
              'and answer ONLY JSON: [{"id":0,"score":7,"hook":"...","cliffhanger":"...","why":"one line"}, ...]\n\n' + body)
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        data=json.dumps({"model": model, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}).encode())
    txt = json.load(urllib.request.urlopen(req, timeout=60))["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\[.*\]", txt, re.S).group(0))

# ---------------------------------------------------------------- output
def mmss(x): return f"{int(x // 60)}:{x % 60:04.1f}"

def describe(c):
    lines = [e for e in c["events"] if e["kind"] == "line"]
    first = next((e for e in c["events"] if e["kind"] != "sfx"), c["events"][0])
    hook = f"{first['who']}: {first['text']}" if first["kind"] == "line" else first["text"]
    last = (lines[-1] if lines else c["events"][-1])
    return dict(hook=hook[:160], cliffhanger=(f"{last['who']}: " if last['kind'] == 'line' else "") + last["text"][:160])

def write_outputs(promos, out):
    os.makedirs(out, exist_ok=True)
    json.dump(promos, open(os.path.join(out, "promos.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(out, "promos.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["rank", "episode", "start", "end", "length_s", "score", "hook", "cliffhanger", "why"])
        for p in promos: w.writerow([p["rank"], p["ep"], mmss(p["start"]), mmss(p["end"]), round(p["end"] - p["start"], 1),
                                     p["score"], p["hook"], p["cliffhanger"], p["why"]])
    with open(os.path.join(out, "promos.md"), "w", encoding="utf-8") as f:
        f.write("# Promo candidates (ranked)\n\n| # | Ep | Start | End | Len | Score | Why |\n|--|--|--|--|--|--|--|\n")
        for p in promos:
            f.write(f"| {p['rank']} | {p['ep']} | {mmss(p['start'])} | {mmss(p['end'])} | {p['end']-p['start']:.0f}s | {p['score']} | {p['why']} |\n")
        f.write("\n## Details\n")
        for p in promos:
            f.write(f"\n**#{p['rank']} - Ep {p['ep']} {mmss(p['start'])}-{mmss(p['end'])}**  \nHook: {p['hook']}  \n"
                    f"Cliffhanger: {p['cliffhanger']}  \nWhy: {p['why']}\n")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pack_dir"); ap.add_argument("--out", default="outputs")
    ap.add_argument("--per-episode", type=int, default=2, help="max promos kept per episode")
    ap.add_argument("--top", type=int, default=40, help="max promos in the final ranked list")
    ap.add_argument("--llm", action="store_true", help="re-rank with an LLM (env LLM_API_KEY, LLM_BASE_URL, LLM_MODEL)")
    a = ap.parse_args(argv)
    eps = load_pack(a.pack_dir); promos = []
    key = os.environ.get("LLM_API_KEY", "")
    base = os.environ.get("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
    model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
    if a.llm and not key: sys.exit("--llm needs LLM_API_KEY")
    for ep in eps:
        picks = top_per_episode(candidates(ep), 5 if a.llm else a.per_episode)
        if a.llm:
            try:
                for j in llm_rerank(ep, picks, base, key, model):
                    p = picks[j["id"]]; p["llm"] = j; p["score"] = float(j["score"])
                picks = sorted([p for p in picks if "llm" in p], key=lambda p: -p["score"])[:a.per_episode]
            except Exception as e:
                print(f"ep {ep['ep']}: LLM stage failed ({e}); keeping heuristic picks", file=sys.stderr)
                picks = picks[:a.per_episode]
        for p in picks:
            d = describe(p); llm = p.get("llm", {})
            promos.append(dict(ep=p["ep"], start=p["start"], end=p["end"], score=p["score"], parts=p["parts"],
                               hook=llm.get("hook", d["hook"]), cliffhanger=llm.get("cliffhanger", d["cliffhanger"]),
                               why=llm.get("why") or "; ".join(dict.fromkeys(p["flags"])) or "high dialogue density"))
    promos.sort(key=lambda p: -p["score"]); promos = promos[:a.top]
    for i, p in enumerate(promos, 1): p["rank"] = i
    write_outputs(promos, a.out)
    print(f"{len(eps)} episodes -> {len(promos)} promos written to {a.out}/")

if __name__ == "__main__":
    main()
