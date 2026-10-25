# NightGuard test plan

Rules come from `docs/design_spec.md` and `docs/json_contract.md`. This file only orders tests and assertions.

Order: **modules (no story, no live model) → scenes (modules in sequence) → state cross.**

Defaults (also in the design spec):

- If several filter lines hit, use the first line in `filter_text`.
- Pass B names the lamp under review and the four verdicts. `reason` must name `outcome_15min` and `later_posture` or `later_motion_type`. No mosquito audio. `left_bed` after a lamp-on is not fixed.
- The nightly 6 counts Pass A, Pass B, and their retries. Morning is extra.
- `morning_label: not_mosquito` turns the Pass A lamp off. `downweight` still runs Pass A and only caps `belief_p`. Do not swap the tiers.
- Three traps (`design_spec` §4.10): **S4** before other scheduler cases; filters use regex + `clock_arc_min`, not `split()`; `json.loads` must be followed by `sanitize_pass_a` (**P5**).
- The watch window has three phases. One upgrade, only `off→on`. Transitions in §0.1. No `on→off→on`.

---

## 0. Two state layers

Pass A hidden states (4): `quiet | possible_harassment | routine_wake | general_discomfort`  
Pass B outcomes (5): `settled_lie | sat_up | left_bed | scratch_again_after_5m | no_new_event`  
The cross is 4×5 = 20 cells, section 3. Module tests do not replace those 20 cells with a handful of stories.

### 0.1 Watch-window phases (every arrow)

This is not the 4×5 table. 4×5 is Pass A belief × Pass B outcome. This is **how the lamp changes in one window**:

| Phase | Name | Window | Lamp so far |
| --- | --- | --- | --- |
| 1 | first judgment | open | only Pass A (often `off`, may already be `on`) |
| 2 | upgrade | open | after first `off`, code added one `on` / `assist_search` |
| 3 | closed | closed | Pass B wrote a card. Done |

Only these arrows. Missing arrows (especially 2→2, 2→1, 3→2) fail if the code produces them.

```
          Pass A
            │
            ▼
         ┌─ phase 1 ─┐
         │           │
    should have     everything else:
    been on,        first judgment
    still lying     ends here
    scratch
         │           │
         ▼           ▼
      phase 2      phase 3
         │
         │  sit / leave / scratch again / 15 min
         ▼
      phase 3     (no second upgrade)
```

| ID | From | Trigger | To | Lamp / card | Assert |
| --- | --- | --- | --- | --- | --- |
| S9 | 1 (`first=off`) | 5 min in, still lying `scratch_burst` | **2** | upgrade `assist_search`; window stays open | Pass B=0; LLM count unchanged |
| S12 | 1 (`first=off`) | 15 min, no later scratch (second look: off was right) | **3** | no upgrade | `correction=none`, `light=off` |
| S17 | 1 (`first=off`) | `sit` / `leave_bed` before 5 min | **3** | no upgrade (person is up) | `correction=none`; `sat_up` / `left_bed` |
| S13 | 1 (`first=on`) | 5 min in, still lying scratch | **3** | no upgrade, skip phase 2 | `correction=none`, review the first |
| S14 | 1 (`first=on`) | 15 min settled (wrong-on also ends; do not turn off and watch) | **3** | no “off then watch again” | `correction=none`, `light=on` |
| L2 / S2 | 1 (`first=on`) | `sit` / `leave_bed` | **3** | no upgrade | no second Pass A |
| S10 | 2 | `sit` | **3** | review the second lamp | `first_light=off`, `correction=upgraded_on`, `light=on` |
| S15 | 2 | `leave_bed` | **3** | review the second lamp | same, `outcome_15min=left_bed` |
| S11 | 2 | another lying scratch ≥5 min later | **3** | **no second upgrade** | lamp fields stay as at upgrade |
| S16 | 2 | 15 min after the upgrade | **3** | review the second lamp | `correction=upgraded_on`; lamp unchanged |

Also assert:

- Phase 2 does not return to phase 1.
- Phase 2 does not add another lamp (no 2→2 `off→on`).
- After phase 3 this window is done; the next gated-through event is a new phase 1.
- Sit / leave from phase 1 or 2 go straight to phase 3 and never upgrade.

---

## 1. Modules

Each section uses fixtures. §1.7 RL / MB stay offline. R1–R3 / RM1 HTTP only when `NIGHTGUARD_REMOTE=1`.

### 1.1 Hard gates `gates`

Test this table only with the window closed.

| ID | Input | Assert |
| --- | --- | --- |
| G1 | 26°C, lying, `scratch_burst`, 0 calls | allow a new Pass A |
| G2 | `temp_c=8`, lying, `scratch_burst` | reject; `light=off`; reasoning contains `temp_c<=10`; no card |
| G3 | 26°C, `posture=sit`, `human_sound=slap` | reject; no pardon; `awake=true` |
| G4 | 26°C, `motion_type=leave_bed` | reject; reasoning contains `leave_bed` |
| G5 | 26°C, lying, `slow_roll` | reject; reasoning contains `not a trigger` |
| G6 | 26°C, lying, `scratch_burst`, already 6 calls | reject; reasoning contains `budget` |
| G7 | `curl` and `sigh_shift`, otherwise G1 | both allow |
| G8 | 26°C, `posture=lie_stable`, `motion_type=none` | reject; `light=off`; reasoning contains `settled lie`; no LLM |

G3 must keep “sitting and slapping does not open a new Pass A.”

### 1.2 Scheduler `scheduler`

No LLM. Assert window open/close and `outcome_15min`.

Rule 2 must compute `elapsed_min` first. Do not close on “any scratch” before “already 5 minutes.”

| ID | Sequence | Assert |
| --- | --- | --- |
| S4 | another lying `scratch_burst` 2 minutes after open | **window stays open**. `elapsed_min=2 < 5`, not `scratch_again_after_5m`, no close |
| S4b | S4 then wait to 15 minutes | `settled_lie`, not `scratch_again_after_5m` |
| S5b | a 6-minute lying scratch left in `follow_events`, then 15 minutes | `scratch_again_after_5m`. The main loop normally handles minute 6; this locks the timeout branch |
| S1 | window closed, a gated-through `scratch_burst` | open the window; this beat is not Pass B |
| S2 | `posture=sit` 1 minute after open, no slap | close now; `outcome_15min=sat_up`; no new Pass A |
| S3 | `leave_bed` 1 minute after open | close now; `outcome_15min=left_bed` |
| S5 | another lying `scratch_burst` 6 minutes after open | scheduler marks `confirm_harass` / `scratch_again_after_5m`, **does not close itself**. Close is the loop looking at the first lamp (S9 / S13) |
| S6 | 15 minutes, `follow_events` empty | `no_new_event` |
| S7 | 15 minutes, only `slow_roll` | `settled_lie` |
| S8 | `sit` while the window is open | that event enters `follow_events`; it does not take the hard-gate “reject new open” |
| S9 | first `light=off`, still lying `scratch_burst` at 6 minutes | window stays open; one `assist_search`; Pass B count 0; LLM count unchanged |
| S10 | S9 then sit | close, Pass B; card `first_light=off`, `correction=upgraded_on`, `light=on` |
| S11 | S9 then another lying scratch 6 minutes later | close; `outcome_15min=scratch_again_after_5m`; no second lamp |
| S12 | first `light=off`, 15 minutes, no later scratch | no upgrade; Pass B; `correction=none` |
| S13 | first `light=on`, still lying scratch at 6 minutes | close, Pass B, `scratch_again_after_5m`; no upgrade, no third round |
| S14 | first `light=on`, 15 minutes settled | close; `correction=none`; `light=on`. Do not turn the lamp off and open another window |
| S15 | S9 then `leave_bed` | close; `left_bed`; card `correction=upgraded_on`, `light=on` |
| S16 | S9 then 15 minutes from the upgrade beat | close, Pass B; `correction=upgraded_on`; lamp unchanged |
| S17 | first `light=off`, `sit` 1 minute later | close `sat_up`; no upgrade; `correction=none` |

### 1.3 Memory `memory`

| ID | Input | Assert |
| --- | --- | --- |
| M1 | 6 cards `weight=1.0`, nights n1 < n2 < n3 | `memory_text` has only the latest 5; contains `outcome_15min:`; no `weight` |
| M2 | 3 `inconclusive` with `morning_label=none` | `uncertain_count=3`; those 3 are not card lines |
| M3 | clocks 01:55, 02:00, 02:15, all `left_bed` | one `habit: ~02:00 outcome_15min=left_bed x3` with `motion_counts:`. Distance must use `clock_arc_min`, not string sort |
| M9 | clocks 23:40, 23:55, 00:10, all `left_bed` | one midnight-crossing habit (center about 23:55); all three inside ±30 minutes. `if t2 < t1` as a break fails |
| M4 | current event 04:00, habit center 02:00 | this `memory_text` does not include that clock habit |
| M5 | current event 02:10, same habit | includes that habit |
| M6 | same `scratch_burst` and `morning=not_mosquito` on 3 cards | `habit: scratch_burst morning not_mosquito x3`; no disease words |
| M7 | a hard-gated event | no new card |
| M8 | card `inconclusive`, morning label becomes `mosquito` | `weight` becomes 1.0 |

### 1.4 Filter lines

Grammar is only `ignore` / `downweight`. Parse with §4.9 regex + `clock_arc_min`, not `split()`.

| ID | Input | Assert |
| --- | --- | --- |
| F1 | `ignore ~01:55-02:15 motion sigh_shift`, overlapping `left_bed` cluster that contains `sigh_shift` | accept |
| F11 | legal line with extra spaces | accept (collapse whitespace, then `fullmatch`) |
| F12 | `ignore ~23:30-00:30 motion sigh_shift`, midnight cluster that contains `sigh_shift` | accept. Length 60, not negative, not 1380 |
| F13 | `ignore ~02:15-01:55 motion sigh_shift`, same cluster as F1 | accept, same 20-minute band as `01:55-02:15` |
| F14 | `ignore ~01:55-02:15, motion sigh_shift` (extra comma) | drop the line |
| F15 | `ignore ~22:00-00:30 motion sigh_shift` | drop: shortest arc 150 > 90 |
| F2 | same clock written as `scratch_burst`, cluster never had it | drop the line |
| F3 | band longer than 90 minutes | drop the line |
| F4 | unknown verb `suppress` | drop the line |
| F5 | three lines, only the middle one legal | keep only the middle |
| F6 | all illegal, yesterday already had a filter | keep yesterday |
| F7 | first line `ignore`, second `downweight`, event hits both | this beat runs only the first `ignore`: no new Pass A |
| F8 | only `downweight` hits | still a new Pass A; `active_filter` is that line; after parse `belief_p<=0.3` and `mode!=assist_search` |
| F9 | a removed third opcode | parse rejects; archive and `memory_text` unchanged |
| F10 | `ignore motion scratch_burst` without a `not_mosquito` habit | drop the line |

### 1.5 Parse and code overwrite

A successful `json.loads` is not enough to return. Pass A must run `sanitize_pass_a(event, parsed)`; Pass B must run the deterministic contract overwrite.

| ID | Input | Assert |
| --- | --- | --- |
| P1 | flat Pass A JSON, legal enums | accept |
| P2 | nested `action` object | fail; retry once; then lamp-off fallback and `llm_parse_failed` |
| P3 | model writes `aim=floor_right`, `body_zone=left_calf` | code rewrites `floor_left` |
| P4 | `light=off` but `duration_s=4` | code sets `mode=none`, `brightness=none`, `duration_s=0`, `aim=none` |
| P5 | `posture=lie_stable` but model `awake=true` | code sets `awake=false`. Handing the model field to the loop is a fail |
| P6 | `outcome_15min=no_new_event` but model `verdict=appropriate` | code sets `verdict=inconclusive` |

### 1.6 Main loop (fake LLM)

The fake model returns fixed legal JSON. Assert call counts and cards, not clever wording.

| ID | Sequence | Assert |
| --- | --- | --- |
| L1 | one warm `scratch_burst`, 15 minutes, no follow-up | 1 Pass A + 1 Pass B; card `outcome_15min=no_new_event` |
| L2 | `sit` 1 minute after open | Pass B input is `sat_up`; no second Pass A |
| L3 | three “Pass A + immediate sit → Pass B”, then a scratch that should trigger | the 4th Pass A is budget-blocked (3×2=6). Do not write “seven Pass A in a row”: a scratch while the window is open only enters `follow_events` |
| L4 | indoor 8°C scratch | LLM calls = 0 |
| L5 | phase 1 `off` → phase 2 upgrade → phase 3 sit | LLM is still 1 Pass A + 1 Pass B; the upgrade is not in the budget |

### 1.7 Live model (local twins, then remote)

Default `pytest` is **offline**. The same payloads live in `tests/cases.py`.  
Remote: `NIGHTGUARD_REMOTE=1 pytest tests/test_remote.py -m remote` (at most 3 HTTP: Pass A, Pass B, morning). Local iteration may use Gemini. Submission proof is still Nemotron. Changing models changes `LLM_PROVIDER` / keys / model name, not a second client.

| ID | Layer | Assert |
| --- | --- | --- |
| RL1 | local FakeLLM | same Pass A input as R1, parses, no forbidden keys |
| RL2 | local FakeLLM | same `no_new_event` as R2, `verdict=inconclusive` |
| RL3 | local FakeLLM | no `peak_hz`, coordinates, `n_mosquitoes` |
| MB1–MB7 | local FakeLLM | morning JSON, reject if window open, not in night budget, once per night, accepted line goes live, 07:00 closes then briefs |
| A1 | local | `project_to_contract` strips fences and extra keys, keeps contract keys |
| A2 | local | both `gemini` and `nemotron` wires `encode`; contract few-shot is the same. No HTTP |
| A3 | local | error text has no API key |
| A6 | local | fake HTTP 500 and a dead network. 500 becomes a key-free `RuntimeError`; dead network stays `URLError`. No real vendor |
| H1 | local HTTP | dead network: `/play` returns 502 `llm_failed`; that response and the next `/session` have no key; window did not open |
| R1 | remote Gemini | same Pass A input, parseable flat JSON |
| R2 | remote Gemini | `no_new_event` → `verdict=inconclusive` (the only pinned verdict on a live model) |
| R3 | remote Gemini | no `peak_hz`, coordinates, `n_mosquitoes` |
| RM1 | remote Gemini | morning output has `brief` / `filter_text`; three calls including retry total ≤ 6 |

### 1.8 Morning filter update (memory × yesterday’s rules)

No new product rules. Assert `design_spec` §4.9: morning is sent `habit_text` / `last_night_text` / `yesterday_filter` / `morning_label`; illegal lines drop; if none remain, keep yesterday; the model copies yesterday then edits; code does not merge yesterday’s lines into a new draft.

The fake model emits scripted JSON. These tests check **that the payload carries current rules** and **that the night follows the accepted draft**.

| ID | Memory / yesterday | Model writes | Assert |
| --- | --- | --- | --- |
| U0 | water cluster; `yesterday_filter` already a legal `ignore` | default copy of yesterday | `run_morning_brief` payload has the four keys; `yesterday_filter` equals the line before the run; `habit_text` contains `habit:` |
| U1 | no cards, yesterday `none` | `none` | live stays `none` |
| U2 | no new cluster, yesterday already a legal `ignore` | copy yesterday | live stays that line |
| U3 | water cluster, yesterday `none` | `ignore ~01:55-02:15 motion sigh_shift` | accept; next night that clock `sigh_shift` is not Pass A |
| U4 | same cluster as U3, yesterday already that `ignore` | copy that line again | still one line; no motion the cluster never had |
| U5 | same cluster as U3, yesterday already a legal `ignore` | illegal line (comma / unknown verb) | keep yesterday |
| U6 | same cluster as U3, yesterday already `ignore` | yesterday’s line + a same-band `downweight` | both lines kept; that clock `sigh_shift` still follows the first `ignore` |
| U7 | three `scratch_burst` + `morning_label: not_mosquito` | `ignore motion scratch_burst` | payload `morning_label=not_mosquito`; bare line accepted |

---

## 2. Scenes

After modules 1.1–1.6. Each scene is an event sequence, not an isolated JSON.

| ID | Sequence | What to see |
| --- | --- | --- |
| C1 first-night scratch | n1 02:15 warm `scratch_burst`, no memory; +12 min sit-slap | Pass A happens; Pass B outcome `sat_up`; one card |
| C2 morning label | C1 card was `inconclusive` or already had a verdict; morning tap `mosquito` | that card `weight=1.0`, `morning_label=mosquito` |
| C3 water habit | three nights about 01:55 / 02:00 / 02:15 `sigh_shift` → `left_bed` | one clock habit; night-four 02:10 `sigh_shift` can see it |
| C4 personal filter | morning model writes `ignore ~01:55-02:15 motion sigh_shift` and it is accepted | next night that clock `sigh_shift` does not call Pass A; same night 02:10 `scratch_burst` still does |
| C5 cold night | indoor 8°C, motion like C1 | 0 calls, no new card |
| C6 habitual motion, not a disease | three nights `scratch_burst` + morning `not_mosquito` | habit line exists; next night same motion Pass A `memory_text` contains `not_mosquito`; no disease words |
| C7 three-phase chain | first `off`; +6 min still lying scratch; then sit | 1→2→3. Card: `first_light=off`, `correction=upgraded_on`, `light=on`, `outcome_15min: sat_up`. `memory_text` contains `first_light:` and `correction:` |
| C8 full rule update | C3’s three water nights, then one morning brief (fake model writes the U3 line) | payload has `habit_text` and `yesterday_filter`; night-four 02:10 `sigh_shift` is not Pass A; same night `scratch_burst` still is |

Scenes do not assert mosquito counts or coordinates. C4 may call `accept_morning_filter` directly. C8 must go through `run_morning_brief`.

---

## 3. State cross (20 cells)

Columns are scheduler outcomes. Rows are the `belief_state` Pass A wrote.  
**Code gate:** all 20 cells pack into a legal Pass B input (complete fields, legal enums). These 20 do not call a model.  
**Model gate:** only the `no_new_event` column requires `verdict=inconclusive`. Other cells record model output and are not a module pass/fail.

| belief \\ outcome | settled_lie | sat_up | left_bed | scratch_again_after_5m | no_new_event |
| --- | --- | --- | --- | --- | --- |
| quiet | legal input | legal input | legal input | legal input | verdict=inconclusive |
| possible_harassment | legal input | legal input | legal input | legal input | verdict=inconclusive |
| routine_wake | legal input | legal input | legal input | legal input | verdict=inconclusive |
| general_discomfort | legal input | legal input | legal input | legal input | verdict=inconclusive |

Build: take the five outcomes from S2/S3/S5/S6/S7, then set `pending_pass_a.belief_state` to each of the four values. Outcome does not follow belief; belief is only the judgment written into the Pass B input.

The three-pane page and `UiSession` edges / fixtures are `docs/ui_testplan.md`. That file does not replace the modules and scenes above.

---

## 4. Out of scope

- Scoring free-text `reason` on the 20 cells as a pass condition
- Calling Token Factory from module tests
- Treating any JSON in this file as the contract; the contract is only `docs/json_contract.md`
