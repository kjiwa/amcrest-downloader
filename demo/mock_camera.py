#!/usr/bin/env python3
import http.server
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path


def generate_dummy_video() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        clip_path = tf.name

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=0.5:size=320x240:rate=10",
        "-f",
        "lavfi",
        "-i",
        "sine=duration=0.5:frequency=440",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        clip_path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    with open(clip_path, "rb") as f:
        video_bytes = f.read()
    Path(clip_path).unlink(missing_ok=True)
    return video_bytes


class MockCameraHandler(http.server.BaseHTTPRequestHandler):
    video_data = b""
    find_count = 0

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)

        if url.path == "/cgi-bin/mediaFileFind.cgi":
            action = qs.get("action", [""])[0]
            if action == "factory.create":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"result=12345\r\n")
            elif action == "findFile":
                MockCameraHandler.find_count = 0
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK\r\n")
            elif action == "findNextFile":
                self.send_response(200)
                self.end_headers()
                if MockCameraHandler.find_count == 0:
                    MockCameraHandler.find_count += 1
                    resp = (
                        "found=2\r\n"
                        "items[0].Channel=0\r\n"
                        "items[0].StartTime=2026-09-09 08:00:00\r\n"
                        "items[0].EndTime=2026-09-09 08:15:00\r\n"
                        "items[0].FilePath=/mnt/sd/2026-09-09/001.mp4\r\n"
                        "items[0].Length=1048576\r\n"
                        "items[1].Channel=0\r\n"
                        "items[1].StartTime=2026-09-09 08:15:00\r\n"
                        "items[1].EndTime=2026-09-09 08:30:00\r\n"
                        "items[1].FilePath=/mnt/sd/2026-09-09/002.mp4\r\n"
                        "items[1].Length=1048576\r\n"
                    )
                    self.wfile.write(resp.encode("utf-8"))
                else:
                    self.wfile.write(b"found=0\r\n")
            elif action in ("close", "destroy"):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK\r\n")
            else:
                self.send_response(404)
                self.end_headers()
        elif url.path.startswith("/cgi-bin/RPC_Loadfile/"):
            import time
            time.sleep(0.3)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(self.video_data)))
            self.end_headers()
            self.wfile.write(self.video_data)
        elif url.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK\r\n")
        elif url.path == "/shutdown":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"bye\r\n")
            threading.Thread(target=self.server.shutdown).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    MockCameraHandler.video_data = generate_dummy_video()
    server = http.server.HTTPServer(("127.0.0.1", port), MockCameraHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
