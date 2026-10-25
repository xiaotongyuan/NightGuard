# NightGuard page ↔ Python

The page is a thin client. Gates, window, filter, memory, and sanitize run only inside `NightLoop`.  
This file is the HTTP JSON. Keys are English. Product enums are not added here.

Code: `src/nightguard/ui_session.py` (session + `enabled_choices`), `src/nightguard/ui_server.py` (local HTTP). Static files: `web/`.

Stack: **Python stdlib `http.server` + HTML / CSS / native `fetch` in `web/`.** No Java, no React / Vue, no Flask / FastAPI.

Default `127.0.0.1:8765`. Loopback only.

---

## 1. Session

One browser tab = one `UiSession` = one `NightLoop`.

| Item | Default |
| --- | --- |
| LLM | `FakeLLM` |
| Mode | `continue` (page and `POST /session`). `UiSession()` in tests still starts in `inspect` |
| `night_id` | `n1` |
| Indoor temp | `26.4` |
| `t` | `02:00:00` |
| `filter_text` | `none` |
| Mosquito draw | `none` (session UI only, never an Event) |

In `inspect`, every **`open.*`** play first calls session `reset_night` (window, lamp, tonight’s counts), then `play`. `follow.*` does not reset.  
`continue` never auto-resets.

---

## 2. Routes

All `application/json`. Errors: `{"error": "<ascii id>"}`, HTTP 400/409. Never put an API key in a response.

| Method | Path | Job |
| --- | --- | --- |
| `POST` | `/session` | New session. Body §3. Full snapshot back |
| `GET` | `/session` | Current snapshot |
| `POST` | `/play` | `{ "choice_id": "open.scratch.head" }`. Snapshot back |
| `POST` | `/reset` | Reset tonight’s window / lamp / counts. Memory and filter stay |
| `POST` | `/next-night` | Next `night_id` only (`n1→n2→n3→n4…`). No morning. Cards and filter stay |
| `POST` | `/morning` | Morning brief. Success auto-advances (same as `/next-night`). LLM pane still shows this morning. Window open → 409 `window_open` |
| `POST` | `/label` | `{ "morning_label": "mosquito" }` three keys, no LLM. Stamps the **current** `night_id` |
| `POST` | `/ui` | `{ "mosquito_draw": "head", "temp_c": 8.0, "mode": "inspect" }` session controls only, not the loop |

No WebSocket. One click, one request.

---

## 3. `POST /session` body

```json
{
  "mode": "inspect",
  "temp_c": 26.4,
  "pass_a_fixture": "off",
  "filter_text": "none"
}
```

| Key | Meaning |
| --- | --- |
| `mode` | `inspect` \| `continue` |
| `temp_c` | Written onto every later Event |
| `filter_text` | Pre-set accepted soft line; still runs `accept_filter_text` (illegal → `none`) |
| `pass_a_fixture` | Pin FakeLLM Pass A, §6. Omit for the current FakeLLM default |

Morning FakeLLM: if yesterday already has a legal line, copy yesterday; if yesterday is `none` and a water clock habit exists, write `ignore ~01:55-02:15 motion sigh_shift`; if a `scratch_burst morning not_mosquito` habit exists, write `ignore motion scratch_burst`. Else `none`. `POST /morning` may still override once with `script_filter_text`.

---

## 4. Snapshot

Every write returns this object. The page draws only these keys. It does not invent state.

```json
{
  "mode": "inspect",
  "night_id": "n1",
  "t": "02:00:00",
  "temp_c": 26.4,
  "mosquito_draw": "none",
  "window": {
    "open": false,
    "phase": "closed",
    "first_light": "none",
    "already_corrected": false,
    "elapsed_min": null
  },
  "budget": {"llm_calls_tonight": 0, "pass_a_count": 0, "pass_b_count": 0, "morning_llm_calls": 0},
  "enabled_choices": ["open.scratch.head", "open.scratch.left_calf"],
  "disabled_choices": ["follow.scratch.plus2"],
  "last_step": {
    "kind": "none",
    "choice_id": "none",
    "llm_called": false,
    "llm_kind": "none",
    "gate_hit": "none",
    "filter_hit": "none",
    "correction": "none"
  },
  "llm": {"input": null, "output": null},
  "action": {"light": "off", "mode": "none", "brightness": "none", "duration_s": 0, "aim": "none"},
  "person": {"posture": "lie_stable", "body_zone": "none"},
  "rules": {
    "hard": [
      {"id": "temp", "text": "temp_c<=10", "hit": false},
      {"id": "up", "text": "sit|off_bed", "hit": false},
      {"id": "leave", "text": "leave_bed", "hit": false},
      {"id": "trigger", "text": "not a trigger", "hit": false},
      {"id": "budget", "text": "night llm budget", "hit": false}
    ],
    "soft": [{"line": "none", "hit": false}],
    "soft_diff": {"added": [], "removed": [], "kept": []}
  },
  "memory": {
    "cards": [],
    "habit_text": "none",
    "uncertain_count": 0,
    "filter_text": "none"
  },
  "morning": null
}
```

### 4.1 `window.phase`

Derived from existing window fields. Not a new product state:

| phase | When |
| --- | --- |
| `closed` | `window.is_open` is false |
| `watch` | open, and `already_corrected` is false (phase 1) |
| `upgraded` | open, and `already_corrected` is true (phase 2) |

`first_light` comes from `pending.pass_a.light`; closed and no pending → `none`.  
`elapsed_min` uses existing `forward_elapsed_min`; closed → `null`.

### 4.2 `last_step.kind`

| kind | When |
| --- | --- |
| `none` | no play yet |
| `gated` | hard gate blocked a new Pass A |
| `filtered` | `ignore` hit, no LLM |
| `pass_a` | Pass A ran |
| `follow` | recorded while open; no close, no upgrade (e.g. +2 min) |
| `upgrade` | code lamp upgrade, no LLM |
| `pass_b` | window closed, Pass B ran |
| `morning` | morning brief |
| `label` | three keys |

`llm_called` is true only for `pass_a` / `pass_b` / `morning`.  
`llm.input` / `llm.output` are the **latest** LLM golden flat objects. Upgrade / follow / hard gate do not call the model and do not clear these panes; they are `null` only if this session has never called. The server drops `FORBIDDEN_LLM_KEYS` before send.

### 4.3 `enabled_choices`

Server only. Algorithm (a read of the scheduler, not a rewrite):

```
if not window.open:
    enable all open.*
    disable all follow.*
else:
    disable all open.*
    enable follow.sit.plus1, follow.leave.plus1, follow.wait15
    enable follow.scratch.plus2
    enable follow.scratch.plus6
```

Phase 2 still enables `follow.scratch.plus6`: that path closes, it is not a second upgrade.  
`disabled_choices` = full catalog minus enabled. The front end greys disabled; a click is a no-op (server 409 `choice_disabled` if it arrives).

Open catalog: `ui_spec` §2.4. Follow catalog: §2.5.

### 4.4 Room fields

| Key | Source |
| --- | --- |
| `action.*` | `action.apply_pass_a` or the upgrade; else the off-lamp set |
| `person.posture` | last Event, or `lie_stable` |
| `person.body_zone` | zone of the last human Event |
| `mosquito_draw` | `/ui` only, default `none` |

`aim` still goes through `sanitize_pass_a` / the table. The page must not change it.

---

## 5. `POST /play`

```json
{ "choice_id": "follow.scratch.plus6" }
```

Server:

1. `inspect` and `choice_id` starts with `open.` → `reset_night`
2. If the id is not in `enabled_choices` → 409 `choice_disabled`
3. `follow.wait15` → `loop.advance_clock(t + 15 min)`
4. Else → `make_event(...)` + `loop.on_event`
5. Clock becomes that event’s `t`
6. Snapshot back

`make_event` uses the session `night_id` / `temp_c` / current `t+dt`. `human_sound`: sit uses `slap` (same as C1), else `none`.  
Mosquito draw is **not** written into Event.

---

## 6. FakeLLM fixtures

`pass_a_fixture` only scripts Pass A’s four raw keys. Pass B still picks verdict from the outcome. Morning uses the FakeLLM default above.

| Value | raw `mode` | raw `belief_state` | derived `light` |
| --- | --- | --- | --- |
| `off` | `none` | `quiet` | `off` |
| `on` | `silent_confirm` | `possible_harassment` | `on` |
| `assist` | `assist_search` | `possible_harassment` | `on` |
| `default` | current `default_pass_a_text` | same | from mode |

Fields still pass `sanitize_pass_a` (`awake` from posture; all action fields from mode and zone).

`POST /morning`:

```json
{
  "morning_label": "none",
  "script_filter_text": "ignore ~01:55-02:15 motion sigh_shift"
}
```

If `script_filter_text` is set, this morning FakeLLM returns only that `filter_text` (`brief`/`timeline` stay one-line English placeholders). Then the usual `accept_morning_filter`.  
Omit to copy yesterday. Window open → 409, snapshot `morning` is `null`, `last_step.kind` is not `morning`, **night does not advance**.  
On success: if `morning_label` is one of the three keys, stamp the night just ended, then change `night_id`. `last_step.kind` stays `morning`. The Time dropdown `/next-night` still works alone.

`memory.cards`: same crop as the prompt, at most 5 latest high-weight card lines. `uncertain_count` still counts the whole archive.

`soft_diff`: accepted line set vs `yesterday_filter` before the request (`none` = empty). System-pane color only. Not part of accept.

---

## 7. Error ids

| id | When |
| --- | --- |
| `choice_disabled` | a grey choice was sent |
| `unknown_choice` | id not in the catalog |
| `window_open` | `/morning` while the window is open |
| `unknown_label` | three-key value is not one of those three words |
| `bad_json` | body is not an object |

Do not serve a stack as an error page. Do not read `.env` into the snapshot.

---

## 8. Boundary with the loop

| Allowed | Not allowed |
| --- | --- |
| Wrap `UiSession`; inside, only call `NightLoop` / `make_event` / `accept_filter_text` | Reimplement `elapsed_min`, gates, or filter regex in `ui_*.py` |
| `enabled_choices` as a read-only projection of `WindowState` | Front end disables choices from a story |
| FakeLLM fixtures to walk lamps / drafts | Default pytest hitting Gemini / Token Factory |
| Snapshot shows golden JSON as-is | Give the model `mosquito_draw` / coordinates |

Changing LLM is `RemoteLLM(provider=...)` at session create. Page routes do not branch on vendor.
