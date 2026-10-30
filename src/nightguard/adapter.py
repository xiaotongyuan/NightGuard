"""One remote LLM client. Providers are wire specs, not extra classes."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from nightguard.llm import FakeLLM, parse_morning_json, parse_pass_a_json, parse_pass_b_json
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
MAX_OUTPUT_TOKENS = 2048


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
        "maxOutputTokens": MAX_OUTPUT_TOKENS,
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
            "max_tokens": MAX_OUTPUT_TOKENS,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )


def _field_text(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list):
        parts = [part.get("text", "") for part in value if isinstance(part, dict)]
        joined = "".join(parts)
        if joined.strip():
            return joined
    return ""


def _looks_json_object(text: str) -> bool:
    return text.lstrip().startswith("{")


def extract_openai(payload: dict) -> str:
    """Prefer the answer box. Scratch notes are only a JSON-shaped last resort."""
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("remote empty")
    message = choices[0].get("message") or {}
    content = _field_text(message.get("content"))
    if content:
        return content
    scratch = _field_text(message.get("reasoning_content")) or _field_text(message.get("reasoning"))
    if scratch and _looks_json_object(scratch):
        return scratch
    raise RuntimeError("remote empty")


def require_contract(kind: str, raw: str) -> str:
    """Project, then parse. Scratch prose must not become a successful remote beat."""
    projected = project_to_contract(kind, raw)
    if kind == "pass_a":
        parse_pass_a_json(projected)
    elif kind == "morning":
        parse_morning_json(projected)
    else:
        parse_pass_b_json(projected)
    return projected


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
        default_model="nvidia/Nemotron-3_5-Lightning",
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


# Token Factory list price for nvidia/Nemotron-3_5-Lightning.
NANO_USD_PER_1M_INPUT = 0.06
NANO_USD_PER_1M_OUTPUT = 0.24
# If the vendor omits usage, still count something so a tight loop cannot stay free.
USD_PER_CALL_FLOOR = 0.0002
# Keep this much of the hourly purse available before opening another request.
# The bounded prompts and replies cost far less; this prevents a last tiny
# remainder from authorizing one more full HTTP call.
USD_PER_CALL_RESERVE = 0.001


def estimate_usd(usage: dict | None) -> float:
    """Dollars for one Token Factory reply. Missing usage pays the floor."""
    if not usage:
        return USD_PER_CALL_FLOOR
    prompt = float(usage.get("prompt_tokens") or 0)
    completion = float(usage.get("completion_tokens") or 0)
    if prompt == 0 and completion == 0:
        total = float(usage.get("total_tokens") or 0)
        cost = total / 1_000_000.0 * NANO_USD_PER_1M_INPUT
    else:
        cost = (
            prompt / 1_000_000.0 * NANO_USD_PER_1M_INPUT
            + completion / 1_000_000.0 * NANO_USD_PER_1M_OUTPUT
        )
    return max(cost, USD_PER_CALL_FLOOR)


class HourlyUsdCap:
    """One hour, one purse. Unused dollars die at the UTC hour. No carry.

    claim() takes the only in-flight seat so two threads cannot both HTTP.
    settle() after the hour bills the new hour. The dying hour keeps only
    what it already spent.
    """

    def __init__(
        self,
        limit_usd: float,
        now_fn: Callable[[], float] | None = None,
        min_call_usd: float = USD_PER_CALL_RESERVE,
    ) -> None:
        self.limit_usd = max(0.0, float(limit_usd))
        self.min_call_usd = max(0.0, float(min_call_usd))
        self.now_fn = now_fn or time.time
        self._lock = threading.Lock()
        self._hour_id: int | None = None
        self._in_flight = False
        self.spent_usd = 0.0

    def _roll(self) -> None:
        hour_id = int(self.now_fn() // 3600)
        if hour_id != self._hour_id:
            self._hour_id = hour_id
            self.spent_usd = 0.0

    def remaining(self) -> float:
        with self._lock:
            self._roll()
            return max(0.0, self.limit_usd - self.spent_usd)

    def exhausted(self) -> bool:
        return self.remaining() < self.min_call_usd

    def allow(self) -> bool:
        return not self.exhausted()

    def claim(self) -> bool:
        with self._lock:
            self._roll()
            remaining = self.limit_usd - self.spent_usd
            if self._in_flight or remaining < self.min_call_usd:
                return False
            self._in_flight = True
            return True

    def settle(self, usd: float) -> None:
        with self._lock:
            self._roll()
            self._in_flight = False
            self.spent_usd += max(0.0, float(usd))

    def release(self) -> None:
        with self._lock:
            self._roll()
            self._in_flight = False

    def add(self, usd: float) -> None:
        with self._lock:
            self._roll()
            self.spent_usd += max(0.0, float(usd))

    def status(self) -> dict:
        with self._lock:
            self._roll()
            remaining = max(0.0, self.limit_usd - self.spent_usd)
            return {
                "limit_usd": self.limit_usd,
                "spent_usd": self.spent_usd,
                "remaining_usd": remaining,
                "min_call_usd": self.min_call_usd,
                "exhausted": remaining < self.min_call_usd,
            }


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
            if is_out_of_usage(last_err):
                raise RuntimeError(last_err) from None
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
        remote_kinds: tuple[str, ...] | None = None,
        hourly_usd: float | None = None,
        now_fn: Callable[[], float] | None = None,
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
        self.remote_kinds = frozenset(remote_kinds) if remote_kinds is not None else None
        self.hourly = HourlyUsdCap(hourly_usd, now_fn) if hourly_usd is not None else None
        self.calls: list[tuple[str, dict]] = []
        self.out_of_usage = False
        self.last_usage: dict | None = None
        self.last_remote: dict | None = None
        self.last_fallback: str | None = None

    def encode(self, kind: str, payload: dict) -> HttpRequest:
        system, user = pack_user(kind, payload)
        req = self.spec.encode(system, user, self.api_key, self.model, self.base_url)
        self.last_remote = {"url": req.url, "model": self.model}
        return req

    def _local(self, kind: str, payload: dict) -> str:
        return FakeLLM().complete(kind, payload)

    def _use_fake(self, kind: str, payload: dict, note: str | None) -> str:
        self.last_remote = None
        self.last_fallback = note
        return self._local(kind, payload)

    def complete(self, kind: str, payload: dict) -> str:
        self.calls.append((kind, payload))
        if self.remote_kinds is not None and kind not in self.remote_kinds:
            return self._local(kind, payload)
        if self.out_of_usage:
            return self._use_fake(kind, payload, None)
        claimed = False
        if self.hourly is not None:
            if not self.hourly.claim():
                return self._use_fake(kind, payload, None)
            claimed = True
        try:
            try:
                body = call_http(self.encode(kind, payload), self.api_key, self.spec.retry_http)
                self.last_usage = _usage_from(body)
                try:
                    billed_usd = estimate_usd(self.last_usage)
                except (TypeError, ValueError):
                    billed_usd = USD_PER_CALL_FLOOR
                if claimed:
                    self.hourly.settle(billed_usd)
                    claimed = False
                raw = self.spec.extract(body)
                try:
                    projected = require_contract(kind, raw)
                except (ValueError, TypeError, json.JSONDecodeError, RuntimeError):
                    return self._use_fake(kind, payload, "unknown remote error; FakeLLM is used")
            except Exception as exc:
                if isinstance(exc, RuntimeError) and is_out_of_usage(str(exc)):
                    self.out_of_usage = True
                    return self._use_fake(kind, payload, None)
                if isinstance(exc, urllib.error.HTTPError):
                    note = "unknown remote error; FakeLLM is used"
                elif isinstance(exc, urllib.error.URLError):
                    note = "unknown network error; FakeLLM is used"
                else:
                    note = "unknown remote error; FakeLLM is used"
                return self._use_fake(kind, payload, note)
            self.last_fallback = None
            return projected
        finally:
            if claimed:
                self.hourly.release()


def make_remote_llm() -> RemoteLLM:
    return RemoteLLM()
