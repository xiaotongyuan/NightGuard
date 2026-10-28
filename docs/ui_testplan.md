# NightGuard page tests

Specs: `docs/ui_spec.md`, `docs/ui_interface.md`. Product rules stay in `design_spec` / `json_contract`.  
This file only asserts **UI sessions**. It does not replace `docs/testplan.md` modules / scenes / 20 cells.

Default pytest: **no browser, no HTTP to Gemini**. Test `UiSession` the same way `NightLoop` is tested. Browser clicks, if added later, mark `web`.

Order: snapshot shape → enabled edges → watch-window matrix with fixtures → filter update draft → room does not leak the hidden variable.

---

## 0. Relation to existing IDs

Right/wrong edges are already in testplan §0.1 / S4 / S9–S17. Page tests only assert: **the same `choice_id` sequence produces a snapshot whose `phase` / `enabled_choices` / `last_step.kind` match those IDs.**

| Page ID | Product ID | Fixture |
| --- | --- | --- |
| W4 | S4 | `pass_a_fixture=off`, `follow.scratch.plus2` |
| W5 | S9 | `off`, `follow.scratch.plus6` |
| W6 | S10 | W5 then `follow.sit.plus1` |
| W7 | S11 | W5 then another `follow.scratch.plus6` |
| W8 | S12 | `off`, `follow.wait15` |
| W9 | S13 | `on`, `follow.scratch.plus6` |
| W10 | S14 | `on`, `follow.wait15` |
| W11 | S15 | W5 then `follow.leave.plus1` |
| W12 | S16 | W5 then `follow.wait15` |
| W13 | S17 | `off`, `follow.sit.plus1` (before 5 min) |
| W14 | L2 / S2 | `on` after open, then `follow.sit.plus1` |

Filter drafts are already U0–U7 / F1–F15 / C8. The page only walks `/morning` and snapshot `memory.filter_text` / `rules.soft_diff`.

---

## 1. Snapshot and edges (no story)

| ID | Action | Assert |
| --- | --- | --- |
| W1 | new session | `phase=closed`; `enabled` has every `open.*`; no `follow.*`; `action.light=off`; `llm.input` is `null` |
| W2 | `inspect` + `open.scratch.left_calf` + fixture `off` | `last_step.kind=pass_a`; `llm_called=true`; `phase=watch`; no `open.*` enabled; all five `follow.*` enabled |
| W3 | same but `temp_c=8` | `kind=gated`; `llm_called=false`; hard gate `temp` `hit=true`; `phase=closed`; still `open.*` |
| W15 | window open, `POST /play` an `open.*` | 409 `choice_disabled`; window still open |
| W16 | window closed, `POST /play` a `follow.*` | 409 `choice_disabled` |
| W17 | `inspect`, two `open.scratch.head` in a row | second `pass_a_count=1` (reset then open); the second snapshot is the source of truth |
| W18 | `continue`, two open-window moves (must close in between) | second `pass_a_count` accumulates; budget is not reset |

---

## 2. Watch-window matrix (FakeLLM fixtures)

Each starts from a new session, warm room, `open.scratch.left_calf`. Only the fixture and follow-up change.

| ID | Fixture | Follow-up | Snapshot |
| --- | --- | --- | --- |
| W4 | `off` | `plus2` | `phase=watch`; `kind=follow`; `llm_called=false`; `follow.*` still enabled (including `plus2` / `plus6`) |
| W5 | `off` | `plus6` | `phase=upgraded`; `kind=upgrade`; `action.light=on`; `llm_called=false`; `correction=upgraded_on`; `follow.*` still enabled |
| W6 | `off` | `plus6` → `sit` | `phase=closed`; `kind=pass_b`; card `correction=upgraded_on`; enabled back to `open.*`; all `follow.*` disabled |
| W7 | `off` | `plus6` → `plus6` | `phase=closed`; `kind=pass_b`; `action.aim` same as at upgrade (lamp unchanged); `follow.*` disabled |
| W8 | `off` | `wait15` | `phase=closed`; `kind=pass_b`; `correction=none`; `action.light=off` |
| W9 | `on` | `plus6` | `phase=closed`; `kind=pass_b`; **no** `upgrade`; never `upgraded` |
| W10 | `on` | `wait15` | `phase=closed`; `correction=none`; `light=on` |
| W11 | `off` | `plus6` → `leave` | `phase=closed`; `pass_b`; `upgraded_on` |
| W12 | `off` | `plus6` → `wait15` | `phase=closed`; `upgraded_on`; lamp unchanged |
| W13 | `off` | `sit` (immediately after first) | `phase=closed`; `correction=none`; no upgrade |
| W14 | `on` | `sit` | `phase=closed`; no second Pass A (`pass_a_count` still 1) |

W4 must not drop `plus2` from enabled.

---

## 3. Filter update (the page is one more snapshot layer)

Memory fixtures match the U table (three water cards, or three `not_mosquito`). Walk `/morning`. The page does not accept.

| ID | Maps to | Assert (snapshot) |
| --- | --- | --- |
| WF0 | U0 | before `POST /morning`, if the outbound input is readable: has `habit_text` / `yesterday_filter`. After the brief `llm.input` has all four keys |
| WF1 | U1 | no cards, yesterday `none` → `memory.filter_text=none`; all three `soft_diff` buckets empty |
| WF2 | U2 | no new cluster, yesterday already a legal ignore → same line; `kept` contains it |
| WF3 | U3 | script writes water `ignore` → that `soft` line; next same-clock `open.sigh.torso` is `filtered`, `llm_called=false` |
| WF5 | U5 | script illegal line → filter stays yesterday; `added` empty |
| WF6 | U6 | script “yesterday line + downweight” → two `soft` lines; `sigh` still `filtered` (first line ignore) |
| WF7 | U7 | three `not_mosquito`; script `ignore motion scratch_burst` → accept; `llm.input.morning_label=not_mosquito` |
| WF8 | (§4.9: no merge) | yesterday legal ignore; script **only** another still-legal `downweight` → filter is **only** the new line; yesterday’s line in `removed` |
| WF9 | MB3 | window open `/morning` → 409 `window_open`; `filter_text` unchanged; `night_id` unchanged |
| WF10 | night advance | successful `/morning` advances `night_id`; cards and filter stay; `last_step.kind=morning`; night budget zeros |
| WF11 | stamp + advance | `/morning` with `not_mosquito`: stamp the night just ended, then advance |
| W20 | Mode | `/next-night` does not run morning; cards and filter stay; `last_step.kind=none` |
| W21 | 5 cards | 6 high-weight + 1 inconclusive: `memory.cards` is only the latest 5 high-weight; `uncertain_count=1` |

WF4 is unused so it cannot drift from U4. U4 “copy the same ignore again” is covered by WF2.

---

## 4. Room and leaks

| ID | Action | Assert |
| --- | --- | --- |
| WR1 | `/ui` sets `mosquito_draw=head`, then `open.scratch.left_calf` | snapshot / `llm.input` / last Event have **no** `mosquito_draw`, `x`, `y`, `n_mosquitoes` |
| WR2 | fixture `on`, `open.scratch.head` | `action.aim=wall_head`; `light=on` |
| WR3 | fixture `off`, same | `aim=none`; none of the five faces should be marked on (snapshot is enough) |
| WR4 | `open.sit` (window closed) | `kind=gated`; hard gate `up` hit; person `posture=sit`; lamp off |

---

## 5. Long scenes (page session restates C)

All FakeLLM. `continue`. Do not assert clever copy. Assert window / card / filter / `night_id`.

| ID | Maps to | Clicks | Assert |
| --- | --- | --- | --- |
| WC1 | C1 | `scratch` → `sit` | `pass_a` then `pass_b`; card `outcome_15min: sat_up` |
| WC5 | C5 | room 8, `scratch` | `gated`; no card; `pass_a_count=0` |
| WC6 | C6 | three nights `scratch` → `wait15` → `not_mosquito` → next night; night four scratch again | Pass A `memory_text` contains `not_mosquito`; habit line present |
| WC7 | C7 | fixture `off`: `scratch` → `+6` → `sit` | card `first_light: off` / `correction: upgraded_on` / `outcome_15min: sat_up` |
| WC8 | C8 | three nights `sigh` → `leave` → next; after night three **unscripted** `morning` | FakeLLM writes the water `ignore`; advance to `n4`; same-clock `sigh` is `filtered`; `scratch` still `pass_a` |

## 6. Random clicks

| ID | Action | Assert |
| --- | --- | --- |
| WX1 | `continue` + fixture `off`; seeds 24/25/26, 80 steps each. Only tap `enabled_choices`; while closed, sometimes morning / next night / three keys | every step snapshot is legal: enums in the contract, edges match the window, cards ≤5, no forbidden keys, no `weight`. A grey choice is still 409 |

Oracles come only from FakeLLM and code gates. No network.

---

## 7. Shared room

One process, one room. Writes need `X-Operator-Token`. A second writer is `429 busy`. Idle 3 minutes releases the seat. Closing a tab does not. HTTP cases: `H2`–`H6` in `docs/testplan.md` / `tests/test_ui_http.py`.

---

## 8. Guided example

Page chrome. `example` on the snapshot is the only source. The front end does not invent the next highlight.

| ID | Action | Assert |
| --- | --- | --- |
| E0 | new session | `example.state=idle`; Start button; no highlight |
| E1 | `start_example` | `guiding`; Next: sigh shift; highlight `open.sigh.torso` |
| E2 | the 11 scripted clicks (HTTP same as the page) | each cue matches the next script beat; night 4 sigh is `filtered` and scratch stays enabled; last scratch → `finished`; no highlight |
| E3 | more clicks after finished | state stays `finished`; room still records the extra move |
| E4 | first click is scratch | `left`; no highlight; room still plays |
| E5 | `start_example` after left | new room; `guiding` from step 0; leftover `llm.remote` is hidden |
| E6 | label or temp while guiding | still `guiding` |
| E7 | reset / early next night / early morning | `left` |
| E8 | wait 15 or a second sigh on night 1 | `left` |
| E9 | next night instead of morning | `left`; filter still `none` |
| E12 | HTTP start, GET poll, then `/session` without the flag | poll does not advance the step; replacement session is `left` |
| E13 | scripted morning returns `downweight` for the water clock | accepted filter is still `ignore ~01:55-02:15 motion sigh_shift`; night 4 sigh is `filtered`; scratch stays enabled |
| E14 | HTTP with a Nano-shaped morning (`downweight ~02:00-03:00` + leftover `last_remote`) | same night-4 contract as E2; Restart hides `llm.remote` |
| E15 | live Token Factory morning (`NIGHTGUARD_NEMOTRON=1`) | same pin and scratch-enabled contract; default pytest skips |

Restart is `POST /session` with `start_example: true`.

---

## 9. Out of scope

- Replacing §2 `UiSession` tests with browser clicks
- Default pytest opening the page to hit Gemini
- Calling Token Factory from UI tests
- Expecting the page to “find where the mosquito is”
- Letting the front end compute `enabled_choices` and then checking the server (the server is the only source)
