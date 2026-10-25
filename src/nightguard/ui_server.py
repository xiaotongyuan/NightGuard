"""Loopback HTTP for the local three-pane page. No extra framework."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from nightguard.ui_session import UiSession, UiError

HOST = "127.0.0.1"
PORT = 8765
WEB_DIR = Path(__file__).resolve().parents[2] / "web"

_SESSION: UiSession | None = None
_LLM = None


def _make_session(
    mode: str = "continue",
    temp_c: float = 26.4,
    pass_a_fixture: str = "default",
    filter_text: str = "none",
) -> UiSession:
    return UiSession(
        mode=mode,
        temp_c=temp_c,
        pass_a_fixture=pass_a_fixture if _LLM is None else "default",
        filter_text=filter_text,
        llm=_LLM,
    )


def current_session() -> UiSession:
    global _SESSION
    if _SESSION is None:
        _SESSION = _make_session()
    return _SESSION


def replace_session(session: UiSession) -> UiSession:
    global _SESSION
    _SESSION = session
    return _SESSION


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise UiError("bad_json", 400) from exc
    if not isinstance(data, dict):
        raise UiError("bad_json", 400)
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, status: int, body: dict | bytes, content_type: str = "application/json") -> None:
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_error_id(self, exc: UiError) -> None:
        self._send(exc.status, {"error": exc.code})

    def _static(self, rel: str) -> None:
        if rel in ("", "/"):
            rel = "/index.html"
        path = (WEB_DIR / rel.lstrip("/")).resolve()
        if WEB_DIR.resolve() not in path.parents and path != WEB_DIR.resolve():
            self._send(404, {"error": "not_found"})
            return
        if not path.is_file():
            self._send(404, {"error": "not_found"})
            return
        suffix = path.suffix.lower()
        types = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript"}
        self._send(200, path.read_bytes(), types.get(suffix, "application/octet-stream"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/session":
            self._send(200, current_session().snapshot())
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = _read_json(self)
            if path == "/session":
                session = _make_session(
                    mode=str(body.get("mode") or "continue"),
                    temp_c=float(body.get("temp_c", 26.4)),
                    pass_a_fixture=str(body.get("pass_a_fixture") or "default"),
                    filter_text=str(body.get("filter_text") or "none"),
                )
                self._send(200, replace_session(session).snapshot())
                return
            session = current_session()
            if path == "/play":
                self._send(200, session.play(str(body.get("choice_id") or "")))
                return
            if path == "/reset":
                self._send(200, session.reset_night())
                return
            if path == "/next-night":
                self._send(200, session.next_night())
                return
            if path == "/morning":
                script = body.get("script_filter_text")
                self._send(
                    200,
                    session.morning(
                        morning_label=str(body.get("morning_label") or "none"),
                        script_filter_text=script if isinstance(script, str) else None,
                    ),
                )
                return
            if path == "/label":
                self._send(200, session.label(str(body.get("morning_label") or "")))
                return
            if path == "/ui":
                self._send(200, session.set_ui(body))
                return
        except UiError as exc:
            self._send_error_id(exc)
            return
        except Exception as exc:
            import sys
            from nightguard.adapter import redact

            key = getattr(_LLM, "api_key", "") or ""
            print(redact(f"llm_failed: {exc}", key), file=sys.stderr, flush=True)
            self._send(502, {"error": "llm_failed"})
            return
        self._send(404, {"error": "not_found"})


def main() -> None:
    global _LLM
    os.chdir(Path(__file__).resolve().parents[2])
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=("fake", "gemini", "nemotron"), default="fake")
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    if args.llm == "fake":
        _LLM = None
        label = "fake"
    else:
        from dotenv import load_dotenv

        from nightguard.adapter import RemoteLLM
        from nightguard.ui_session import backend_label

        load_dotenv()
        if args.llm == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                raise SystemExit("GEMINI_API_KEY missing")
            model = args.model or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
            _LLM = RemoteLLM(provider="gemini", model=model)
        else:
            if not os.getenv("NEMOTRON_API_KEY"):
                raise SystemExit("NEMOTRON_API_KEY missing")
            model = args.model or os.getenv("NEMOTRON_MODEL") or "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
            _LLM = RemoteLLM(provider="nemotron", model=model)
        label = backend_label(_LLM)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NightGuard UI  http://{HOST}:{PORT}/  llm={label}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
