"""Adapter wires only. No live HTTP."""

import io
import json
import urllib.error

from nightguard.adapter import (
    HTTP_TIMEOUT_S,
    RemoteLLM,
    call_http,
    encode_gemini,
    extract_openai,
    project_to_contract,
)
from nightguard.schema import PASS_A_MODEL_KEYS


def test_A1_project_strips_fence_and_extra_keys():
    raw = (
        "```json\n"
        '{"reasoning": "x", "belief_state": "quiet", "belief_p": "0.2", '
        '"mode": "none", "extra": 1}\n'
        "```"
    )
    out = project_to_contract("pass_a", raw)
    assert "```" not in out
    assert "extra" not in out
    for key in PASS_A_MODEL_KEYS:
        assert f'"{key}"' in out


def test_A2_gemini_and_nemotron_encode_same_contract():
    gemini = RemoteLLM(provider="gemini", api_key="secret-key", model="gemini-3.5-flash-lite")
    nemotron = RemoteLLM(
        provider="nemotron",
        api_key="secret-key",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
    )
    payload = {"night_id": "n2"}
    g = gemini.encode("pass_a", payload)
    n = nemotron.encode("pass_a", payload)
    assert g.url.endswith(":generateContent")
    assert "key=" not in g.url
    assert g.headers["x-goog-api-key"] == "secret-key"
    assert n.url.endswith("/chat/completions")
    assert n.headers["Authorization"] == "Bearer secret-key"
    assert nemotron.last_remote == {
        "url": n.url,
        "model": "nvidia/Nemotron-3_5-Lightning",
    }
    assert "secret-key" not in json.dumps(nemotron.last_remote)
    assert "Return exactly these keys" in g.body["contents"][0]["parts"][0]["text"]
    assert "Return exactly these keys" in n.body["messages"][1]["content"]
    assert "Example:" not in g.body["contents"][0]["parts"][0]["text"]
    assert "Example:" not in n.body["messages"][1]["content"]
    assert g.body["generationConfig"]["maxOutputTokens"] == 2048
    assert n.body["max_tokens"] == 2048
    assert n.body["chat_template_kwargs"] == {"enable_thinking": False}
    assert HTTP_TIMEOUT_S == 75
    assert encode_gemini is gemini.spec.encode


def test_A5_prompts_lock_reply_enums():
    from nightguard.prompts import MORNING_SYSTEM, PASS_A_SYSTEM, PASS_B_SYSTEM

    assert "quiet | possible_harassment | routine_wake | general_discomfort" in PASS_A_SYSTEM
    assert "appropriate | too_strong | too_weak | inconclusive" in PASS_B_SYSTEM
    assert "scratch_burst | curl | sigh_shift" in MORNING_SYSTEM
    for prompt in (PASS_A_SYSTEM, PASS_B_SYSTEM, MORNING_SYSTEM):
        assert "TASK\n" in prompt
        assert "INPUT SEMANTICS\n" in prompt
        assert "OUTPUT CONTRACT\n" in prompt
    gemini = RemoteLLM(provider="gemini", api_key="secret-key", model="gemini-3.5-flash-lite")
    user = gemini.encode("pass_a", {"night_id": "n2"}).body["contents"][0]["parts"][0]["text"]
    assert "belief_state must be exactly one of" in user
    morning_user = gemini.encode("morning", {"night_id": "n2"}).body["contents"][0]["parts"][0]["text"]
    assert "<opcode> ~HH:MM-HH:MM motion <motion_enum>" in morning_user
    assert "The word motion is literal and required." in morning_user


def test_A4_project_maps_unknown_belief_to_quiet():
    raw = (
        '{"reasoning": "x", "belief_state": "neutral", "belief_p": 0.2, '
        '"mode": "none"}'
    )
    out = json.loads(project_to_contract("pass_a", raw))
    assert out["belief_state"] == "quiet"


def test_A6_http_failure_stays_local_and_redacts_the_key(monkeypatch):
    key = "secret-key-value"
    llm = RemoteLLM(
        provider="nemotron",
        api_key=key,
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
    )
    req = llm.encode("morning", {"night_id": "n1"})

    def raise_500(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            req.url,
            500,
            "server error",
            None,
            io.BytesIO(f"provider said {key}".encode("utf-8")),
        )

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_500)
    try:
        call_http(req, key, retry_http=())
    except RuntimeError as exc:
        assert key not in str(exc)
        assert "remote http 500" in str(exc)
    else:
        raise AssertionError("http 500 should fail closed")

    def raise_offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_offline)
    try:
        call_http(req, key, retry_http=())
    except urllib.error.URLError as exc:
        assert "offline" in str(exc.reason)
    else:
        raise AssertionError("connection failure should surface")


def test_A7_billing_refusal_uses_fake_and_stops_calling(monkeypatch):
    from nightguard.adapter import is_out_of_usage
    from nightguard.llm import parse_pass_a_json

    assert is_out_of_usage("remote http 402: credit balance is 0") is True
    assert is_out_of_usage("remote http 429: insufficient_quota") is True
    assert is_out_of_usage("remote http 429: rate limit exceeded") is False
    assert is_out_of_usage("remote http 500: server error") is False

    key = "secret-key-value"
    llm = RemoteLLM(
        provider="nemotron",
        api_key=key,
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
    )
    remote_calls = {"n": 0}

    def raise_402(*_args, **_kwargs):
        remote_calls["n"] += 1
        raise urllib.error.HTTPError(
            "https://example.invalid/v1/chat/completions",
            402,
            "Payment Required",
            None,
            io.BytesIO(b'{"error":{"code":"insufficient_quota","message":"credit balance is 0"}}'),
        )

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_402)
    first = parse_pass_a_json(llm.complete("pass_a", {"motion_type": "scratch_burst", "night_id": "n1"}))
    second = parse_pass_a_json(llm.complete("pass_a", {"motion_type": "sigh_shift", "night_id": "n1"}))
    assert llm.out_of_usage is True
    assert remote_calls["n"] == 1
    assert first["mode"] in ("none", "silent_confirm", "assist_search")
    assert second["mode"] in ("none", "silent_confirm", "assist_search")
    assert key not in json.dumps(first)


def test_A3_errors_redact_api_key():
    from nightguard.adapter import redact

    key = "secret-key-value"
    hidden = redact(f"remote http 401: used {key}", key)
    assert key not in hidden
    assert "<redacted>" in hidden
    try:
        extract_openai({"choices": []})
    except RuntimeError as exc:
        assert "empty" in str(exc)
    reasoned = extract_openai(
        {"choices": [{"message": {"content": "", "reasoning_content": '{"brief":"x"}'}}]}
    )
    assert reasoned == '{"brief":"x"}'
    assert (
        extract_openai({"choices": [{"message": {"content": '{"brief":"from content"}', "reasoning_content": "{"}}]})
        == '{"brief":"from content"}'
    )
    try:
        extract_openai({"choices": [{"message": {"content": None, "reasoning": "just thinking"}}]})
    except RuntimeError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("prose scratch notes must not become the answer")


def _openai_ok(content: str, prompt: int = 1000, completion: int = 80) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        },
    }


def test_A8_nemotron_page_only_remotes_morning(monkeypatch):
    from nightguard.adapter import estimate_usd
    from nightguard.llm import parse_morning_json, parse_pass_a_json, parse_pass_b_json

    assert estimate_usd({"prompt_tokens": 1_000_000, "completion_tokens": 0}) == 0.06
    assert estimate_usd({"prompt_tokens": 0, "completion_tokens": 1_000_000}) == 0.24

    hits = {"n": 0}
    morning_json = json.dumps(
        {"brief": "Night n1.", "timeline": "none", "filter_text": "none"}
    )

    class _Resp:
        def __init__(self, payload: dict):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

    def urlopen(req, *args, **kwargs):
        hits["n"] += 1
        return _Resp(_openai_ok(morning_json))

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", urlopen)
    now = [1000.0]
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: now[0],
    )
    pass_a = parse_pass_a_json(llm.complete("pass_a", {"motion_type": "scratch_burst", "night_id": "n1"}))
    parse_pass_b_json(
        llm.complete("pass_b", {"outcome_15min": "no_new_event", "later_motion_type": "none"})
    )
    assert hits["n"] == 0
    assert pass_a["mode"] in ("none", "silent_confirm", "assist_search")
    morning = parse_morning_json(llm.complete("morning", {"night_id": "n1", "yesterday_filter": "none"}))
    assert hits["n"] == 1
    assert morning["brief"]
    assert llm.hourly is not None
    assert llm.hourly.spent_usd > 0
    assert llm.out_of_usage is False


def test_A9_hourly_cap_expires_and_does_not_carry(monkeypatch):
    from nightguard.llm import parse_morning_json

    morning_json = json.dumps(
        {"brief": "Night n1.", "timeline": "none", "filter_text": "none"}
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_openai_ok(morning_json, prompt=10, completion=10)).encode("utf-8")

    hits = {"n": 0}

    def urlopen(req, *args, **kwargs):
        hits["n"] += 1
        return _Resp()

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", urlopen)
    now = [3600.0]
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: now[0],
    )
    assert llm.hourly is not None
    llm.hourly.add(0.10)
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert hits["n"] == 0
    assert llm.out_of_usage is False
    now[0] = 7200.0
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert hits["n"] == 1
    assert llm.hourly.spent_usd < 0.10
    assert llm.out_of_usage is False


def test_A10_wallet_claim_is_single_seat():
    from nightguard.adapter import HourlyUsdCap

    now = [1000.0]
    cap = HourlyUsdCap(0.10, now_fn=lambda: now[0])
    assert cap.claim() is True
    assert cap.claim() is False
    cap.release()
    assert cap.claim() is True
    cap.settle(0.10)
    assert cap.claim() is False
    assert cap.exhausted() is True
    now[0] = 4600.0
    assert cap.claim() is True


def test_A11_urlerror_releases_the_wallet_seat(monkeypatch):
    from nightguard.llm import parse_morning_json

    hits = {"n": 0}
    morning_json = json.dumps(
        {"brief": "Night n1.", "timeline": "none", "filter_text": "none"}
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_openai_ok(morning_json, prompt=10, completion=10)).encode("utf-8")

    def urlopen(req, *args, **kwargs):
        hits["n"] += 1
        if hits["n"] == 1:
            raise urllib.error.URLError("offline")
        return _Resp()

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", urlopen)
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    first = parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert first["brief"]
    assert llm.last_fallback == "unknown network error; FakeLLM is used"
    assert llm.last_remote is None
    assert llm.hourly is not None
    assert llm.hourly.exhausted() is False
    assert llm.out_of_usage is False
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert hits["n"] == 2
    assert llm.last_fallback is None
    assert llm.out_of_usage is False


def test_A12_settle_after_the_hour_bills_the_new_hour():
    from nightguard.adapter import HourlyUsdCap

    now = [3599.0]
    cap = HourlyUsdCap(0.10, now_fn=lambda: now[0])
    assert cap.claim() is True
    now[0] = 3601.0
    cap.settle(0.01)
    assert cap.spent_usd == 0.01
    assert cap.exhausted() is False


def test_A13_fake_fallback_clears_last_remote(monkeypatch):
    from nightguard.llm import parse_morning_json

    morning_json = json.dumps(
        {"brief": "Night n1.", "timeline": "none", "filter_text": "none"}
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_openai_ok(morning_json, prompt=10, completion=10)).encode("utf-8")

    def raise_402(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid/v1/chat/completions",
            402,
            "Payment Required",
            None,
            io.BytesIO(b'{"error":{"code":"insufficient_quota","message":"credit balance is 0"}}'),
        )

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_402)
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert llm.out_of_usage is True
    assert llm.last_remote is None

    llm2 = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    llm2.last_remote = {"url": "https://example.invalid/v1", "model": llm2.model}
    assert llm2.hourly is not None
    llm2.hourly.add(0.10)
    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    parse_morning_json(llm2.complete("morning", {"night_id": "n1"}))
    assert llm2.last_remote is None


def test_A14_remote_morning_bad_json_is_not_paid_twice(monkeypatch):
    from nightguard.llm import invoke

    hits = {"n": 0}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_openai_ok("{", prompt=10, completion=10)).encode("utf-8")

    def urlopen(*_args, **_kwargs):
        hits["n"] += 1
        return _Resp()

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", urlopen)
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    payload = {"night_id": "n1", "yesterday_filter": "none"}
    out, attempts, failed = invoke(llm, "morning", payload, {})
    assert hits["n"] == 1
    assert attempts == 1
    assert failed is False
    assert llm.last_fallback == "unknown remote error; FakeLLM is used"
    assert out["filter_text"] == "none"


def test_A15_http_500_uses_fake_and_is_not_sticky(monkeypatch):
    from nightguard.llm import parse_morning_json

    hits = {"n": 0}
    morning_json = json.dumps(
        {"brief": "Night n1.", "timeline": "none", "filter_text": "none"}
    )

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(_openai_ok(morning_json, prompt=10, completion=10)).encode("utf-8")

    def urlopen(req, *args, **kwargs):
        hits["n"] += 1
        if hits["n"] == 1:
            raise urllib.error.HTTPError(
                "https://example.invalid/v1/chat/completions",
                500,
                "server error",
                None,
                io.BytesIO(b'{"error":"nope"}'),
            )
        return _Resp()

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", urlopen)
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert llm.last_fallback == "unknown remote error; FakeLLM is used"
    assert llm.last_remote is None
    assert llm.out_of_usage is False
    parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert hits["n"] == 2
    assert llm.last_fallback is None


def test_A16_wallet_reserves_the_last_mill(monkeypatch):
    from nightguard.adapter import HourlyUsdCap

    cap = HourlyUsdCap(0.10, now_fn=lambda: 1000.0)
    cap.add(0.0991)
    assert cap.status()["remaining_usd"] < cap.status()["min_call_usd"]
    assert cap.exhausted() is True
    assert cap.claim() is False


def test_A17_billing_429_is_not_retried(monkeypatch):
    hits = {"n": 0}
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
    )

    def raise_quota(*_args, **_kwargs):
        hits["n"] += 1
        raise urllib.error.HTTPError(
            "https://example.invalid/v1/chat/completions",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(b'{"error":{"code":"insufficient_quota"}}'),
        )

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", raise_quota)
    llm.complete("morning", {"night_id": "n1"})
    assert hits["n"] == 1
    assert llm.out_of_usage is True


def test_A18_empty_remote_envelope_uses_fake_after_settlement(monkeypatch):
    from nightguard.llm import parse_morning_json

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"choices": [], "usage": {"total_tokens": 10}}).encode("utf-8")

    monkeypatch.setattr("nightguard.adapter.urllib.request.urlopen", lambda *_a, **_k: _Resp())
    llm = RemoteLLM(
        provider="nemotron",
        api_key="secret-key-value",
        model="nvidia/Nemotron-3_5-Lightning",
        base_url="https://example.invalid/v1",
        remote_kinds=("morning",),
        hourly_usd=0.10,
        now_fn=lambda: 1000.0,
    )
    out = parse_morning_json(llm.complete("morning", {"night_id": "n1"}))
    assert out["brief"]
    assert llm.last_fallback == "unknown remote error; FakeLLM is used"
    assert llm.last_remote is None
    assert llm.hourly is not None
    assert llm.hourly.spent_usd > 0
