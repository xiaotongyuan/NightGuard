"""One remote LLM client. Providers are wire specs, not extra classes."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from nightguard.llm import FakeLLM
from nightguard.prompts import (
    MORNING_FILTER_GRAMMAR,
    MORNING_SYSTEM,
    PASS_A_SYSTEM,
    PASS_B_SYSTEM,
    messages,
    reply_enums,
)
from nightguard.schema import (
    BELIEF_STATES,
    MODES,
    MORNING_OUTPUT_KEYS,
    PASS_A_MODEL_KEYS,
    PASS_B_OUTPUT_KEYS,
    VERDICTS,
)

@dataclass(frozen=True)
class HttpRequest:
    url: str
    headers: dict[str, str]
    body: dict


EncodeFn = Callable[[str, str, str, str, str], HttpRequest]
ExtractFn = Callable[[dict], str]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    key_env: str
    model_env: str
    default_model: str
    base_url_env: str
    default_base: str
    encode: EncodeFn
    extract: ExtractFn
    retry_http: tuple[int, ...] = (429, 503)


def _system_for(kind: str) -> str:
    if kind == "pass_a":
        return PASS_A_SYSTEM
    if kind == "morning":
        return MORNING_SYSTEM
    return PASS_B_SYSTEM


def contract_hint(kind: str) -> str:
    enums = reply_enums(kind)
    if kind == "pass_a":
        return (
            "Return exactly these keys and no others: "
            + ", ".join(PASS_A_MODEL_KEYS)
            + ".\nTypes: reasoning=one-line string; belief_state=enum; "
            "belief_p=number from 0.0 to 1.0; mode=enum.\n"
            + enums
        )
    if kind == "morning":
        return (
            "Return exactly these keys and no others: "
            + ", ".join(MORNING_OUTPUT_KEYS)
            + ".\nTypes: brief=one-line string; timeline=one-line string; "
            "filter_text=string containing none or newline-separated opcode lines.\n"
            + MORNING_FILTER_GRAMMAR
            + "\n"
            + enums
        )
    return (
        "Return exactly these keys and no others: "
        + ", ".join(PASS_B_OUTPUT_KEYS)
        + ".\nTypes: verdict=enum; revised_belief_p=number from 0.0 to 1.0; "
        "reason=one-line string. If outcome_15min is no_new_event, verdict must be inconclusive.\n"
        + enums
    )


def pack_user(kind: str, payload: dict) -> tuple[str, str]:
    packed = messages(_system_for(kind), payload)
    user = contract_hint(kind) + "\n\nInput:\n" + packed[1]["content"]
    return packed[0]["content"], user


def _allowed_keys(kind: str) -> tuple[str, ...]:
    if kind == "pass_a":
        return PASS_A_MODEL_KEYS
    if kind == "morning":
        return MORNING_OUTPUT_KEYS
    return PASS_B_OUTPUT_KEYS


def project_to_contract(kind: str, raw: str) -> str:
    """Drop markdown fences and extra keys. Contract parse still requires the remaining keys."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:]
        if inner and inner[-1].strip().startswith("```"):
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        return raw
    allowed = _allowed_keys(kind)
    if len(set(data) & set(allowed)) < 3:
        for value in data.values():
            if isinstance(value, dict) and len(set(value) & set(allowed)) >= 3:
                data = value
                break
    projected = {k: data[k] for k in allowed if k in data}
    if kind == "pass_a":
        if "belief_p" in projected:
            projected["belief_p"] = float(projected["belief_p"])
        if projected.get("belief_state") not in BELIEF_STATES:
            projected["belief_state"] = "quiet"
        if projected.get("mode") not in MODES:
            projected["mode"] = "none"
    if kind == "pass_b":
        if "revised_belief_p" in projected:
            projected["revised_belief_p"] = float(projected["revised_belief_p"])
        if projected.get("verdict") not in VERDICTS:
            projected["verdict"] = "inconclusive"
    return json.dumps(projected, ensure_ascii=True)


def encode_gemini(system: str, user: str, api_key: str, model: str, base_url: str) -> HttpRequest:
    root = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    config = {
        "temperature": 0.1,
        "responseMimeType": "application/json",
    }
    if "2.5" in model:
        config["thinkingConfig"] = {"thinkingBudget": 0}
    return HttpRequest(
        url=f"{root}/models/{model}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        body={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": config,
        },
    )


def extract_gemini(payload: dict) -> str:
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if p.get("text")]
    if not texts:
        raise RuntimeError("remote empty")
    return texts[0]


def encode_openai(system: str, user: str, api_key: str, model: str, base_url: str) -> HttpRequest:
    if not base_url:
        raise RuntimeError("openai-compat provider needs a base_url")
    return HttpRequest(
        url=f"{base_url.rstrip('/')}/chat/completions",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        body={
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )


def extract_openai(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("remote empty")
    text = choices[0].get("message", {}).get("content") or ""
    if not text:
        raise RuntimeError("remote empty")
    return text


PROVIDERS: dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        name="gemini",
        key_env="GEMINI_API_KEY",
        model_env="GEMINI_MODEL",
        default_model="gemini-3.5-flash-lite",
        base_url_env="GEMINI_BASE_URL",
        default_base="https://generativelanguage.googleapis.com/v1beta",
        encode=encode_gemini,
        extract=extract_gemini,
    ),
    "nemotron": ProviderSpec(
        name="nemotron",
        key_env="NEMOTRON_API_KEY",
        model_env="NEMOTRON_MODEL",
        default_model="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        base_url_env="NEMOTRON_BASE_URL",
        default_base="",
        encode=encode_openai,
        extract=extract_openai,
    ),
}


def redact(text: str, api_key: str) -> str:
    if api_key and api_key in text:
        return text.replace(api_key, "<redacted>")
    return text


_OUT_OF_USAGE_MARKERS = (
    "insufficient_quota",
    "insufficient_credit",
    "insufficient credits",
    "insufficient credit",
    "out of credit",
    "out_of_credits",
    "credit balance",
    "payment required",
    "exceeded your current quota",
    "billing_hard_limit",
    "insufficient_funds",
    "no credits",
    "quota_exceeded",
    "trial has ended",
    "trial ended",
)


def is_out_of_usage(message: str) -> bool:
    """Billing refusal. Rate limits stay ordinary failures."""
    text = message.lower()
    if "remote http 402" in text:
        return True
    if "rate limit" in text or "too many requests" in text:
        return False
    return any(marker in text for marker in _OUT_OF_USAGE_MARKERS)


def _usage_from(payload: dict) -> dict | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion = usage.get("completion_tokens", usage.get("output_tokens"))
    total = usage.get("total_tokens")
    if prompt is None and completion is None and total is None:
        return None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def call_http(req: HttpRequest, api_key: str, retry_http: tuple[int, ...] = (429, 503)) -> dict:
    last_err = "remote empty"
    for attempt in range(2):
        http_req = urllib.request.Request(
            req.url,
            data=json.dumps(req.body).encode("utf-8"),
            headers=req.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")[:240]
            last_err = redact(f"remote http {exc.code}: {err}", api_key)
            if exc.code in retry_http and attempt == 0:
                time.sleep(3)
                continue
            raise RuntimeError(last_err) from None
    raise RuntimeError(last_err)


class RemoteLLM:
    """Shared complete(kind, payload). Swap LLM_PROVIDER, not the class."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        name = (provider or os.getenv("LLM_PROVIDER") or "gemini").strip().lower()
        if name not in PROVIDERS:
            raise ValueError(f"unknown LLM_PROVIDER={name!r}; expected {sorted(PROVIDERS)}")
        self.spec = PROVIDERS[name]
        self.provider = name
        self.api_key = api_key if api_key is not None else os.getenv(self.spec.key_env, "")
        self.model = model or os.getenv(self.spec.model_env, self.spec.default_model)
        self.base_url = (
            base_url
            if base_url is not None
            else os.getenv(self.spec.base_url_env, self.spec.default_base)
        )
        self.calls: list[tuple[str, dict]] = []
        self.out_of_usage = False
        self.last_usage: dict | None = None
        self.last_remote: dict | None = None

    def encode(self, kind: str, payload: dict) -> HttpRequest:
        system, user = pack_user(kind, payload)
        req = self.spec.encode(system, user, self.api_key, self.model, self.base_url)
        self.last_remote = {"url": req.url, "model": self.model}
        return req

    def complete(self, kind: str, payload: dict) -> str:
        self.calls.append((kind, payload))
        if self.out_of_usage:
            return FakeLLM().complete(kind, payload)
        try:
            body = call_http(self.encode(kind, payload), self.api_key, self.spec.retry_http)
        except RuntimeError as exc:
            if is_out_of_usage(str(exc)):
                self.out_of_usage = True
                return FakeLLM().complete(kind, payload)
            raise
        self.last_usage = _usage_from(body)
        raw = self.spec.extract(body)
        try:
            return project_to_contract(kind, raw)
        except (ValueError, TypeError, json.JSONDecodeError):
            return raw


def make_remote_llm() -> RemoteLLM:
    return RemoteLLM()
