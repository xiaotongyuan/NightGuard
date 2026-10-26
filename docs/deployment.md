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
| **Docker Space** (Hugging Face) | Yes. Same HTTP service, same three panes. Free CPU is enough. |
| Gradio / Streamlit Space | Yes, but wraps and reskins the page |
| Static HTML Space | No. No Python backend |

A public Space uses **FakeLLM**. Page Backend says `fake`. That is the scripted night, not a billing error. `out of usage` is only for a refused Token Factory call. This Space does not call Token Factory and needs no Secrets.

Local: `127.0.0.1:8765`. Space: listen `0.0.0.0:$PORT` (7860). Judges open `https://huggingface.co/spaces/<user>/NightGuard`.

| Item | Decision |
| --- | --- |
| Default inference | FakeLLM. Dockerfile starts `--llm fake` |
| Refresh | `GET` the current room. Do not `POST /session` on every open |
| Reset | **Start this example** is the only full-room reset |
| Backend label | `fake` on this Space |
| Do not | one session per visitor, visitor-supplied keys, port-forward, ngrok as the demo URL |

Do not put an API key in the page, the repo, or response JSON.

### Hugging Face (free Docker Space)

1. Push this repo (including `Dockerfile`) to GitHub.
2. huggingface.co → **New Space**.
3. SDK: **Docker**. Hardware: **CPU basic** (free). Visibility: **Public**.
4. Create from the GitHub repo, or empty Space then point it at this repo.
5. No Secrets. Wait for the build log: `NightGuard UI  http://0.0.0.0:7860/  llm=fake`.
6. Put the Space URL on Devpost and in this README.

---

## Example on the page

The short list: sigh shift → leave bed → repeat two more nights → Update tomorrow's rules → next night the sigh is skipped, scratch left calf is still asked. **Start this example** returns the room to night one, 02:00, 26.4°C, empty memory.
