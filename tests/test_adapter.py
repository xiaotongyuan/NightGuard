"""Adapter wires only. No live HTTP."""

import io
import json
import urllib.error

from nightguard.adapter import RemoteLLM, call_http, encode_gemini, extract_openai, project_to_contract
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
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
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
        "model": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
    }
    assert "secret-key" not in json.dumps(nemotron.last_remote)
    assert "Return exactly these keys" in g.body["contents"][0]["parts"][0]["text"]
    assert "Return exactly these keys" in n.body["messages"][1]["content"]
    assert "Example:" not in g.body["contents"][0]["parts"][0]["text"]
    assert "Example:" not in n.body["messages"][1]["content"]
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
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
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
        model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
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
