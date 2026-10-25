"""Loopback /play and /morning. No browser, no remote model."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from nightguard import ui_server


def _get(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + path, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post(base: str, path: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_http_play_and_morning():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"})
        assert status == 200
        assert opened["last_step"]["kind"] == "pass_a"
        assert opened["last_step"]["llm_called"] is True
        assert opened["window"]["open"] is True

        status, blocked = _post(base, "/morning", {})
        assert status == 409
        assert blocked["error"] == "window_open"

        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"})
        assert status == 200
        assert waited["window"]["open"] is False
        assert waited["last_step"]["kind"] == "pass_b"

        status, morning = _post(base, "/morning", {"morning_label": "none"})
        assert status == 200
        assert morning["last_step"]["kind"] == "morning"
        assert morning["last_step"]["llm_called"] is True
        assert morning["llm"]["output"]["brief"]
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm


def test_http_billing_falls_back_and_says_out_of_usage(monkeypatch):
    import io

    from nightguard.adapter import RemoteLLM

    key = "secret-key-value"
    real_urlopen = urllib.request.urlopen
    remote_calls = {"n": 0}

    def raise_billing(req, *args, **kwargs):
        url = getattr(req, "full_url", str(req))
        if str(url).startswith("http://127.0.0.1"):
            return real_urlopen(req, *args, **kwargs)
        remote_calls["n"] += 1
        raise urllib.error.HTTPError(
            url,
            402,
            "Payment Required",
            None,
            io.BytesIO(b'{"error":{"code":"insufficient_quota","message":"credit balance is 0"}}'),
        )

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_billing)
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = RemoteLLM(
        provider="nemotron",
        api_key=key,
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        base_url="https://example.invalid/v1",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"})
        assert status == 200
        assert opened["llm_backend"] == "out of usage"
        assert opened["last_step"]["kind"] == "pass_a"
        assert opened["window"]["open"] is True
        assert key not in json.dumps(opened)

        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"})
        assert status == 200
        assert waited["last_step"]["kind"] == "pass_b"
        assert waited["llm_backend"] == "out of usage"
        assert remote_calls["n"] == 1
        assert key not in json.dumps(waited)
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm


def test_http_remote_outage_is_502_without_leaking_the_key(monkeypatch):
    import urllib.error

    from nightguard.adapter import RemoteLLM

    key = "secret-key-value"
    real_urlopen = urllib.request.urlopen

    def raise_offline(req, *args, **kwargs):
        url = getattr(req, "full_url", str(req))
        if url.startswith("http://127.0.0.1"):
            return real_urlopen(req, *args, **kwargs)
        raise urllib.error.URLError(f"offline {key}")

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_offline)
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = RemoteLLM(
        provider="nemotron",
        api_key=key,
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        base_url="https://example.invalid/v1",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, failed = _post(base, "/play", {"choice_id": "open.scratch.left_calf"})
        assert status == 502
        assert failed == {"error": "llm_failed"}
        assert key not in json.dumps(failed)

        status, snap = _get(base, "/session")
        assert status == 200
        assert snap["window"]["open"] is False
        assert snap["last_step"]["kind"] == "none"
        assert key not in json.dumps(snap)
        session = ui_server.current_session()
        assert len(session.loop.log.rows) == 1
        assert session.loop.window.is_open is False
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
