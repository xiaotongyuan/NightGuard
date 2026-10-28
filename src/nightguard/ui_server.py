"""Loopback HTTP for the local three-pane page. No extra framework."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from nightguard.ui_session import UiError, UiSession, _as_temp

HOST = "127.0.0.1"
PORT = 8765
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
LEASE_SEC = 180.0
MAX_BODY_BYTES = 64 * 1024
WRITE_PATHS = {
    "/session",
    "/play",
    "/reset",
    "/next-night",
    "/morning",
    "/label",
    "/ui",
}


def listen_addr() -> tuple[str, int]:
    """Loopback at home. 0.0.0.0 and $PORT when hosted (Render injects PORT)."""
    if os.getenv("SPACE_ID") or os.getenv("SPACE_HOST") or os.getenv("PORT"):
        return "0.0.0.0", int(os.getenv("PORT") or "7860")
    return HOST, PORT

_SESSION: UiSession | None = None
_LLM = None
_SEAT = threading.Lock()
_WRITE = threading.Lock()
_OPERATOR_TOKEN: str | None = None
_OPERATOR_UNTIL = 0.0
_IN_FLIGHT = 0
_LAST_MORNING_AT = 0.0


def _make_session(
    mode: str = "continue",
    temp_c: float = 26.4,
    pass_a_fixture: str = "default",
    filter_text: str = "none",
    start_example: bool = False,
) -> UiSession:
    return UiSession(
        mode=mode,
        temp_c=temp_c,
        pass_a_fixture=pass_a_fixture if _LLM is None else "default",
        filter_text=filter_text,
        llm=_LLM,
        start_example=start_example,
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


def reset_operator() -> None:
    global _OPERATOR_TOKEN, _OPERATOR_UNTIL, _IN_FLIGHT, _LAST_MORNING_AT
    with _SEAT:
        _OPERATOR_TOKEN = None
        _OPERATOR_UNTIL = 0.0
        _IN_FLIGHT = 0
        _LAST_MORNING_AT = 0.0


def request_token(handler: BaseHTTPRequestHandler) -> str:
    return (handler.headers.get("X-Operator-Token") or "").strip()[:64]


def _clear_expired(now: float) -> None:
    global _OPERATOR_TOKEN, _OPERATOR_UNTIL
    if _IN_FLIGHT:
        return
    if _OPERATOR_TOKEN is not None and now >= _OPERATOR_UNTIL:
        _OPERATOR_TOKEN = None
        _OPERATOR_UNTIL = 0.0


def operator_status(token: str) -> dict:
    with _SEAT:
        now = time.monotonic()
        _clear_expired(now)
        held = _OPERATOR_TOKEN is not None and (now < _OPERATOR_UNTIL or _IN_FLIGHT > 0)
        you = held and bool(token) and token == _OPERATOR_TOKEN
        left = max(0, int(_OPERATOR_UNTIL - now)) if held else 0
        if held and left == 0 and _IN_FLIGHT:
            left = 1  # keep watcher UI while a write is still in flight
    return {"held": held, "you": you, "seconds_left": left}


def attach_operator(snap: dict, token: str) -> dict:
    snap["operator"] = operator_status(token)
    return snap


def claim_or_reject(token: str) -> None:
    """First writer takes the seat. Same token refreshes. Anyone else gets 429."""
    global _OPERATOR_TOKEN, _OPERATOR_UNTIL, _IN_FLIGHT
    if not token:
        raise UiError("need_token", 400)
    with _SEAT:
        now = time.monotonic()
        if _IN_FLIGHT and token != _OPERATOR_TOKEN:
            raise UiError("busy", 429)
        _clear_expired(now)
        if _OPERATOR_TOKEN is None:
            _OPERATOR_TOKEN = token
            _OPERATOR_UNTIL = now + LEASE_SEC
            _IN_FLIGHT += 1
            return
        if token == _OPERATOR_TOKEN:
            _OPERATOR_UNTIL = now + LEASE_SEC
            _IN_FLIGHT += 1
            return
        raise UiError("busy", 429)


def finish_write() -> None:
    global _IN_FLIGHT
    with _SEAT:
        if _IN_FLIGHT:
            _IN_FLIGHT -= 1


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    if length > MAX_BODY_BYTES:
        # Drain only the bounded prefix so common clients receive the 413
        # instead of a connection reset while they are still sending.
        handler.rfile.read(min(length, MAX_BODY_BYTES + 1))
        handler.close_connection = True
        raise UiError("request_too_large", 413)
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
            token = request_token(self)
            with _WRITE:
                snap = current_session().snapshot()
            self._send(200, attach_operator(snap, token))
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        token = request_token(self)
        try:
            if path not in WRITE_PATHS:
                self._send(404, {"error": "not_found"})
                return
            body = _read_json(self)
            claim_or_reject(token)
            try:
                with _WRITE:
                    snap = self._mutate(path, body)
            finally:
                finish_write()
            self._send(200, attach_operator(snap, token))
            return
        except UiError as exc:
            self._send_error_id(exc)
            return
        except (ValueError, TypeError):
            self._send(400, {"error": "bad_json"})
            return
        except Exception as exc:
            import sys
            from nightguard.adapter import redact

            key = getattr(_LLM, "api_key", "") or ""
            print(redact(f"llm_failed: {exc}", key), file=sys.stderr, flush=True)
            self._send(502, {"error": "llm_failed"})
            return

    def _mutate(self, path: str, body: dict) -> dict:
        global _LAST_MORNING_AT
        if path == "/session":
            start_example = bool(body.get("start_example"))
            prev = _SESSION
            session = _make_session(
                mode=str(body.get("mode") or "inspect"),
                temp_c=_as_temp(body.get("temp_c", 26.4)),
                pass_a_fixture=str(body.get("pass_a_fixture") or "default"),
                filter_text=str(body.get("filter_text") or "none"),
                start_example=start_example,
            )
            if (
                not start_example
                and prev is not None
                and prev.example.state != "idle"
            ):
                session.example.mark_left()
            return replace_session(session).snapshot()
        session = current_session()
        if path == "/play":
            return session.play(str(body.get("choice_id") or ""))
        if path == "/reset":
            return session.reset_night()
        if path == "/next-night":
            return session.next_night()
        if path == "/morning":
            cooldown = max(0.0, float(os.getenv("NIGHTGUARD_MORNING_COOLDOWN_SEC") or "0"))
            now = time.monotonic()
            if cooldown and _LAST_MORNING_AT and now - _LAST_MORNING_AT < cooldown:
                raise UiError("morning_cooldown", 429)
            script = body.get("script_filter_text")
            snap = session.morning(
                morning_label=str(body.get("morning_label") or "none"),
                script_filter_text=script if isinstance(script, str) else None,
            )
            _LAST_MORNING_AT = now
            return snap
        if path == "/label":
            return session.label(str(body.get("morning_label") or ""))
        return session.set_ui(body)


def wire_llm(kind: str, model: str = "") -> tuple[object | None, str]:
    """Nemotron without a key stays FakeLLM so a public host does not die."""
    if kind == "fake":
        return None, "fake"
    from nightguard.adapter import RemoteLLM
    from nightguard.ui_session import backend_label

    if kind == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            raise SystemExit("GEMINI_API_KEY missing")
        chosen = model or os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
        llm = RemoteLLM(provider="gemini", model=chosen)
        return llm, backend_label(llm)
    if not (os.getenv("NEMOTRON_API_KEY") or "").strip():
        print("NEMOTRON_API_KEY missing; using FakeLLM", flush=True)
        return None, "fake"
    chosen = model or os.getenv("NEMOTRON_MODEL") or "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    hourly = float(os.getenv("NIGHTGUARD_HOURLY_USD") or "0.02")
    llm = RemoteLLM(
        provider="nemotron",
        model=chosen,
        remote_kinds=("morning",),
        hourly_usd=hourly,
    )
    return llm, backend_label(llm)


def enforce_backend_bind(kind: str, host: str) -> None:
    if kind == "gemini" and host != HOST and os.getenv("NIGHTGUARD_ALLOW_PUBLIC_GEMINI") != "1":
        raise SystemExit("Gemini scratch backend is loopback-only")


def main() -> None:
    global _LLM
    os.chdir(Path(__file__).resolve().parents[2])
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", choices=("fake", "gemini", "nemotron"), default="fake")
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    if args.llm != "fake":
        from dotenv import load_dotenv

        load_dotenv()
    host, port = listen_addr()
    enforce_backend_bind(args.llm, host)
    _LLM, label = wire_llm(args.llm, args.model)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"NightGuard UI  http://{host}:{port}/  llm={label}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
