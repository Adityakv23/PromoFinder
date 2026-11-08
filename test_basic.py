"""Run: python tests/test_basic.py   (no pytest needed; builds a tiny fake episode, no real data)."""
import json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import promo_finder as pf

def block(who, a, b, text): return f"**{who}:**\nStart: ({a}) | End: ({b})\n{text}\n\n"

EP = ("EPISODE NUMBER: Episode 1\nEPISODE LOGLINE: A bride is jilted.\n\n--- SCRIPT START ---\n\nSCENE 01\n"
      "Scene heading: INT. CHURCH\nScene start: 00:00.00\nScene end: 01:10.00\n\n"
      + block("CAMERA", "00:00.00", "00:03.00", "wide shot")
      + block("ACTION", "00:01.00", "00:04.00", "The groom slaps her.")
      + "".join(block("LADY (Angry)", f"00:{5+i*6:02d}.00", f"00:{8+i*6:02d}.00", f'"Line {i}, who are you?!"') for i in range(10))
      + block("SOUND FX", "01:05.00", "01:09.00", "Ominous sting, cliffhanger.") + "--- SCRIPT END ---\n")

def test_parse_and_candidates():
    d = tempfile.mkdtemp(); open(os.path.join(d, "episode-001-Episode 1.txt"), "w").write(EP)
    ep = pf.load_pack(d)[0]
    assert ep["ep"] == 1 and all(e["kind"] != "camera" for e in ep["events"]) and ep["end"] == 69.0
    cs = pf.candidates(ep)
    assert cs and all(pf.MIN_LEN <= c["end"] - c["start"] <= pf.MAX_LEN + 5 for c in cs)
    best = pf.top_per_episode(cs, 1)[0]
    assert best["end"] >= 60, "should prefer the window that ends on the episode sting"

def test_llm_stage_with_fake_server():
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            out = json.dumps({"choices": [{"message": {"content": '[{"id":0,"score":9,"hook":"h","cliffhanger":"c","why":"w"}]'}}]}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    ep = {"ep": 1, "logline": "x"}; pick = {"start": 0, "end": 30, "events": [{"kind": "line", "who": "A", "start": 0, "end": 2, "text": "hi"}]}
    r = pf.llm_rerank(ep, [pick], f"http://127.0.0.1:{srv.server_port}", "k", "m")
    srv.shutdown(); assert r[0]["score"] == 9 and r[0]["why"] == "w"

if __name__ == "__main__":
    test_parse_and_candidates(); test_llm_stage_with_fake_server(); print("ok")
