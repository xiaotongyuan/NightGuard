# NightGuard local page

This file is **how the page is drawn and clicked**. Product rules stay in `docs/design_spec.md`. Model keys stay in `docs/json_contract.md`. Python routes are `docs/ui_interface.md`. Page tests are `docs/ui_testplan.md`.

Open: `python -m nightguard.ui_server` → `http://127.0.0.1:8765/`. Default **FakeLLM**. Default pytest does not start this server.

---

## 1. Three panes, in loop order

Left to right = **input → system → room (conclusion)**.

```
┌─────────────┬─────────────┬─────────────┐
│ Input       │ System      │ Room        │
│ dropdowns   │ LLM / rules │ line art    │
│ next moves  │ / memory    │ + lamp      │
└─────────────┴─────────────┴─────────────┘
```

Three columns stay three columns on a narrow screen (horizontal scroll). Do not stack. A demo has to show cause and effect in one glance.

| Pane | Is not |
| --- | --- |
| Input | A wall clock. Time lives in the next-move `dt_min` |
| System | An editor for hard gates. Hard gates are display-only. Soft lines are accepted `filter_text` |
| Room | Model output. No mosquito. **Do not** write a location into Event / Prompt |

---

## 2. Input pane

Top: mode. Middle: this-beat controls. Bottom: next-move list (scheduler edges).

### 2.1 Mode

| Value | Behavior |
| --- | --- |
| `inspect` | Every **open-window** move first `reset`s to “window closed, lamp off, tonight’s counts zero”. Cards and `filter_text` stay for the session. Used for the edge matrix |
| `continue` (page default) | No auto reset. Window, lamp, budget, and memory accumulate. Used for the demo |

Buttons (all through the interface; the front end does not mutate NightLoop):

- `reset_night`: close window, lamp off, tonight’s LLM count zero. Cards and filter stay
- `next_night`: next `night_id`, same as a loop night advance. Also in the Time dropdown. Cards and filter stay
- `morning`: window must be closed; run the morning brief (changes filter). Success auto-advances the night (same `_advance_night`). Cards and filter stay. The LLM pane still shows this morning JSON
- Three labels: `mosquito` / `not_mosquito` / `unsure`. Stamp before Update; Update sends this `morning_label` onto the night just ended, then advances

### 2.2 This-beat controls (only while the window is closed)

| Control | Enum | Into Event? |
| --- | --- | --- |
| Room temperature | `26` (warm) / `8` (cold, `temp_c<=10`) | yes, `temp_c` |
| Open-window move | §2.4 | yes, `motion_type` + `body_zone` + `posture` |
| Mosquito position | The page does not draw it and does not take it as input. The insect stays hidden | no |

The model only sees a human Event.

### 2.3 Next move = watch-window edges

The page has **no** standalone `+5 min` button. Time is in the choice id.  
Enabled / disabled is server `enabled_choices`. The front end must not guess.

| Current window | Enabled |
| --- | --- |
| Closed (never opened, or already closed) | only open-window moves (§2.4). Follow-ups all disabled |
| Phase 1 first judgment | follow-ups (§2.5). Open-window moves disabled |
| Phase 2 upgrade | still follow-ups; “scratch again +6 min” closes, it does not add a second lamp |
| After sit / leave / wait 15 min | window closed, follow-ups off, open-window moves on again |

Whether “scratch again” stays enabled after one tap follows `design_spec` §4.2 / testplan S4, S9, S11, S13. The front end only renders `enabled_choices`.

### 2.4 Open-window moves (window closed)

Each is one `POST /play`. The server advances `t` on tonight’s clock.

| choice_id | Label | Event |
| --- | --- | --- |
| `open.scratch.head` | scratch head | `scratch_burst` + `head` + `lie_stable` |
| `open.scratch.left_calf` | scratch left calf | `scratch_burst` + `left_calf` |
| `open.scratch.right_calf` | scratch right calf | `scratch_burst` + `right_calf` |
| `open.scratch.left_foot` | rub left foot | `scratch_burst` + `left_foot` |
| `open.scratch.right_foot` | rub right foot | `scratch_burst` + `right_foot` |
| `open.curl.torso` | curl | `curl` + `torso` |
| `open.sigh.torso` | sigh shift | `sigh_shift` + `torso` |
| `open.slow.torso` | slow roll (not a trigger) | `slow_roll` + `torso` |
| `open.lie` | lie down | `none` + `lie_stable`. Window closed: code turns the lamp off, no LLM |
| `open.sit` | sit (gate rejects a new open) | `sit_up` + `sit` |
| `open.leave` | leave bed (gate rejects a new open) | `leave_bed` + `off_bed` |

Warm room + a trigger may Pass A. Cold / sit / leave / `slow_roll` stay clickable; the System pane lights the matching hard gate.

### 2.5 Follow-up moves (window open)

The same `body_zone` as the opening beat. No second picker.

| choice_id | Label | Server |
| --- | --- | --- |
| `follow.scratch.plus2` | scratch same place (+2 min) | same-zone `scratch_burst`, `t+2` |
| `follow.scratch.plus6` | scratch same place (+6 min) | same, `t+6` |
| `follow.sit.plus1` | sit (+1 min) | `sit`, `t+1` |
| `follow.leave.plus1` | leave bed (+1 min) | `leave_bed`, `t+1` |
| `follow.wait15` | wait 15 min, no new move | **no** `on_event`; `advance_clock(t+15)` |

---

## 3. System pane (top / middle / bottom)

### 3.1 Top: LLM

Lit only when this beat `llm_called=true` (Pass A or Pass B or morning). Hard gate / `ignore` / code upgrade **do not** light it.  
When `last_step.kind=filtered`, “What happened” is `personal rule matched — model not called`, the top pane says `personal rule · model not called`, and the matching soft line stays `hit`.

When lit, two equal columns: left `input` (flat JSON sent), right `output` (flat JSON back). English keys, same as golden. No `peak_hz`, coordinates, or `n_mosquitoes`.  
Render: bold and mark `belief_state` and `reasoning` (Pass B: `verdict` and `reason`). CSS only. Do not change the JSON.

Upgrade: top pane stays dim but **still shows** the last Pass A JSON; the middle lamp fields light and mark `correction=upgraded_on` (code, not in the budget).

### 3.2 Middle: hard / soft rules

| Kind | Color (hex may change; meaning must not) | Content |
| --- | --- | --- |
| Hard gates | cool (blue-grey) | indoor `temp_c<=10`; sit/leave; non-trigger; nightly 6 |
| Soft lines | warm (ochre) | each accepted `filter_text` line, or `none` |

The line this beat hit gets `hit`. When `light=on`, draw a small lamp in the middle pane (same `aim` as the room; no extra state).

Hard gates are not editable. Soft lines change only through `morning` (then accept). Hand-editing a filter is out of this page.

### 3.3 Bottom: memory

Only lines code already rendered: at most 5 latest high-weight cards (`weight == 1.0`, `(night_id, t)` descending, same crop as the prompt) and `habit:` lines. The page lists every current habit; the Pass A prompt still hides a clock habit that is more than ±30 minutes from this beat. No `weight`. No disease words. The archive is not deleted.

`inconclusive` is a count, not a list.  
After close, `verdict` uses three backgrounds: `appropriate` / `too_weak` / `inconclusive` (`too_strong` gets a background too, no new meaning).

---

## 4. Room pane

Minimal SVG. No photos. No “how many mosquitoes.”

```
           wall_head
      +-----------------+
      |                 |
wall  |      O  person  |  wall
side  |      |          |  right
      |     [bed]       |
      |                 |
      +-----------------+
        floor_L   floor_R
```

| Element | Draw |
| --- | --- |
| Bed | A flat rectangle in the middle |
| Person | A circle + a line. `sit` shortens the line; `off_bed` moves the circle off the bed |
| Mosquito | Not drawn. The hidden variable does not appear in the room |
| Five faces | Light the face when `aim` is `floor_left` / `floor_right` / `wall_head` / `wall_side` / `wall_right`. `aim=none` or `light=off`: all dark |

`aim` still comes from the body-zone table. The page does not compute it.

Lamp hold: in `inspect`, until the next `play` / `reset`. In `continue`, until the next beat. A 1.2s CSS fade is allowed. **Do not** use the fade instead of `elapsed_min`.

---

## 5. FakeLLM and a live model

Default session: `FakeLLM`. The page has no First-lamp / fixture dropdown. The lamp judges see comes from the middle pane and the room. Window-matrix tests still pin Pass A through the interface `pass_a_fixture` (`off` / `on` / `assist`).

Update filter: tap `morning`. The request carries current `yesterday_filter` + memory. After accept, the System soft lines become the new text and mark **added / removed / kept** versus yesterday (UI highlight only; accept rules do not change).

Live Gemini: `python -m nightguard.ui_server --llm gemini --model gemini-3.5-flash-lite`. Default start is still FakeLLM. Not default pytest. Nemotron: `--llm nemotron`.

---

## 6. The page does not

- Invent a fourth watch-window phase
- Send mosquito position, coordinates, or counts to the model
- Reimplement gates / filter / `elapsed_min` in the browser
- Treat a canned click list as product rules. A demo sequence may cite testplan C1–C8. That list is not the nightly 6-call budget
