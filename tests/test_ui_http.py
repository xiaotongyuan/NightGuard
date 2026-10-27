"""Loopback /play and /morning. No browser, no remote model."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from nightguard import ui_server
from nightguard.ui_session import UiError


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Operator-Token"] = token
    return headers


def _get(base: str, path: str, token: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(base + path, headers=_headers(token), method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post(base: str, path: str, body: dict, token: str | None = "solo") -> tuple[int, dict]:
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers=_headers(token),
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
    ui_server.reset_operator()
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
        ui_server.reset_operator()


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
    ui_server.reset_operator()
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
        ui_server.reset_operator()


def test_http_remote_outage_uses_fake_without_leaking_the_key(monkeypatch):
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
    ui_server.reset_operator()
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
        status, snap = _post(base, "/play", {"choice_id": "open.scratch.left_calf"})
        assert status == 200
        assert snap["llm_backend"] == "remote error"
        assert snap["llm"]["fallback"] == "unknown network error; FakeLLM is used"
        assert snap["llm"]["remote"] is None
        assert snap["last_step"]["kind"] != "none"
        assert key not in json.dumps(snap)
        session = ui_server.current_session()
        assert len(session.loop.log.rows) >= 1
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_second_client_watches_while_operator_is_active():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, peek = _get(base, "/session", token="bob")
        assert status == 200
        assert peek["operator"] == {"held": False, "you": False, "seconds_left": 0}

        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token="alice")
        assert status == 200
        assert opened["window"]["open"] is True
        assert opened["operator"]["held"] is True
        assert opened["operator"]["you"] is True
        assert opened["operator"]["seconds_left"] > 0

        for path, body in (
            ("/play", {"choice_id": "follow.wait15"}),
            ("/reset", {}),
            ("/next-night", {}),
            ("/morning", {"morning_label": "none"}),
            ("/label", {"morning_label": "mosquito"}),
            ("/ui", {"temp_c": 8}),
            ("/session", {"mode": "continue"}),
        ):
            status, denied = _post(base, path, body, token="bob")
            assert status == 429, path
            assert denied == {"error": "busy"}

        status, snap = _get(base, "/session", token="bob")
        assert status == 200
        assert snap["window"]["open"] is True
        assert snap["last_step"]["kind"] == "pass_a"
        assert snap["operator"]["held"] is True
        assert snap["operator"]["you"] is False

        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"}, token="alice")
        assert status == 200
        assert waited["window"]["open"] is False
        assert waited["last_step"]["kind"] == "pass_b"
        assert waited["operator"]["you"] is True
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_expired_lease_lets_the_next_client_take_over():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token="alice")
        assert status == 200
        assert opened["window"]["open"] is True

        ui_server._OPERATOR_UNTIL = 0.0

        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"}, token="bob")
        assert status == 200
        assert waited["window"]["open"] is False
        assert waited["operator"]["you"] is True

        status, denied = _post(base, "/reset", {}, token="alice")
        assert status == 429
        assert denied == {"error": "busy"}
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_write_without_token_is_rejected():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, denied = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token=None)
        assert status == 400
        assert denied == {"error": "need_token"}
        status, also = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token="")
        assert status == 400
        assert also == {"error": "need_token"}
        status, snap = _get(base, "/session")
        assert status == 200
        assert snap["last_step"]["kind"] == "none"
        assert snap["operator"] == {"held": False, "you": False, "seconds_left": 0}
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_same_operator_refreshes_the_lease():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token="alice")
        assert status == 200
        ui_server._OPERATOR_UNTIL = time.monotonic() + 2
        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"}, token="alice")
        assert status == 200
        assert waited["operator"]["you"] is True
        assert waited["window"]["open"] is False
        assert ui_server._OPERATOR_UNTIL > time.monotonic() + ui_server.LEASE_SEC - 1
        status, denied = _post(base, "/reset", {}, token="bob")
        assert status == 429
        assert denied == {"error": "busy"}
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_short_lease_expires_without_forcing_the_clock(monkeypatch):
    monkeypatch.setattr(ui_server, "LEASE_SEC", 0.05)
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, opened = _post(base, "/play", {"choice_id": "open.scratch.left_calf"}, token="alice")
        assert status == 200
        time.sleep(0.08)
        status, waited = _post(base, "/play", {"choice_id": "follow.wait15"}, token="bob")
        assert status == 200
        assert waited["operator"]["you"] is True
        assert waited["window"]["open"] is False
        status, denied = _post(base, "/reset", {}, token="alice")
        assert status == 429
        assert denied == {"error": "busy"}
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_in_flight_write_blocks_takeover_even_if_lease_hits_zero():
    ui_server.reset_operator()
    try:
        ui_server.claim_or_reject("alice")
        ui_server._OPERATOR_UNTIL = 0.0
        try:
            ui_server.claim_or_reject("bob")
            raise AssertionError("bob should stay busy while alice is in flight")
        except UiError as exc:
            assert exc.code == "busy"
            assert exc.status == 429
        assert ui_server._OPERATOR_TOKEN == "alice"
    finally:
        ui_server.finish_write()
        ui_server.reset_operator()


def test_http_bad_temp_is_400_not_llm_failed():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, denied = _post(base, "/ui", {"temp_c": "abc"})
        assert status == 400
        assert denied == {"error": "bad_json"}
        status, also = _post(base, "/session", {"mode": "continue", "temp_c": "abc"})
        assert status == 400
        assert also == {"error": "bad_json"}
        status, snap = _get(base, "/session")
        assert status == 200
        assert snap["temp_c"] == 26.4
        assert snap["last_step"]["kind"] == "none"
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_rejects_oversized_json_body():
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, denied = _post(base, "/ui", {"padding": "x" * ui_server.MAX_BODY_BYTES})
        assert status == 413
        assert denied == {"error": "request_too_large"}
        assert ui_server._OPERATOR_TOKEN is None
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_http_morning_cooldown_limits_one_operator(monkeypatch):
    monkeypatch.setenv("NIGHTGUARD_MORNING_COOLDOWN_SEC", "60")
    saved_session, saved_llm = ui_server._SESSION, ui_server._LLM
    ui_server._SESSION = None
    ui_server._LLM = None
    ui_server.reset_operator()
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, first = _post(base, "/morning", {"morning_label": "none"})
        assert status == 200
        assert first["night_id"] == "n2"
        status, denied = _post(base, "/morning", {"morning_label": "none"})
        assert status == 429
        assert denied == {"error": "morning_cooldown"}
        status, snap = _get(base, "/session")
        assert status == 200
        assert snap["night_id"] == "n2"
    finally:
        server.shutdown()
        server.server_close()
        ui_server._SESSION = saved_session
        ui_server._LLM = saved_llm
        ui_server.reset_operator()


def test_listen_addr_local(monkeypatch):
    monkeypatch.delenv("SPACE_ID", raising=False)
    monkeypatch.delenv("SPACE_HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert ui_server.listen_addr() == ("127.0.0.1", 8765)


def test_listen_addr_space(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "user/NightGuard")
    monkeypatch.setenv("PORT", "7860")
    assert ui_server.listen_addr() == ("0.0.0.0", 7860)


def test_listen_addr_port_only(monkeypatch):
    monkeypatch.delenv("SPACE_ID", raising=False)
    monkeypatch.delenv("SPACE_HOST", raising=False)
    monkeypatch.setenv("PORT", "10000")
    assert ui_server.listen_addr() == ("0.0.0.0", 10000)


def test_gemini_public_bind_requires_explicit_override(monkeypatch):
    monkeypatch.delenv("NIGHTGUARD_ALLOW_PUBLIC_GEMINI", raising=False)
    try:
        ui_server.enforce_backend_bind("gemini", "0.0.0.0")
    except SystemExit as exc:
        assert "loopback-only" in str(exc)
    else:
        raise AssertionError("public Gemini should be refused")
    monkeypatch.setenv("NIGHTGUARD_ALLOW_PUBLIC_GEMINI", "1")
    ui_server.enforce_backend_bind("gemini", "0.0.0.0")
    ui_server.enforce_backend_bind("gemini", "127.0.0.1")
    ui_server.enforce_backend_bind("nemotron", "0.0.0.0")


def test_nemotron_without_key_uses_fake(monkeypatch):
    monkeypatch.delenv("NEMOTRON_API_KEY", raising=False)
    llm, label = ui_server.wire_llm("nemotron")
    assert llm is None
    assert label == "fake"


def test_nemotron_blank_key_uses_fake(monkeypatch):
    monkeypatch.setenv("NEMOTRON_API_KEY", "   ")
    llm, label = ui_server.wire_llm("nemotron")
    assert llm is None
    assert label == "fake"


def test_nemotron_with_key_uses_nano(monkeypatch):
    monkeypatch.setenv("NEMOTRON_API_KEY", "secret-key-value")
    llm, label = ui_server.wire_llm("nemotron")
    assert llm is not None
    assert getattr(llm, "provider", "") == "nemotron"
    assert getattr(llm, "remote_kinds", None) == frozenset({"morning"})
    assert label == "nano"
