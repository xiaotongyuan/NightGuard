"""Live Nano example walk. Off unless NIGHTGUARD_NEMOTRON=1. Never prints the key."""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from nightguard.adapter import RemoteLLM
from nightguard.llm import WATER_IGNORE
from nightguard.ui_session import UiSession

from tests.test_ui_flows import assert_snapshot_legal


def _walk_to_morning(session: UiSession) -> None:
    for _ in range(3):
        session.play("open.sigh.torso")
        session.play("follow.leave.plus1")
        if session.night_id != "n3":
            session.next_night()


@pytest.mark.nemotron
def test_E15_live_nano_example_morning_keeps_night4_scratch_open():
    if os.getenv("NIGHTGUARD_NEMOTRON") != "1":
        pytest.skip("set NIGHTGUARD_NEMOTRON=1 to spend one Token Factory morning")
    load_dotenv()
    if not (os.getenv("NEMOTRON_API_KEY") or "").strip():
        pytest.skip("NEMOTRON_API_KEY missing")
    llm = RemoteLLM(provider="nemotron", remote_kinds=("morning",), hourly_usd=0.02)
    session = UiSession(mode="continue", start_example=True, llm=llm)
    _walk_to_morning(session)
    snap = session.morning()
    assert llm.last_fallback is None
    assert llm.last_remote is not None
    assert llm.last_usage is not None
    assert snap["llm_backend"] == "lightning"
    assert snap["memory"]["filter_text"] == WATER_IGNORE
    assert snap["llm"]["output"]["filter_text"]
    assert snap["llm"]["remote"]["model"]
    snap = session.play("open.sigh.torso")
    assert snap["last_step"]["kind"] == "filtered"
    assert snap["window"]["open"] is False
    assert snap["example"]["highlight"]["choice_id"] == "open.scratch.left_calf"
    assert "open.scratch.left_calf" in snap["enabled_choices"]
    snap = session.play("open.scratch.left_calf")
    assert snap["example"]["state"] == "finished"
    assert snap["last_step"]["kind"] == "pass_a"
    leftover = RemoteLLM(provider="nemotron", remote_kinds=("morning",), hourly_usd=0.02)
    leftover.last_remote = llm.last_remote
    restart = UiSession(mode="continue", start_example=True, llm=leftover)
    cleared = restart.snapshot()
    assert cleared["night_id"] == "n1"
    assert cleared["llm"]["input"] is None
    assert cleared["llm"]["remote"] is None
    assert_snapshot_legal(snap)
    assert_snapshot_legal(cleared)
