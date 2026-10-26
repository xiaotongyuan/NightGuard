# NightGuard design spec

The mosquito is a hidden variable. The human is the sensor. This file is the product: main loop, blocks, data, and rules.

JSON sent to or received from the model is defined only in `docs/json_contract.md`. Tests do not invent extra product rules.

---

## 0. Posture

This is a playable closed loop, not a hardware product. Stop at an honest POC. Do not add sensors, a reading mode, multi-user accounts, or one model stream per person.

| In | Out |
| --- | --- |
| Browser three panes: human events → gates / window / LLM → lamp and cards | Real mattress, real spots, mosquito audio |
| Night one may be wrong; after three nights the rules follow the person | “How many mosquitoes” |
| One Token Factory → Nemotron call on camera | Selling FakeLLM as live intelligence |
| Lie down, lights off, no hardware action | A reading lamp or a repeller |

Tone: geeky, minimal, technically dense. One dry joke. Judges should remember: *human is the sensor · mosquito stays hidden*. Night one can be messy. That is the design. Lie down to read and the lamp will betray you — it is not a reading light.

### 0.1 Why an LLM instead of a frozen table

What can be hardcoded already is: a cold room, a person already up, a 15-minute window, one lamp upgrade, two filter opcodes, and `aim` lookup. The 20-cell Pass B contract tests do not need a remote model. Runtime Pass B still lets the model review whether the intervention fit. Do not claim “Nemotron decides every lamp.”

What cannot be hardcoded is which stretch of history matters for *this* person, and how tomorrow should bother them less. The same `sigh_shift` may be water, a mosquito, or a roll. The same 2 a.m. pattern may deserve `ignore`, `downweight`, or another night of watching. The difference lives in recent outcomes, morning labels, and clock habits. Enumerating those personal mixes turns the product into a growing table that still does not know the sleeper.

So the split is not “the model replaces the state machine.” Code clusters, compresses, and guards invariants. The model reads a bounded, noisy, personal history and **proposes a personal policy**. Code accepts that proposal as at most five executable lines. The two-opcode grammar is not a substitute for reasoning. It compiles reasoning into a policy that can be audited, refused, and run for free the next night.

Morning is the clean beat: code will not decide “ignore the 2 a.m. water trip tomorrow”; the model may propose that inside the grammar. Night four then runs the accepted line with no model call. One fewer call is not a weaker LLM. It is proof that one judgment was distilled into a cheap personal rule.

**Code owns time and safety. Nemotron owns personal strategy.** The insect never appears and never enters the prompt. The spine is: **observe → judge once → see the outcome → compress memory → compile a personal rule → ask less next time.**

---

## 1. Main loop

```
human event
    → input log
    → if the watch window is still open
         always write follow_events (sit / leave do not open a new Pass A)
         then §4.2:
              keep waiting
              or (first light=off, 5 min in, still lying and scratching) code adds one lamp,
                  restarts the watch clock, window stays open. No LLM.
              or close the window and run Pass B (this LLM call counts toward the 6)
         Pass B writes a memory card. It does not open a new Pass A. At most one upgrade.
    → if the window is closed
         hard gates (§4.1)
         → accepted filter (§4.9; ignore → lamp off, no card, no LLM)
         → if the event is a trigger:
              compress memory (latest 5 cards + habit lines)
              → Pass A prompt → LLM (counts toward the 6)
              → code overwrites aim / awake / off-lamp fields
              → action is a no-op (record only)
              → open the watch window
```

Two jobs sit outside night events. They are not woken by a body event and not by a window timer:

1. **Three labels** (no LLM): the person taps `mosquito` / `not_mosquito` / `unsure`. That stamps `morning_label` and card `weight`.
2. **Morning brief** (one LLM): after the night ends, send habit lines, last night’s new cards, and yesterday’s `filter_text`. Receive `brief` / `timeline` / `filter_text`. This call is **not** part of the nightly 6.

Trigger (demo, fixed, not conversational):

- Not a wall cron, and not polled on every night beat.
- One brief per night. Both must hold: the replay has ended (or the UI tapped Morning), **and** the watch window is closed. If the window is still open, finish Pass B under §4.2 first.
- The page does not auto-fire at `07:00`. The operator taps **Update tomorrow's rules**. A loop helper may still close an open window at `07:00` before a brief; that is not a UI cron. Do not fire at 03:00 because “dawn is near.”
- The three labels may be tapped before or after the brief. Untapped stays `morning_label=none`.

**Review versus a new case is the scheduler’s job. Do not ask the LLM to choose.**

---

## 2. Blocks

| Block | Path | Job |
| --- | --- | --- |
| input log | `src/nightguard/log.py` | Append Event as golden flat JSON |
| gates | `src/nightguard/gates.py` | Block only “open a new Pass A”; skipped while the window is open |
| scheduler | `src/nightguard/scheduler.py` | This event is follow-up / close for Pass B / new Pass A. Compute `elapsed_min` first. Do not close on every scratch (trap 1 in §4.10) |
| memory | `src/nightguard/memory.py` | Persist cards; retrieve at most 5 `weight=1.0`; render `memory_text`; count `inconclusive`. Clock distance uses the same `clock_arc_min` as filters |
| Filter | `src/nightguard/filters.py` | Morning lines: regex accept, midnight shortest arc, first matching line. Do not parse with `split()` (trap 2) |
| Prompt | `src/nightguard/prompts.py` | Pass A / Pass B / morning templates. Changing models does not change this file |
| parse | `src/nightguard/llm.py` | FakeLLM, `invoke`, validate, one retry, rule fallback. After `json.loads` always `sanitize_pass_a` (trap 3) |
| remote | `src/nightguard/adapter.py` | One `RemoteLLM`. Gemini / Nemotron are wires (URL, headers, body). Few-shot, `project_to_contract`, retry, and key redaction are shared |
| results | memory / log | Record Pass A, Pass B, morning labels |
| action | `src/nightguard/action.py` | **Empty**: accept lamp JSON, drive no hardware |
| loop | `src/nightguard/loop.py` | Wire the above |
| schema | `src/nightguard/schema.py` | Enums and constants, aligned with the golden file |

The hard part is **how memory is packed into the prompt** and **how the two night prompts are written**, not the scene story.

---

## 3. Data structures

Flat, English, keys never dropped. Full fields and examples live in the golden file.

| Structure | Writer | Reader | Into the LLM |
| --- | --- | --- | --- |
| Event | simulator / replay | scheduler (window open), gates (window closed), log | no |
| Pass A input | memory + current Event + `active_filter` | LLM | **yes** |
| Pass A output | LLM or gate / fallback | scheduler, action, card | **yes (back)** |
| Pass B input | last Pass A + bodies in the window | LLM | **yes** |
| Pass B output | LLM | card | **yes (back)** |
| Memory card | our code | memory retrieval | no (rendered to a string first) |
| Morning label | UI three keys | card | no |
| Morning brief | LLM | UI + tomorrow’s filter | **yes**. Not in the nightly 6 |
| `active_filter` | code: first matching filter line this beat | Pass A | yes (string; `none` if miss) |

Hidden-state values (Pass A) are only four: `quiet | possible_harassment | routine_wake | general_discomfort`.
15-minute outcomes (Pass B) are only five: `settled_lie | sat_up | left_bed | scratch_again_after_5m | no_new_event`.
The 20-cell hard cross is a scene matrix, not a new loop structure.

Watch-window state (scheduler, **not** an LLM field):

```
pending_pass_a : last gated-through Pass A snapshot, or empty
correction     : in-window lamp upgrade snapshot, or empty (at most one)
already_corrected : bool
window_open_t  : window start (moved to the upgrade beat if one happened)
follow_events  : human events inside the window
llm_calls_tonight : int
```

`memory_text` is two parts. Neither writes `weight` or a diagnosis.

Latest cards (at most 5 lines):

```
{night_id} {HH:MM} | motion_type: {motion_type} ({body_zone}) | outcome_15min: {outcome_15min} | first_light: {first_light} | correction: {correction} | response_verdict: {verdict} | morning_label: {morning_label}
```

Habit lines (code aggregates all high-weight cards, not only these 5):

```
habit: ~02:00 outcome_15min=left_bed x4 | motion_counts: curl x1, sigh_shift x3 (±30min)
habit: scratch_burst morning not_mosquito x3
```

No cards and no habits: `none`. Otherwise join with `\n`. `later` makes a 2 a.m. get-up visible. `motion_counts:` is a code tally inside the cluster so the morning model does not guess the motion from the outcome.

---

## 4. Rules

### 4.1 Gates (only block “open a new Pass A”)

While the window is open **do not use this table**. Sit and leave first enter `follow_events`, then §4.2 closes for Pass B. Otherwise a 2 a.m. water trip is eaten by the gate and review never sees it.

While the window is closed, `temp_c` is **indoor**. Any hit: no LLM, lamp off, **no memory card**.

| Condition | reasoning |
| --- | --- |
| `temp_c <= 10` | `Gated: indoor temp_c<=10. No LLM.` |
| `posture` is `sit` or `off_bed` | `Gated: person already up. No LLM.` |
| `motion_type` is `leave_bed` | `Gated: leave_bed. No LLM.` |
| `posture` is `lie_stable` and `motion_type` is `none` | `Gated: settled lie. Lights off. No LLM.` |
| `motion_type` is not `scratch_burst` / `curl` / `sigh_shift` | `Gated: motion not a trigger. No LLM.` |
| Night LLM already 6 (Pass A, Pass B, and their retries only) | `Gated: night llm budget. No LLM.` |

**No pardon.** With no pending window, `sit` + `slap` does not open an assist lamp. The person is already up. Do not add noise.  
`slow_roll` does not open Pass A. Inside an open window it is only low-intensity review material.

### 4.2 Scheduler

Window open: later events only enter `follow_events`. They are **not** a new Pass A (sit is not pardoned into a new assist lamp).  
Window closed or no pending: a gated-through event opens a new Pass A.  
Speed is decided by later human events. After close, run **Pass B** (review the judgment made while they were still lying), not a new Pass A.

From `follow_events` to `outcome_15min`, **match the first rule only, in this order**. Each beat: compute time, then branch:

```
# Forward elapsed across midnight. Do not take the shortest arc. Window max 15 minutes.
elapsed_min = (minutes_from_midnight(event.t) - minutes_from_midnight(window_open_t)) % 1440
# Forbidden: if motion == scratch_burst: close   ← that closes a second scratch in the first 5 minutes
if rule 1 force-close:          close now
elif 5 <= elapsed_min < 15 and rule 2:  close as scratch_again_after_5m
elif elapsed_min >= 15:         natural timeout
else:                           window stays open (including a lying scratch_burst 2 minutes after open)
```

`clock_arc_min` (shortest arc) is only for memory clusters and filter bands. Do not use it as `elapsed_min`.

**1. Force close (0–15 min, close now)**

- `posture == sit` or `motion_type == leave_bed` or `posture == off_bed`.
- Map (no extra enum):
  - `leave_bed` or `off_bed` → `left_bed` (leaving the bed is the night-path; do not wait for them to return).
  - `sit` → `sat_up` (with or without `slap`; **do not** map a dry sit to `left_bed`).
- `later_*` take the event that fired this rule.

**2. Confirm harassment (requires `elapsed_min >= 5` and `< 15`)**

- The previous line’s `elapsed_min` must exist. If `elapsed_min < 5` this rule is false.
- Another `scratch_burst` in `follow_events` with `posture == lie_stable`.
- A second scratch in the first 5 minutes **does not close** (avoid counting one burst twice). That is S4.
- Map: `outcome_15min = scratch_again_after_5m`. The scheduler only marks `confirm_harass`. **It does not close here.** Close-or-upgrade is the lamp rule below.

**2b. In-window lamp upgrade (at most once, code, no LLM)**

One window allows one `off → on`. Never `on → off → on`.

```
first light=off and confirm_harass and not yet upgraded
    → code writes one assist_search (aim from this beat’s body_zone)
    → action records (UI lights now)
    → window_open_t = this beat, follow_events cleared
    → window stays open. No Pass B. Does not count toward the 6
first light=on and confirm_harass
    → a lamp already happened. Close, Pass B on the first lamp. Done
already upgraded once and confirm_harass / sit / leave / 15 min
    → close, Pass B on the upgraded lamp. Done. No second upgrade
first light=off and the person settles / no new event (second look says off was right)
    → close, Pass B on the first lamp. Done. No upgrade
first light=on and later proof it should not have been on (settled)
    → close, Pass B on the first lamp (it was on). Done. Do not “turn off and watch again”
sit / leave
    → person is up. Never upgrade. Close, Pass B
```

The card stores the chain: `first_light=off` → `correction=upgraded_on` → `verdict` (on the second lamp). No upgrade: `correction=none`, `light` equals the first.

**3. Natural timeout (15 min)**

- `follow_events` empty, or only `motion_type == none` → `no_new_event` (Pass B must be `inconclusive`; code overwrites after parse).
- Only low-intensity motion (`slow_roll` / `curl` / `sigh_shift`) and rules 1–2 missed → `settled_lie`.
- A `scratch_burst` in the first 5 minutes belongs to the opening cluster. Timeout does not promote it to `scratch_again_after_5m`. No new lying scratch after minute 5 → `settled_lie`.
- A lying `scratch_burst` after minute 5 still in `follow_events` at timeout → `scratch_again_after_5m`. The main loop normally handles `confirm_harass` on that beat.

### 4.3 Memory

Run **before every Pass A**. Do not call a second model to summarize. Do not write labels such as “skin disease.” Compress habitual motion and clock patterns (always scratching, or leave-and-return around 02:00). The demo has one sleeper and no `user_id`.

Cards are written after Pass B and carry `outcome_15min` (from the scheduler map, not a model-invented key). A gated-away new Pass A **writes no card**.

1. **Filter:** `weight == 1.0`. `inconclusive` with no morning label, or `morning_label == unsure` → `0.1`.
2. **Latest 5:** all high-weight cards by `(night_id, t)` descending, `[:5]`, rendered as card lines (including `later`).
3. **Habits** (scan all high-weight cards, not only these 5). A group needs `>= 3` to write a line. The LLM does not cluster and may not add gates.
   - Clock + outcome: convert `t` to minutes from midnight. Distance uses the shared `clock_arc_min`. For one `outcome_15min`, take the median, then keep points within 30 minutes of that median (1:55, 2:00, 2:15 is one cluster; 23:40 / 23:55 / 00:10 is one cluster; a single chain must not drag farther points in). Code then tallies motions: `habit: ~02:00 outcome_15min=left_bed x4 | motion_counts: curl x1, sigh_shift x3 (±30min)`.
   - **This line enters this prompt only if the current event also falls in that ±30 minutes.** A 4:00 scratch does not see the 2 a.m. habit.
   - Motion + morning label: only when the label is `mosquito` or `not_mosquito` → `habit: scratch_burst morning not_mosquito x3`. These lines ride every Pass A.
4. **Noise:** count of `weight == 0.1` cards → `uncertain_count`. Not written into the string.
5. No card lines and no habit lines: `memory_text = none`. Never write `weight`.

### 4.4 `aim`

Rule table. The LLM may only copy the enum. Light a neighboring **static background face**, never the body. `light=off` ⇒ `aim=none`.  
Five faces: `floor_left` / `floor_right` / `wall_head` / `wall_side` (left wall) / `wall_right` (right wall). Limbs → floor, head/neck/shoulder → headboard wall, torso → left wall. `wall_right` is in the enum; current `body_zone` values do not land on it. Sanitize still overwrites a model-chosen aim.

### 4.5 LLM parse and code overwrite

Pure JSON, no markdown fences. Fail → retry once (retry counts toward the 6). Fail again: rule fallback, lamp off. Do not regex-scrape. The snapshot marks `last_step.llm_parse_failed` (program state, not a model field).

`llm.py` must **not** `return json.loads(response)`. After a successful parse, `sanitize_pass_a(event, parsed)` must run before the loop sees it. A successful retry uses the same function.

`sanitize_pass_a` does not trust:

- `awake`: `event.posture == lie_stable` → `false`, else `true`. Rewrite if the model flipped it.
- `aim`: table from `body_zone`; `light=off` forces `none`.
- `light=off` ⇒ `mode=none`, `brightness=none`, `duration_s=0`, `aim=none`.
- A hit `downweight`: `belief_p = min(belief_p, 0.3)`, `mode` must not be `assist_search`.

`sanitize_pass_b` locks one deterministic contract: `outcome_15min=no_new_event` ⇒ `verdict=inconclusive`. Other outcomes stay with the model, looking back at the first judgment and later events.

### 4.6 Action

No hardware. The action block is a no-op: record the current lamp fields for the UI. Sources are only two: Pass A, or the one in-window code upgrade. An upgrade is not a new Pass A.

### 4.7 Forbidden

Mosquito audio / coordinates / counts / handing detection to the LLM / RL / sit-pardon / outdoor temperature as a hard gate.  
The LLM may not add or drop hard gates (temperature, sit, leave, trigger list, the 6-call budget). It may only write **agreed filter lines** in the morning brief. Code and model share one grammar. A smarter model uses more phrasings of those lines. It cannot invent the grammar.

### 4.8 Prompt reasoning (Pass A)

Do not copy test inputs or answers into the runtime prompt. All three prompts follow `TASK → INPUT SEMANTICS → STATE/FILTER/VERDICT SEMANTICS → DECISION POLICY AND PRECEDENCE → OUTPUT CONTRACT`. The only English runtime source is `src/nightguard/prompts.py`. This spec locks meaning so two copied prompts cannot drift. Holdouts and pass lines are in `docs/prompt_tests.md`.

Pass B does not reuse Pass A lamp rules. It reviews the lamp in `belief_state` / `belief_p` / `light` / `mode`. When `correction=upgraded_on` it reviews the second lamp, not `first_light`. The four verdicts are fit, opposite, too weak, not enough evidence. Lamp off then `left_bed` is fit. Lamp on then `left_bed` is not fixed. `reason` must name the outcome value and at least one later value.

- **This lamp.** `quiet` / `routine_wake` → off. Only `possible_harassment` may turn on. `general_discomfort` is only for `curl` with `uncertain_count >= 3`, lamp off.
- **No card of this motion.** `scratch_burst` → `possible_harassment`, on, `silent_confirm`. `sigh_shift` → `quiet`, off.
- **Get-up habit.** `outcome_15min=left_bed` covers only a motion whose own `motion_counts:` is at least 3. That motion stays `quiet` or `routine_wake`, `mode=none`, even if a card says `too_strong`. Do not drag another motion with it.
- **Hit filter.** If `active_filter` is not `none`, execute §4.9 as written. `downweight`: `belief_p` at most 0.3, no `assist_search`.
- **Morning no.** Same `motion_type` with `morning_label: not_mosquito` (card or habit): `light: off`, `belief_p` 0.35 or below. This beats an old `too_weak` and is harder than `downweight`. Do not merge the two. Do not write it as a skin disease.
- **Morning yes.** Same motion with `morning_label: mosquito`: `possible_harassment`, on, `belief_p` 0.5 or above. If `downweight` also hits, the 0.3 cap replaces 0.5, still no `assist_search`.
- **Upgrade.** Same motion with `response_verdict: too_weak`: do not emit `silent_confirm` again; if the lamp is on use `assist_search`. Do not upgrade tonight’s `curl` from an old scratch. Habit lines without a card of this motion do not use `assist_search`.
- **No memory.** `memory_text` is `none` ⇒ no `assist_search`.
- **Noise.** `uncertain_count >= 3` and the current motion is only `curl`: `quiet` or `general_discomfort`, `light: off`. `sigh_shift` and `scratch_burst` do not use `general_discomfort`.

Pass A raw is only `reasoning, belief_state, belief_p, mode`. Code derives `awake` from posture and lamp fields from mode: `none → off/none/0/none`, `silent_confirm → on/very_low/4/zone aim`, `assist_search → on/medium/6/zone aim`. Pass A inputs are a human event, rendered memory, a low-weight count, and a filter code already hit. Weather is not a hard gate. Motion is not mosquito detection. `belief_p` is the probability of continued harassment. `downweight` still caps 0.3 and turns `assist_search` into `silent_confirm`.

### 4.9 Morning filter: one grammar for code and LLM

The same morning call sends habit lines, last night’s new cards, yesterday’s live `filter_text`, and the morning label, and asks for **tomorrow night’s filter**. `ignore` skips later Pass A. `downweight` still runs Pass A with a cap.

Morning input (flat; golden in contract §8):

```
habit_text        habit lines, or none
last_night_text   last night’s new cards rendered, or none
yesterday_filter  yesterday’s live filter_text, or none
morning_label     three-key result, or none
```

The morning prompt must explain the four inputs, both opcodes, and the evidence bar, and lock new-rule shape from the evidence source first:

- Preserve first: if a legal `yesterday_filter` still matches a habit and `morning_label` is `none` or `unsure`, copy it verbatim. Do not rewrite opcode, window, or grammar. Ordinary last-night cards do not authorize a rewrite. Only a relevant explicit `mosquito` / `not_mosquito` or a newly qualifying other habit may change or add.
- `habit_text` has `~HH:MM` and the target motion appears at least 3 times in that line’s `motion_counts:`: new rule must be timed, never bare.
- A non-clock habit that literally says `motion morning not_mosquito x3`: new rule must be bare, never timed from last night’s card clock.
- Neither kind of habit: no new rule. Keep a still-legal `yesterday_filter` or write `none`.

Times in `last_night_text` are single-event times for the brief and timeline only. They cannot be a filter center or edge. A clock rule cannot guess motion from `left_bed`, and one last-night card cannot pretend to be a three-night habit. `mosquito` must not become ignore. With no new evidence, keep a legal yesterday rule.

Two sentences. One extra or missing word is a reject. The literal token `motion` must be present. One line each, at most 5 lines. Times are closed intervals, midnight by shortest arc, band at most 90 minutes. Near midnight the start may be later than the end, e.g. `~23:30-00:20`. Do not rewrite a clock habit as a bare rule because it crosses midnight. The same two legal forms sit in the system prompt and in a contract hint next to the input.

Parse with regex. Do not count spaces with `split()`. Morning models add spaces, commas, and reversed ends. Steps:

1. Strip edges. Collapse inner runs of whitespace to one space.
2. `fullmatch` the whole line. One extra mark rejects:

```
^(ignore|downweight) ~([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d) motion (scratch_burst|curl|sigh_shift)$
^(ignore|downweight) motion (scratch_burst|curl|sigh_shift)$
```

The second form has no time.
3. Convert both clock ends to minutes from midnight. Length = `clock_arc_min(a, b)` (`min(fwd, 1440-fwd)`). Drop `> 90` or `== 0`.
4. **Do not** write `if end < start: illegal`. That kills `23:30-00:30` (legal 60 minutes). Do not only “add a day to the end”: `02:15-01:55` clockwise is 23 hours; the shortest arc is 20 minutes, the same band as `01:55-02:15`. Reversed ends normalize to the shortest arc.
5. A clock is inside the band if its shortest arc to both ends is at most the band length and it sits on the shorter segment (closed).
6. `clock_arc_min` is shared with memory clustering. Do not write two copies.

```
ignore ~01:55-02:15 motion sigh_shift
downweight ~01:55-02:15 motion sigh_shift
```

| Form | Who writes it | What code does |
| --- | --- | --- |
| `ignore` | weaker model: skip this motion | no new Pass A, lamp off, no card |
| `downweight` | stronger model: the person is not in deep sleep, lower confidence | still Pass A, but `active_filter` is this line; the prompt caps `belief_p` at 0.3 and forbids `assist_search`. Code clamps again after parse |

Untimed forms are only `ignore motion <enum>` or `downweight motion <enum>`, and only when a same-motion `morning_label: not_mosquito` habit already exists.

Accept: a timed line’s band must overlap an existing clock cluster, and the motion must have appeared in that cluster. 1:55–2:15 water may become `sigh_shift`. It cannot become a `scratch_burst` that never appeared. Drop bad lines; keep the rest. If none remain, keep yesterday’s filter.

Next-night order: hard gates → accepted filter → maybe Pass A. Review inside an open window does not consult the filter.

If one event hits several lines, use the **first line in `filter_text`**. Later lines are ignored this beat.

Invariants:

1. **The nightly 6 does not include the morning brief.** Count Pass A, Pass B, and those retries. The morning `brief` / `timeline` / `filter_text` call is separate. It cannot block a spent night, and it does not spend tomorrow night’s 6.
2. **`morning_label: not_mosquito` and `downweight` are not the same tier.** The first is lamp off in Pass A. The second still runs Pass A with a 0.3 cap and no `assist_search`. Do not swap them in the prompt or in tests.
3. **One in-window upgrade, and only `off → on`.** If the first lamp was already on, or the person scratches again after an upgrade, close and Pass B. Do not change the lamp again. The upgrade is not an LLM call and not in the 6. Sit / leave never upgrade.
4. **One remote client.** `RemoteLLM.complete(kind, payload)` is the same for every vendor. `LLM_PROVIDER=gemini|nemotron` only swaps the wire. Contract keys, the two opcodes, and the user-side `messages()` JSON do not change with the model. Default pytest does not HTTP. `NIGHTGUARD_REMOTE=1` hits Gemini.

### 4.10 Implementation traps

These three places are easy to “simplify” wrongly. The spec above already states the rule. Tests lock it.

| # | Wrong | Right | Tests |
| --- | --- | --- | --- |
| 1 | `scheduler.py` closes on any `scratch_burst` | Forward `elapsed_min` first (`% 1440`, not shortest arc). Rule 2 only when `5 <= elapsed_min < 15`. A second scratch in the first 5 minutes keeps the window open | **S4** |
| 2 | filter via `split()`; `end < start` illegal | regex `fullmatch`; `clock_arc_min` for midnight and reversed ends. `23:30-00:30` is legal; `02:15-01:55` is the same 20-minute band as `01:55-02:15` | **M3, M9, F1, F11–F15** |
| 3 | `llm.py` returns `json.loads` | every successful parse goes through `sanitize_pass_a`: overwrite `awake` / `aim` / off-lamp fields / downweight clamp | **P3, P4, P5** |
| 4 | one `*LLM` class per vendor | one `RemoteLLM` + a wire table. Few-shot and `project_to_contract` sit above the wire | **A1, A2, A3** |

---

## 5. How tests follow the frame

Order is `docs/testplan.md`: modules, then scenes, then the 4×5 state cross. Scenes and the cross do not replace module tests. Live model calls wait until modules pass.

---

## 6. Documents

| File | Role |
| --- | --- |
| `docs/design_spec.md` | This file: loop, blocks, rules |
| `docs/json_contract.md` | **Golden** JSON allowed in and out of the LLM |
| `docs/testplan.md` | Modules → scenes → 20-cell cross |
| `docs/ui_spec.md` | Local three-pane page |
| `docs/ui_interface.md` | Page talks HTTP JSON to NightLoop only |
| `docs/ui_testplan.md` | UI session tests. Restates S4 / S9–S17 |
| `docs/prompt_tests.md` | Holdout prompts; not copied into runtime |
| `docs/deployment.md` | Local FakeLLM; hosted demo; Token Factory proof |
