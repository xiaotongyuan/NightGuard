# NightGuard run notes

Product rules stay in `docs/design_spec.md`. This page is only how to run the page and how to show a real Token Factory call.

Do not publish a home `8765` port. Local is for you. A public demo is a hosted page, not a tunnel.

---

## Local

| Command | Backend |
| --- | --- |
| `python -m nightguard.ui_server` | FakeLLM. Default. Offline. |
| `python -m nightguard.ui_server --llm nemotron` | Every Pass A, Pass B, and morning hits Nano on Token Factory |
| `python -m nightguard.ui_server --llm gemini --model gemini-3.5-flash-lite` | Local scratch only. Not submission proof |

Bind: `http://127.0.0.1:8765/` loopback only.

```text
export PYTHONPATH=src          # Windows PowerShell: $env:PYTHONPATH = "src"
python -m nightguard.ui_server
python -m nightguard.ui_server --llm nemotron
```

`--llm nemotron` reads `.env`: `NEMOTRON_API_KEY`, `NEMOTRON_MODEL`, `NEMOTRON_BASE_URL`. Copy `.env.example`. The key never appears in the page, the snapshot, or an error body. After a real call the System pane shows the Token Factory URL and the full model name.

Submission proof is **NVIDIA Nemotron on Nebius Token Factory**. A same-named model on Hugging Face or OpenRouter does not count. Gemini is local practice only.

If Token Factory returns a billing refusal (HTTP 402, `insufficient_quota`, balance, trial ended), `RemoteLLM` finishes the beat with FakeLLM and the page Backend becomes `out of usage`. Later remote calls in that process stay off. Other failures stay visible locally so a bad model reply is not hidden.

---

## Hosted demo

The page is `python -m nightguard.ui_server` plus `web/`, not Gradio or Streamlit.

| Host | Fits |
| --- | --- |
| **Docker Space** (Hugging Face) | Yes. Same HTTP service, same three panes |
| Gradio / Streamlit Space | Yes, but wraps and reskins the page |
| Static HTML Space | No. No Python backend |

Secrets (`NEMOTRON_API_KEY` and Token Factory URL / model) live in the host secret store, not in git.

A public room is **one shared night**, not one model stream per visitor.

| Item | Decision |
| --- | --- |
| Default inference | FakeLLM for scratches, sits, leaves, first judgment, and 15-minute review |
| Live call | Optional, rate-limited. Prefer morning **Update tomorrow's rules** only |
| Refresh | `GET` the current room. Do not `POST /session` on every open |
| Reset | **Start this example** is the only full-room reset |
| Backend label | `fake`, `nano`, or `out of usage` |
| Do not | one session per visitor, visitor-supplied keys, WebSockets, port-forward, ngrok as the demo URL |

Do not put an API key in the page, the repo, or response JSON.

---

## Example on the page

The short list: sigh shift → leave bed → repeat two more nights → Update tomorrow's rules → next night the sigh is skipped, scratch left calf is still asked. **Start this example** returns the room to night one, 02:00, 26.4°C, empty memory.
