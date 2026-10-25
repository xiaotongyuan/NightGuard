# Prompt holdouts

This table checks whether Nano understands the prompt. Test inputs and answers here are **not** copied into the runtime prompt. These calls do not run the night loop and do not chain one output into the next input.

Each row is one `invoke(kind, payload)`. Memory, habits, and yesterday’s filter are written into that input.

## How to score

- Keep three copies per row: **raw** (Nano text), **projected** (adapter after fences / extra keys), **final** (parse + sanitize). Meaning is scored on raw. Product safety is scored on final.
- Raw must be one flat JSON object whose keys are exactly the contract. A markdown fence, extra key, missing key, or out-of-enum value is a model-contract fail. `project_to_contract` must not hide that fail.
- `belief_p` / `revised_belief_p` must sit in `[0,1]`. Table thresholds do not require an exact float match.
- `reasoning` / `reason` / `brief` / `timeline` do not require the same wording. Forbidden-word fail: `wingbeat`, `mosquito sound`, and `skin` / `disease` / `dermat` / `eczema` / `allerg` / `illness` / `medical` / `chronic` / `psoriasis` / `diagnosis`.
- Final also checks code overwrite: `awake`, `aim`, off-lamp fields, the `downweight` cap, and `no_new_event → inconclusive`. Those overwrites do not replace the raw model score.
- First pass: once per row, to catch obvious misreads. A freeze candidate: three times per row; all three must pass. Record tokens, latency, and whether a retry happened.
- If one input has two reasonable conclusions, put it under “record only” at the end. That is not a meaning fail.

## Runtime prompt shape

All three prompts use the same order: `TASK → INPUT SEMANTICS → STATE/FILTER/VERDICT SEMANTICS → DECISION POLICY AND PRECEDENCE → OUTPUT CONTRACT`.

Do not give Nano a fixed JSON example that already contains a decision. Field names, types, and enums come from the contract. Concrete A/B/morning examples stay in this file as holdouts.

Unspecified Pass A event fields use: `night_id=n4`, `t=02:00:00`, `temp_c=26.4`, `rain_mm_24h=0`, `humidity=60`, `window_min=5`, `amp=0.2`, `duration_s=3`, `centroid_shift=0.05`, `human_sound=none`, `posture=lie_stable`, `uncertain_count=0`, `active_filter=none`.

Card-line format matches the contract:

```text
n1 02:00 | motion_type: sigh_shift (torso) | outcome_15min: left_bed | first_light: off | correction: none | response_verdict: appropriate | morning_label: none
```

A clock habit also carries the code motion tally. Outcome alone is not enough:

```text
habit: ~02:00 outcome_15min=left_bed x3 | motion_counts: sigh_shift x3 (±30min)
```

Mixed cluster:

```text
habit: ~02:00 outcome_15min=left_bed x4 | motion_counts: curl x1, sigh_shift x3 (±30min)
```

---

## Pass A

The model is deciding **this lamp now**, not a diagnosis, and not whether a mosquito is present. Each row only changes the listed fields. The rest uses the default input.

| ID | Input delta | Raw pass line | Why |
| --- | --- | --- | --- |
| A1 | `sigh_shift` / `torso`, `memory_text=none` | raw: `quiet`, `mode=none`, `belief_p≤0.35`; final derives `light=off` | no-memory low-intensity baseline |
| A2 | `scratch_burst` / `left_calf`, `memory_text=none` | raw: `possible_harassment`, `mode=silent_confirm`; final derives `on, very_low, 4, floor_left` | no-memory scratch baseline |
| A3 | `curl` / `torso`, `uncertain_count=2` | raw: `quiet`, `mode=none`; not `general_discomfort` | negative control under the 3-card bar |
| A4 | same as A3, `uncertain_count=3` | raw: `quiet` or `general_discomfort`, `mode=none` | repeated curl, non-diagnosis state |
| A5 | `sigh_shift` / `torso`, 2 a.m. habit `motion_counts: sigh_shift x3`; latest cards all `appropriate` | raw: `quiet` or `routine_wake`, `mode=none` | get-up habit is an ordinary path |
| A6 | same left-bed habit as A5; also a same-motion history card `first_light:on`, `outcome_15min:settled_lie`, `response_verdict:too_strong` | same as A5 | a legal too_strong history must not promote a routine habit to harassment |
| A7 | `scratch_burst` / `left_calf`, memory is only A5’s sigh habit | same as A2; not `assist_search` | do not migrate a habit across motions |
| A8 | `scratch_burst` / `left_calf`; same-motion card `morning_label:not_mosquito` | `mode=none`; `belief_p≤0.35` | one morning no |
| A9 | same as A8, but `habit: scratch_burst morning not_mosquito x3` | same as A8 | aggregated morning no |
| A10 | `scratch_burst` / `left_calf`; same-motion card `morning_label:mosquito`, verdict not too_weak | `possible_harassment`; `belief_p≥0.5`; `mode=silent_confirm` | morning yes, isolated |
| A11 | `scratch_burst` / `left_calf`; same-motion card `response_verdict:too_weak`, `morning_label:none` | `mode=assist_search`; final derives `on, medium, 6` | upgrade, isolated |
| A12 | current `scratch_burst`; same-motion history `first_light:on`, `outcome_15min:settled_lie`, `response_verdict:too_strong`, `morning_label:none` | `mode=none`; final derives lamp off | read a B6-style card: last lamp too strong, this one off |
| A13 | same-motion card is both `morning_label:mosquito` and `response_verdict:too_weak` | `possible_harassment`; `belief_p≥0.5`; `mode=assist_search` | two positive evidences |
| A14 | same as A13, also hit `downweight ~01:55-02:15 motion scratch_burst` | `possible_harassment`; `belief_p≤0.3`; `mode=silent_confirm` | conflict precedence |
| A15 | same-motion cards include one `morning_label:not_mosquito` and one `response_verdict:too_weak` | `mode=none`; `belief_p≤0.35` | explicit morning no beats an old underestimate |
| A16 | `sigh_shift` / `torso`, `uncertain_count=3`, no memory | `quiet`; `mode=none`; not `general_discomfort` | inconclusive rule does not cross motions |

Every lamp-on row also needs: `aim` is a legal enum; final `aim` is rewritten by code from `body_zone`. Every lamp-off row’s final must be `mode=none`, `brightness=none`, `duration_s=0`, `aim=none`.

---

## Pass B

The model is looking back at **the lamp under review**. Input `belief_state` / `light` / `mode` are that lamp. After an upgrade they are the second lamp; `first_light` is still the first.

| verdict | Meaning |
| --- | --- |
| `appropriate` | later motion fits this lamp |
| `too_strong` | later motion overturns this lamp |
| `too_weak` | they scratched again, or sat up and slapped: too light |
| `inconclusive` | no new motion in fifteen minutes, not enough evidence |

Each `reason` must contain that row’s `outcome_15min` and a value of `later_posture` or `later_motion_type`.

Shared base: `night_id=n4`, `t=02:00:00`, `correction=none`, `first_light` equals `light`, `first_mode` equals `mode`.

| ID | Lamp under review | Later | Raw pass line |
| --- | --- | --- | --- |
| B1 | `sigh_shift` / `torso` / `lie_stable`, `quiet`, `belief_p=0.2`, `light=off`, `mode=none` | `left_bed`, `later_posture=off_bed`, `later_motion_type=leave_bed`, `later_human_sound=none` | `verdict=appropriate`. `revised_belief_p≤0.35` |
| B2 | same as B1, but `belief_state=routine_wake` | same as B1 | `verdict=appropriate`. `revised_belief_p≤0.35` |
| B3 | `scratch_burst` / `left_calf`, `possible_harassment`, `belief_p=0.34`, `light=on`, `mode=silent_confirm` | `sat_up`, `later_posture=sit`, `later_motion_type=sit_up`, `later_human_sound=slap` | `verdict=too_weak`. `revised_belief_p≥0.5` |
| B4 | same first as B1 | `scratch_again_after_5m`, `later_posture=lie_stable`, `later_motion_type=scratch_burst`, `later_human_sound=none` | `verdict=too_weak`. `revised_belief_p≥0.5` |
| B5 | same first as B3 | same later as B4 | `verdict=too_weak`. `revised_belief_p≥0.5` |
| B6 | same first as B3 | `settled_lie`, `later_posture=lie_stable`, `later_motion_type=none`, `later_human_sound=none` | `verdict=too_strong`. `revised_belief_p<0.34` |
| B7 | same first as B1 | same later as B6 | `verdict=appropriate`. `revised_belief_p≤0.35` |
| B8 | `first_light=off`, `first_mode=none`, `correction=upgraded_on`, lamp under review `light=on`, `mode=assist_search`, `belief_state=possible_harassment`, `belief_p=0.55`. Motion `scratch_burst` / `left_calf` | same later as B3 | `verdict=too_weak`. Review the upgraded lamp, not the first off |
| B9 | same as B3 | `no_new_event`, `later_posture=lie_stable`, `later_motion_type=none` | raw itself should be `inconclusive`; sanitize alone must not be the only reason |
| B10 | same as B3 | `left_bed`, `later_posture=off_bed`, `later_motion_type=leave_bed` | record verdict and probability only; no meaning pass line |

B1 is the live check that lamp-off then leave-bed is `appropriate`. B6 and B7 are a pair: the same settle is `too_strong` only if a lamp was on.

Each `reason` must contain the outcome value verbatim and the actual `later_posture` or `later_motion_type` value. Naming the field is not enough.

---

## Morning

The model writes tomorrow’s executable filter so the night can skip a call. `ignore` skips Pass A. `downweight` still runs Pass A with a confidence cap. Motion on a clock rule must come from that habit’s `motion_counts:`. It cannot be guessed from the outcome, and one last-night card cannot invent a three-night habit.

A timed line must overlap the habit clock: the band contains `02:00`, length ≤ 90 minutes. It need not be exactly `01:55-02:15`. `brief` and `timeline` are one English line each.

Preserve before creating: if a legal `yesterday_filter` still matches a habit and `morning_label` is `none` or `unsure`, copy it verbatim. Do not rewrite opcode, window, or drop words. Only a relevant explicit `mosquito` / `not_mosquito` or a newly qualifying other habit may change or add.

New-rule shape is locked by evidence, then the opcode is chosen: a clock habit with `~HH:MM` and matching `motion_counts≥3` may only become a timed rule; a non-clock `motion morning not_mosquito x3` habit may only become a bare rule; with neither, no new rule. Times in `last_night_text` are for the timeline only. A midnight-crossing timed rule may have `start > end`, e.g. `~23:30-00:20`. It must not collapse to a bare rule because it is near midnight. Every non-`none` line must contain the literal token `motion` and fully match the agreed grammar.

### Rows

| ID | Input | Raw pass line | Guards against |
| --- | --- | --- | --- |
| M1 | `habit_text=habit: ~02:00 outcome_15min=left_bed x3 \| motion_counts: sigh_shift x3 (±30min)`. Last-night card also sigh→left_bed, `morning_label:none`. Yesterday none | exactly one `ignore ... sigh_shift` that contains 02:00 and is ≤90 minutes | live `filter_text:none`, without hiding the answer in a single card |
| M2 | same as M1, but the card and `morning_label` are `mosquito` | not that `ignore` line. `none`, or one timed `downweight` `sigh_shift` | “has a get-up habit ⇒ ignore” as a dead rule |
| M3 | same habit as M1. `yesterday_filter=ignore ~01:55-02:15 motion sigh_shift`. `last_night_text` same as M1. `morning_label=none` | return `ignore ~01:55-02:15 motion sigh_shift` verbatim | dropping or rewriting a live line with no new evidence |
| M4 | `habit_text=habit: scratch_burst morning not_mosquito x3`. `last_night_text` one `scratch_burst`, `morning_label: not_mosquito`. `yesterday_filter=none`. `morning_label=not_mosquito` | exactly one untimed line: `ignore motion scratch_burst` or `downweight motion scratch_burst` | inventing a timed line with no clock habit |
| M5 | `habit_text=none`. Last night only one `scratch_burst` / `sat_up`, `morning_label: none`. `yesterday_filter=none`. `morning_label=none` | `filter_text=none` | a rule from one night |
| M6 | habit is only `~02:00 outcome_15min=left_bed x3`, no `motion_counts:`; last-night card is sigh→left_bed | `filter_text=none` | one card filling a missing three-night cluster |
| M7 | `habit_text` has only outcome, no `motion_counts:`; `last_night_text=none` | `filter_text=none` | inventing a motion from the outcome |
| M8 | `~23:55 outcome_15min=left_bed x3 \| motion_counts: sigh_shift x3`, last night same motion, feedback none | one legal timed `ignore ... sigh_shift` that crosses midnight or contains 23:55; ≤90 minutes; not a bare rule | midnight + clock→timed shape |
| M9 | `~02:00 outcome_15min=left_bed x4 \| motion_counts: curl x1, sigh_shift x3`, last night sigh→leave, feedback none | one timed `ignore ... sigh_shift` that contains 02:00 and is ≤90 minutes; no rule for curl; not a bare rule | mixed cluster uses per-motion counts |
| M10 | no morning habit; last night one scratch card, `morning_label:unsure`, this call `morning_label=unsure` | `none` if yesterday is none; if a legal yesterday rule is in the input, only keep it; no new timed or bare rule | unsure is not a no |
| M11 | M1 habit; `yesterday_filter=downweight ~01:55-02:15 motion sigh_shift`; this feedback none | return yesterday’s `downweight ~01:55-02:15 motion sigh_shift` verbatim | yesterday-policy stability; do not regenerate a legal line |
| M12 | any input above | at most 5 lines; each line only `ignore` or `downweight`; must contain literal `motion`; motion only the three triggers | old opcodes, missing words, non-trigger motions |

M1, M8, M9 use code-built `motion_counts:`. M6 and M7 stay so the model cannot finish a whole cluster from one card.

---

## Contract and adapter checks

These need no extra call. Assert them on every existing raw:

- Pass A raw has exactly 4 keys (`reasoning, belief_state, belief_p, mode`); Pass B exactly 3; morning exactly 3.
- None of the three raws has a fence, a nested object, an array, or extra prose.
- `reasoning`, `reason`, `brief`, `timeline` are one line; only `filter_text` may contain newlines.
- Record whether `project_to_contract` repaired anything. Raw fail + projected success is “product tolerated it, model contract failed,” not a model pass.
- Final must pass the parser. If a retry then fallback, report fallback. Do not score the conservative fallback as a Nano judgment.
