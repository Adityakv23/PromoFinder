# Promo finder (Kuku AI Generalist assignment, Problem 1)

Reads microdrama screenplays and returns the best 20-60s promo clips: episode, start/end timestamps, hook, cliffhanger, one-line why, ranked.
Pure Python 3.9+ standard library. No installs, no paid API.

## Run

```bash
# 1. put the unzipped episode-*.txt files anywhere (the input pack is Kuku's content: it is NOT in this repo)
python promo_finder.py PACK_DIR --out outputs                       # free, offline, ~15 s for 50 episodes
python promo_finder.py PACK_DIR --out outputs --per-episode 5 --top 200   # wider candidate list for an editor

# optional: let any OpenAI-compatible model re-rank the top 5 windows per episode
export LLM_API_KEY=...                                  # Gemini free tier key works
export LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai   # default; swap for Groq/OpenRouter/Ollama
export LLM_MODEL=gemini-2.0-flash                       # swap the model here, nothing else changes
python promo_finder.py PACK_DIR --out outputs --llm
```

Outputs: `promos.md` (readable), `promos.csv`, `promos.json` (with score breakdown).

## Check it

```bash
python tests/test_basic.py                                               # parser, window rules, LLM stage vs a fake server
python eval/evaluate.py outputs/promos.json eval/gold_picks.json         # compare with the hand-reviewed picks
python eval/make_curated.py PACK_DIR                                     # rebuild outputs/curated_promos.*
```

## Folder

- `promo_finder.py` the whole tool (parse -> windows -> score -> optional LLM re-rank -> write)
- `outputs/promos.*` raw, unedited tool output on all 50 episodes (`--per-episode 2 --top 100`)
- `outputs/curated_promos.*` the reviewed final list (48 promos, tiers A/B/C, posting order)
- `eval/gold_picks.json` the reviewed picks used for evaluation

## Not done / known limits

The LLM stage has only been tested against a fake local server (no API key was used while building), so treat it as unproven. Promos are single windows inside one episode (no cross-episode stitching). It reads screenplay text only, so it cannot see the video or hear audio.
