# NightGuard JSON contract (golden)

Bodies sent to the LLM, and JSON received from it, **must look like this**. Events and memory cards on disk use the same keys. The loop is in `docs/design_spec.md`.

All JSON is **ASCII / English**. String enums are never Chinese.

Rules:

- Each object has a fixed key set. Defaults are `"none"` or `0` / `0.0` / `false`. **Do not drop keys.**
- One flat layer. No nested objects or arrays (memory is the pre-rendered string `memory_text`).
- `reasoning` / `reason` / `brief` / `timeline` / `memory_text` are English so Nano and judges can read raw JSON.
- This file is authoritative. Other docs only cite it.

---

## Enums

```
night_id          n1 | n2 | n3 | n4
motion_type       scratch_burst | curl | sit_up | leave_bed | slow_roll | sigh_shift | none
body_zone         left_calf | left_foot | right_calf | right_foot | head | neck | shoulder | torso | none
human_sound       none | sheet_rustle | slap | sigh | footsteps
posture           lie_stable | sit | off_bed
belief_state      quiet | possible_harassment | routine_wake | general_discomfort
light             off | on
mode              none | silent_confirm | assist_search
brightness        none | very_low | medium
aim               none | floor_left | floor_right | wall_head | wall_side | wall_right
verdict           appropriate | too_strong | too_weak | inconclusive
morning_label     none | mosquito | not_mosquito | unsure
outcome_15min     settled_lie | sat_up | left_bed | scratch_again_after_5m | no_new_event
```

`aim` is a rule table, not an LLM invention:

```
left_calf | left_foot   -> floor_left
right_calf | right_foot -> floor_right
head | neck | shoulder  -> wall_head
torso                   -> wall_side
light=off or default    -> none
```

---

## 0. Rule gate — before any prompt (code, no new fields)

Gate first. Any hit: **no LLM**. Code writes a flat JSON with the same shape as a Pass A snapshot (`light=off`).  
`temp_c` is **indoor**, not an outdoor forecast. The freeze line is `temp_c <= 10`.

| Condition | Action | Fixed `reasoning` |
| --- | --- | --- |
| `temp_c <= 10` | no prompt, `light=off` | `Gated: indoor temp_c<=10. No LLM.` |
| `posture` is `sit` or `off_bed` | same | `Gated: person already up. No LLM.` |
| `motion_type` is `leave_bed` | same | `Gated: leave_bed. No LLM.` |
| `posture=lie_stable` and `motion_type=none` | same | `Gated: settled lie. Lights off. No LLM.` |
| `motion_type` is not `scratch_burst` / `curl` / `sigh_shift` | same | `Gated: motion not a trigger. No LLM.` |
| Night LLM already 6 (Pass A, Pass B, and retries; morning excluded) | same | `Gated: night llm budget. No LLM.` |

Gate output still has the nine downstream Pass A snapshot keys, e.g. a cold room:

```json
{
  "reasoning": "Gated: indoor temp_c<=10. No LLM.",
  "belief_state": "quiet",
  "belief_p": 0.05,
  "awake": false,
  "light": "off",
  "mode": "none",
  "brightness": "none",
  "duration_s": 0,
  "aim": "none"
}
```

A frantic scratch still does not ask the model. Habitual self-scratch on a cold night stops here.  
`rain_mm_24h` may be outdoor (a prior, never a hard gate). `humidity` is indoor and not a hard gate.  
**No pardon.** `sit` + `slap` (a dark slap) is not released and does not open a short rule light. If they sat up, we do not add noise. `off_bed` is always lamp off.

This table is only for **opening a new Pass A**. While the watch window is open, `sit` / `leave_bed` / `off_bed` enter review and are not dropped here.  
New Pass A motions are only `scratch_burst | curl | sigh_shift`, still lying, indoor `temp_c > 10`. `slow_roll` does not open.

---

## 1. Event — one night-log line (simulator)

A human event. Indoor temperature and outdoor rain are flat. There is no mosquito-audio field.

```json
{
  "night_id": "n2",
  "t": "03:12:40",
  "temp_c": 26.4,
  "rain_mm_24h": 11.2,
  "humidity": 86,
  "motion_type": "scratch_burst",
  "body_zone": "left_calf",
  "amp": 0.31,
  "duration_s": 4.2,
  "centroid_shift": 0.08,
  "human_sound": "sheet_rustle",
  "posture": "lie_stable"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `night_id` | enum | Which night |
| `t` | string `HH:MM:SS` | Clock |
| `temp_c` | number | **Indoor** °C. Hard gates use this, not an outdoor forecast |
| `rain_mm_24h` | number | Outdoor 24h rain mm, prior only |
| `humidity` | number | **Indoor** relative humidity 0–100, not a hard gate |
| `motion_type` | enum | How the person moved |
| `body_zone` | enum | Where the person was bothered, not a mosquito coordinate |
| `amp` | number | Motion amplitude 0–1 |
| `duration_s` | number | Motion duration seconds |
| `centroid_shift` | number | Pressure-centroid shift 0–1 |
| `human_sound` | enum | Sound the person made |
| `posture` | enum | Posture at that beat |

---

## 2. Pass A input — first judgment sent to the LLM

Window summary plus pre-rendered memory. `window_min` is fixed at 5. `memory_text` is English assembled by our code. The card array is not sent.

```json
{
  "night_id": "n2",
  "t": "03:12:40",
  "temp_c": 26.4,
  "rain_mm_24h": 11.2,
  "humidity": 86,
  "window_min": 5,
  "motion_type": "scratch_burst",
  "body_zone": "left_calf",
  "amp": 0.31,
  "duration_s": 4.2,
  "centroid_shift": 0.08,
  "human_sound": "sheet_rustle",
  "posture": "lie_stable",
  "memory_text": "n1 02:05 | motion_type: sigh_shift (torso) | outcome_15min: left_bed | first_light: off | correction: none | response_verdict: appropriate | morning_label: none\nhabit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)",
  "uncertain_count": 0,
  "active_filter": "none"
}
```

`memory_text` does not write `weight` or a diagnosis. At most 5 latest high-weight cards, one line each; habits are extra `habit:` lines (aggregated from all high-weight cards, a group needs at least 3). Empty is `none`. Template:

```
{night_id} {HH:MM} | motion_type: {motion_type} ({body_zone}) | outcome_15min: {outcome_15min} | first_light: {first_light} | correction: {correction} | response_verdict: {verdict} | morning_label: {morning_label}
habit: ~02:00 outcome_15min=left_bed x4 | motion_counts: curl x1, sigh_shift x3 (±30min)
```

| Field | Type | Meaning |
| --- | --- | --- |
| (all Event fields above) |  | Current window, the person |
| `window_min` | int | Window length, fixed 5 |
| `memory_text` | string | Pre-rendered high-weight memory, or `none` |
| `uncertain_count` | int | Count of down-weighted inconclusive cards not listed |
| `active_filter` | string | The filter line this event hit, or `none`. Forms in §8 |

---

## 3. Pass A model output and derived snapshot

The model returns only these four keys:

```json
{
  "reasoning": "Still lying. Left-calf scratch burst. No prior memory. Low belief. Do not disturb long.",
  "belief_state": "possible_harassment",
  "belief_p": 0.34,
  "mode": "silent_confirm"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `reasoning` | string | Why, in English |
| `belief_state` | enum | Hidden-state discrete value |
| `belief_p` | number | `P(harass)`, 0–1 |
| `mode` | enum | `none | silent_confirm | assist_search` |

Code then derives and keeps, on the Pass A, action, card, and UI snapshot: `awake` from posture; `none` → `light=off, brightness=none, duration_s=0, aim=none`; `silent_confirm` → `on, very_low, 4`; `assist_search` → `on, medium, 6`. Both on modes take `aim` from the body-zone table. `downweight` caps `belief_p` at 0.3 and turns `assist_search` into `silent_confirm`.

---

## 4. Pass B input — later review

Pass A’s conclusion and the next 15 minutes of the person, one flat object.

```json
{
  "night_id": "n2",
  "t": "03:12:40",
  "motion_type": "scratch_burst",
  "body_zone": "left_calf",
  "posture": "lie_stable",
  "belief_state": "possible_harassment",
  "belief_p": 0.34,
  "light": "on",
  "mode": "silent_confirm",
  "first_light": "on",
  "first_mode": "silent_confirm",
  "correction": "none",
  "outcome_15min": "sat_up",
  "later_posture": "sit",
  "later_motion_type": "sit_up",
  "later_human_sound": "slap"
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `night_id` `t` |  | Which Pass A |
| `motion_type` `body_zone` `posture` |  | The person then |
| `belief_state` `belief_p` `light` `mode` |  | The lamp under review (the second lamp if one was upgraded) |
| `first_light` `first_mode` |  | First Pass A lamp |
| `correction` | enum `none` / `upgraded_on` | Whether that one `off→on` happened in the window |
| `outcome_15min` | enum | How the person was after 15 minutes (main feedback) |
| `later_posture` | enum | Posture at the end of the 15 minutes |
| `later_motion_type` | enum | Most salient motion in the 15 minutes |
| `later_human_sound` | enum | Human sound in the 15 minutes |

`outcome_15min`:

```
settled_lie              settled again. A second scratch in the first 5 minutes still belongs to the opening cluster
sat_up                   sat up and slapped
left_bed                 left the bed (and may return)
scratch_again_after_5m   still lying and scratching after 5 minutes
no_new_event             almost nothing new → verdict must be inconclusive
```

---

## 5. Pass B output

```json
{
  "verdict": "too_weak",
  "revised_belief_p": 0.62,
  "reason": "Person sat up and slapped within 15 minutes after a dim confirm. Harassment likely continued."
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `verdict` | enum | Was that lamp policy right |
| `revised_belief_p` | number | `P(harass)` after review |
| `reason` | string | Must name later human state, English; no wingbeat / mosquito sound |

Prompt-locked meaning: `light=off` then `left_bed` or `settled_lie` → `appropriate`; `light=on` then `settled_lie` → `too_strong`; `sat_up` or `scratch_again_after_5m` → `too_weak`. Code overwrites only one deterministic contract: `no_new_event` → `inconclusive`. The rest is model review; `light=on` then `left_bed` stays ambiguous.

---

## 6. Memory card — on disk, never sent as an LLM array

Written by our code. Before Pass A, filter by weight, then render as `memory_text`.

```json
{
  "card_id": "n1-0114",
  "night_id": "n1",
  "t": "01:14:00",
  "motion_type": "scratch_burst",
  "body_zone": "left_calf",
  "belief_state": "possible_harassment",
  "belief_p": 0.34,
  "light": "on",
  "mode": "silent_confirm",
  "first_light": "off",
  "first_mode": "none",
  "correction": "upgraded_on",
  "verdict": "too_weak",
  "revised_belief_p": 0.62,
  "reason": "Person sat up and slapped within 15 minutes.",
  "outcome_15min": "sat_up",
  "morning_label": "mosquito",
  "weight": 1.0
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `card_id` | string | `"{night_id}-{HHmm}"` |
| `light` `mode` |  | Last lamp (the upgrade if one happened) |
| `first_light` `first_mode` |  | First Pass A |
| `correction` | enum `none` / `upgraded_on` | Whether that one in-window `off→on` happened |
| `weight` | number | `inconclusive` and no morning label → `0.1`; else → `1.0`; after a morning stamp → `1.0` |
| `outcome_15min` | enum | Pass B outcome then. Habits use this, not a diagnosis |
| `morning_label` | enum | `none` = no feedback; `unsure` = the user chose unsure |

Retrieval and `habit:` lines are `docs/design_spec.md` §4.3. `inconclusive` is not listed line by line; it only adds to `uncertain_count`.

---

## 7. Morning label — UI three keys

```json
{
  "night_id": "n1",
  "morning_label": "mosquito"
}
```

After the tap: related cards that night get `morning_label`. `weight` becomes `1.0` (`unsure` stays 0.1).

---

## 8. Morning brief — one call outside the loop (not in the nightly 6)

Trigger: `docs/design_spec.md` §1. Once per night, after the window closes. Not a night body event and not a window timer.

Input:

```json
{
  "night_id": "n2",
  "habit_text": "habit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)",
  "last_night_text": "n2 03:12 | motion_type: scratch_burst (left_calf) | outcome_15min: sat_up | first_light: off | correction: upgraded_on | response_verdict: too_weak | morning_label: mosquito",
  "yesterday_filter": "none",
  "morning_label": "mosquito"
}
```

| Field | Meaning |
| --- | --- |
| `habit_text` | Rendered habit lines, or `none` |
| `last_night_text` | Last night’s new card lines, or `none` |
| `yesterday_filter` | Yesterday’s live `filter_text`, or `none` |
| `morning_label` | Three keys; untapped is `none` |

Output:

```json
{
  "brief": "Night n2: one dim confirm at 03:12. Later sit-slap. Morning label mosquito.",
  "timeline": "03:12 scratch_burst left_calf -> silent_confirm -> sat_up -> too_weak",
  "filter_text": "downweight ~01:55-02:15 motion sigh_shift"
}
```

`brief` and `timeline` are one English line each. `filter_text` is multi-line English or `none`, never a JSON array.  
This morning call is **not** in the nightly 6.  
Code and model accept only two opcodes: `ignore` and `downweight`, timed or bare. Every non-`none` line must contain the literal token `motion`; motion is only `scratch_burst | curl | sigh_shift`. Accept rules: `docs/design_spec.md` §4.9. Regex `fullmatch`, no `split()`. Midnight and reversed ends use `clock_arc_min`. `23:30-00:30` is a legal 60-minute band; `02:15-01:55` is the same band as `01:55-02:15`. Hard gates are not edited here.

Preserve before creating: if a legal `yesterday_filter` still matches a habit and `morning_label` is `none` or `unsure`, copy it verbatim. Ordinary last-night cards do not authorize a rewrite of opcode, window, or grammar. Only a relevant explicit `mosquito` / `not_mosquito` or a newly qualifying other habit may change or add.

New-rule shape is locked by evidence: a clock habit in `habit_text` with `~HH:MM` and target `motion_counts≥3` may only become a timed rule; a non-clock `motion morning not_mosquito x3` habit may only become a bare rule; with neither, no new rule. Card times in `last_night_text` are for the brief and timeline only. They cannot be a timed-rule center or edge.

---

## 9. Parse failure (every LLM output)

1. Pure JSON. No markdown fences.
2. Missing key / illegal enum / not flat → retry once.
3. Fail again: rule fallback. Do not regex-scrape.
4. A successful parse still runs `sanitize_pass_a`: derive `light/brightness/duration_s/aim` from `mode`, and `awake` from `posture`. Do not return `json.loads` raw.

Pass A rule fallback:

```json
{
  "reasoning": "parse_failed. Conservative default.",
  "belief_state": "quiet",
  "belief_p": 0.2,
  "awake": false,
  "light": "off",
  "mode": "none",
  "brightness": "none",
  "duration_s": 0,
  "aim": "none"
}
```

The UI also marks `llm_parse_failed=true` (program state, not a model field).

---

## 10. Forbidden keys

`peak_hz`, `snr_db`, `suspect_mosquito_audio`, `x`, `y`, `location`, `curtain`, `count`, `n_mosquitoes`, `weather`, `motion`, `action`, `belief`, `memory_cards`
