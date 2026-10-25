from nightguard.gates import decide_llm, gate_reason


def test_warm_lie_scratch_passes_gate():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="lie_stable",
        motion_type="scratch_burst",
        llm_calls_tonight=0,
    )
    assert ok is True
    assert out is None


def test_indoor_cold_blocks_even_if_scratch_looks_like_harass():
    reason = gate_reason(
        temp_c=8.0,
        posture="lie_stable",
        motion_type="scratch_burst",
        llm_calls_tonight=0,
    )
    assert reason == "Gated: indoor temp_c<=10. No LLM."
    ok, out = decide_llm(
        temp_c=8.0,
        posture="lie_stable",
        motion_type="scratch_burst",
        llm_calls_tonight=0,
    )
    assert ok is False
    assert out["light"] == "off"
    assert out["aim"] == "none"


def test_sat_up_is_not_pardoned():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="sit",
        motion_type="scratch_burst",
        llm_calls_tonight=0,
    )
    assert ok is False
    assert out["reasoning"] == "Gated: person already up. No LLM."
    assert out["awake"] is True


def test_leave_bed_blocks():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="lie_stable",
        motion_type="leave_bed",
        llm_calls_tonight=0,
    )
    assert ok is False
    assert "leave_bed" in out["reasoning"]


def test_budget_blocks_at_six():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="lie_stable",
        motion_type="scratch_burst",
        llm_calls_tonight=6,
    )
    assert ok is False
    assert "budget" in out["reasoning"]


def test_G5_slow_roll_is_not_a_trigger():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="lie_stable",
        motion_type="slow_roll",
        llm_calls_tonight=0,
    )
    assert ok is False
    assert "not a trigger" in out["reasoning"]
    assert out["light"] == "off"


def test_G8_settled_lie_turns_light_off():
    ok, out = decide_llm(
        temp_c=26.4,
        posture="lie_stable",
        motion_type="none",
        llm_calls_tonight=0,
    )
    assert ok is False
    assert "settled lie" in out["reasoning"]
    assert out["light"] == "off"
    assert out["awake"] is False


def test_G7_curl_and_sigh_shift_pass():
    for motion in ("curl", "sigh_shift"):
        ok, out = decide_llm(
            temp_c=26.4,
            posture="lie_stable",
            motion_type=motion,
            llm_calls_tonight=0,
        )
        assert ok is True
        assert out is None
