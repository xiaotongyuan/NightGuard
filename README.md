# NightGuard

**The mosquito is a hidden variable. The human is the sensor.**

NightGuard is a bedside agent for one deeply unfair classification problem: at
2 a.m., was that movement a mosquito problem, a water trip, or simply a human
being human?

It never tries to see the insect. It watches what the sleeper does next, learns
which interruptions were useful, and compiles repeated habits into tiny rules.
The lamp is a judgment, not a reading light. Please do not read in bed and then
file a bug when it judges you.

Hackathon track: **Best Apps and Agents** (Nebius × NVIDIA). The submission uses
**NVIDIA Nemotron 3 Nano 30B-A3B** on **Nebius Token Factory**.

![NightGuard three-pane page](docs/UI_outlook.png)

## The 90-second story

1. On nights 1–3, the sleeper sighs near 2 a.m. and then leaves the bed.
2. NightGuard makes a first judgment, watches the next 15 minutes, and stores
   the outcome instead of pretending the first guess was truth.
3. Repetition becomes a habit: “this person usually gets water around 2 a.m.”
4. In the morning, the model proposes one executable rule:
   `ignore ~01:55-02:15 motion sigh_shift`.
5. On night 4, code runs that rule. The lamp stays off and the model is not
   called.

**Observe → judge → check the outcome → compile a rule → ask less next time.**

## Why use an LLM?

Most of NightGuard is deliberately ordinary code. Code owns:

- hard gates such as a cold room, a person already up, and the nightly budget;
- the 15-minute watch window and the single `off → on` correction;
- clock clustering, memory selection, lamp targeting, and JSON validation;
- the only two legal policy operations: `ignore` and `downweight`;
- the final veto over anything unsafe or outside the contract.

The model handles the part that does not fit a frozen lookup table: deciding
which slice of this sleeper's noisy history matters, reviewing whether a lamp
helped, and proposing how tomorrow should interrupt them less.

The model never receives a mosquito location, count, wingbeat, or diagnosis.
There is no insect oracle hiding behind the UI.

**Code owns time and safety. The LLM owns personal strategy.**

## When the model is called

In the full loop shown by the video, every model-required beat uses the selected
LLM:

- **Pass A** — an ungated, unfiltered motion needs a first judgment;
- **Pass B** — the watch window closes and the earlier lamp decision is reviewed;
- **Morning Update** — recent outcomes are compiled into tomorrow's policy.

Hard gates, accepted `ignore` rules, morning labels, and the one in-window lamp
upgrade are code-only. Pass A and Pass B share a budget of six attempts per
night. Deterministic local replies may be retried once; a paid remote beat is
attempted once and falls back locally if its JSON is invalid. Morning Update is
separate.

The public web demo is built for that cheaper routing profile: Pass A and Pass
B stay on deterministic FakeLLM; **Update tomorrow's rules** is the only beat
that can call Nemotron. The hosted key is set, so that beat is the paid call.
If the key is missing, the page still boots on FakeLLM. Labels are under
[Model availability](#model-availability).

The exact state machine, prompt contracts, filter grammar, and sanitization
rules live in [the design spec](docs/design_spec.md).

## Live demo

**https://nightguard-h18y.onrender.com/**

### Model availability

- The public host has `NEMOTRON_API_KEY` set. **Update tomorrow's rules**
  calls Nemotron; night Pass A and Pass B stay on FakeLLM to protect the
  sponsored credits.
- Confirm on the page: Backend should say `nano`. `fake` means this process
  started without the key.
- After public testing, the hosted key will be removed.

The Backend label is the source of truth for the current deployment.

The Render instance is one shared room. The first visitor who writes becomes
the operator; everyone else watches the same state. The seat expires after
three idle minutes, pages refresh every 2.5 seconds, and competing writes
receive `429 busy`. Successful Morning Updates are at least 30 seconds apart.

The free host may sleep after roughly 15 idle minutes, so the first load can
take about a minute.

### What the Backend label means

- `nano` — Morning Update can call Nemotron.
- `fake` — no `NEMOTRON_API_KEY` was available; the whole page uses FakeLLM.
- `hour cap` — this process spent its configured UTC-hour purse.
- `out of usage` — Token Factory refused billing; later calls in this process
  use FakeLLM.
- `remote error` — network, HTTP 500, or an unknown remote failure; this beat
  used FakeLLM. The next Update still tries Token Factory.

The hosted purse is `$0.02` per UTC hour. This is a demo guardrail, **not a
lifetime spending limit**: the counter is held in memory, a process restart
resets it, and a new UTC hour opens a new purse. A request starts only while at
least `$0.001` remains, output is capped at 512 tokens, and a remote Morning
Update is one paid HTTP call. Invalid JSON falls back locally. Provider-side
credit limits remain the real hard stop.

No key on Render means `--llm nemotron` immediately falls back to FakeLLM, so
the page still boots. The key is read only from the environment and is never
returned in page JSON. Deployment details and current limitations are in
[docs/deployment.md](docs/deployment.md).

## Run locally

```text
python -m venv .venv
```

Activate it (`source .venv/bin/activate` on macOS/Linux or
`.venv\Scripts\activate` on Windows), then:

```text
pip install -r requirements.txt
export PYTHONPATH=src          # PowerShell: $env:PYTHONPATH = "src"
pytest
python -m nightguard.ui_server
```

Open `http://127.0.0.1:8765/`. The default is loopback-only FakeLLM.

To test the hosted routing profile locally:

```text
python -m nightguard.ui_server --llm nemotron
```

Copy `.env.example` and set the `NEMOTRON_*` values. In this profile only
Morning Update reaches Token Factory. Gemini remains a local scratch backend;
it is not the submission proof.

## Tests

The default suite is fully offline:

```text
pytest
NIGHTGUARD_REMOTE=1 pytest tests/test_remote.py -m remote
```

It covers modules, complete scenes, a 4 × 5 belief/outcome matrix, prompt
contracts, sanitization, and shared-room HTTP behavior.

## Read the engineering version

- [Design spec](docs/design_spec.md) — loop, model routing, shared room, rules
- [JSON contract](docs/json_contract.md) — exact model inputs and outputs
- [Test plan](docs/testplan.md) — modules → scenes → 20-cell matrix
- [UI spec](docs/ui_spec.md) — three-pane page
- [UI interface](docs/ui_interface.md) — browser ↔ NightLoop
- [Prompt tests](docs/prompt_tests.md) — holdouts kept out of runtime prompts
- [Deployment notes](docs/deployment.md) — local, Render, credits, and fallback

## License

MIT. See [LICENSE](LICENSE).
