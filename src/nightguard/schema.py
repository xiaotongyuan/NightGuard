"""Frozen enums. Values must stay ASCII. See docs/json_contract.md."""

NIGHT_IDS = ("n1", "n2", "n3", "n4")
MOTION_TYPES = (
    "scratch_burst",
    "curl",
    "sit_up",
    "leave_bed",
    "slow_roll",
    "sigh_shift",
    "none",
)
BODY_ZONES = (
    "left_calf",
    "left_foot",
    "right_calf",
    "right_foot",
    "head",
    "neck",
    "shoulder",
    "torso",
    "none",
)
HUMAN_SOUNDS = ("none", "sheet_rustle", "slap", "sigh", "footsteps")
POSTURES = ("lie_stable", "sit", "off_bed")
BELIEF_STATES = ("quiet", "possible_harassment", "routine_wake", "general_discomfort")
LIGHTS = ("off", "on")
MODES = ("none", "silent_confirm", "assist_search")
BRIGHTNESSES = ("none", "very_low", "medium")
AIMS = ("none", "floor_left", "floor_right", "wall_head", "wall_side", "wall_right")
VERDICTS = ("appropriate", "too_strong", "too_weak", "inconclusive")
MORNING_LABELS = ("none", "mosquito", "not_mosquito", "unsure")
OUTCOMES_15MIN = (
    "settled_lie",
    "sat_up",
    "left_bed",
    "scratch_again_after_5m",
    "no_new_event",
)
CORRECTIONS = ("none", "upgraded_on")

AIM_FROM_ZONE = {
    "left_calf": "floor_left",
    "left_foot": "floor_left",
    "right_calf": "floor_right",
    "right_foot": "floor_right",
    "head": "wall_head",
    "neck": "wall_head",
    "shoulder": "wall_head",
    "torso": "wall_side",
}

TEMP_GATE_C = 10.0
LLM_BUDGET_PER_NIGHT = 6
WINDOW_MIN = 5
WINDOW_MAX_MIN = 15
FILTER_MAX_SPAN_MIN = 90
FILTER_MAX_LINES = 5
# Motions that may open a new Pass A. slow_roll never does.
PASS_A_TRIGGER_MOTIONS = ("scratch_burst", "curl", "sigh_shift")
LOW_INTENSITY_MOTIONS = ("slow_roll", "curl", "sigh_shift", "none")
HABIT_MIN_COUNT = 3
HABIT_CLOCK_TOLERANCE_MIN = 30
MINUTES_PER_DAY = 1440

EVENT_KEYS = (
    "night_id",
    "t",
    "temp_c",
    "rain_mm_24h",
    "humidity",
    "motion_type",
    "body_zone",
    "amp",
    "duration_s",
    "centroid_shift",
    "human_sound",
    "posture",
)
PASS_A_MODEL_KEYS = (
    "reasoning",
    "belief_state",
    "belief_p",
    "mode",
)
PASS_A_KEYS = (
    "reasoning",
    "belief_state",
    "belief_p",
    "awake",
    "light",
    "mode",
    "brightness",
    "duration_s",
    "aim",
)
PASS_A_INPUT_KEYS = EVENT_KEYS + (
    "window_min",
    "memory_text",
    "uncertain_count",
    "active_filter",
)
PASS_B_INPUT_KEYS = (
    "night_id",
    "t",
    "motion_type",
    "body_zone",
    "posture",
    "belief_state",
    "belief_p",
    "light",
    "mode",
    "first_light",
    "first_mode",
    "correction",
    "outcome_15min",
    "later_posture",
    "later_motion_type",
    "later_human_sound",
)
PASS_B_OUTPUT_KEYS = ("verdict", "revised_belief_p", "reason")
MORNING_INPUT_KEYS = (
    "night_id",
    "habit_text",
    "last_night_text",
    "yesterday_filter",
    "morning_label",
)
MORNING_OUTPUT_KEYS = ("brief", "timeline", "filter_text")
CARD_KEYS = (
    "card_id",
    "night_id",
    "t",
    "motion_type",
    "body_zone",
    "belief_state",
    "belief_p",
    "light",
    "mode",
    "first_light",
    "first_mode",
    "correction",
    "verdict",
    "revised_belief_p",
    "reason",
    "outcome_15min",
    "morning_label",
    "weight",
)
FORBIDDEN_LLM_KEYS = (
    "peak_hz",
    "snr_db",
    "suspect_mosquito_audio",
    "x",
    "y",
    "location",
    "curtain",
    "count",
    "n_mosquitoes",
    "weather",
    "motion",
    "action",
    "belief",
    "memory_cards",
)
DISEASE_WORDS = (
    "skin",
    "disease",
    "dermat",
    "eczema",
    "allerg",
    "illness",
    "medical",
    "chronic",
    "psoriasis",
    "diagnosis",
)
