"""Tareekh Ki Kahani - YOUTUBE HELPER.
YOUTUBE_HELPER.bat starts this. While this window is open, Claude can hand the finished files in
"Ready to Upload" (video, Shorts, thumbnail, subtitles) to YouTube Studio in the Claude browser.
It only READS files inside "Ready to Upload", only on this laptop (127.0.0.1). Close the window when done."""
import json, mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
READY = (ROOT / "Ready to Upload").resolve()
PORT = 8766
ALLOWED = ("https://studio.youtube.com", "https://www.youtube.com")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.end_headers()

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        try:
            if u.path == "/list":
                files = [str(p.relative_to(READY)).replace("\\", "/") for p in READY.rglob("*")
                         if p.is_file() and "_old versions" not in p.parts]
                body = json.dumps(sorted(files), ensure_ascii=False).encode("utf-8")
                self.send_response(200); self.cors()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if u.path == "/file":
                p = (READY / q.get("p", [""])[0]).resolve()
                if READY not in p.parents or not p.is_file(): raise FileNotFoundError("not in Ready to Upload")
                size = p.stat().st_size
                self.send_response(200); self.cors()
                self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(size)); self.end_headers()
                with open(p, "rb") as f:
                    while chunk := f.read(1 << 20): self.wfile.write(chunk)
                print(f"  sent: {p.name}  ({size / 1e6:.1f} MB)"); return
            self.send_response(404); self.cors(); self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            self.send_response(404); self.cors(); self.end_headers(); print("  refused:", e)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("\n  YOUTUBE HELPER is running. Keep this window open while Claude uploads.")
    print("  It only reads files in 'Ready to Upload'. Close this window when the upload is done.\n")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
