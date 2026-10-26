# NightGuard run notes

Product rules stay in `docs/design_spec.md`. This page is only how to run the page and how to show a real Token Factory call.

Do not publish a home `8765` port. Local is for you. A public demo is a hosted page, not a tunnel.

---

## Local

| Command | Backend |
| --- | --- |
| `python -m nightguard.ui_server` | FakeLLM. Default. Offline. |
| `python -m nightguard.ui_server --llm nemotron` | Only morning Update hits Nano. Pass A / Pass B stay FakeLLM |
| `python -m nightguard.ui_server --llm gemini --model gemini-3.5-flash-lite` | Local scratch only. Not submission proof |

Bind: `http://127.0.0.1:8765/` loopback only.

```text
export PYTHONPATH=src          # Windows PowerShell: $env:PYTHONPATH = "src"
python -m nightguard.ui_server
python -m nightguard.ui_server --llm nemotron
```

`--llm nemotron` reads `.env`: `NEMOTRON_API_KEY`, `NEMOTRON_MODEL`, `NEMOTRON_BASE_URL`, `NIGHTGUARD_HOURLY_USD`. Copy `.env.example`. Only morning **Update tomorrow's rules** hits Token Factory. Night Pass A / Pass B stay FakeLLM. The hour purse is `$0.10` on the UTC hour; leftover dies at the hour and does not carry. A call claimed in one hour and settled after the hour is billed to the **new** hour. The wallet takes one in-flight seat so two threads cannot both HTTP. When the purse is empty the page Backend says `hour cap` (not `out of usage`). The key never appears in the page, the snapshot, or an error body. After a real morning call the System pane shows the Token Factory URL and the full model name.

Submission proof is **NVIDIA Nemotron on Nebius Token Factory**. A same-named model on Hugging Face or OpenRouter does not count. Gemini is local practice only.

If Token Factory returns a billing refusal (HTTP 402, `insufficient_quota`, balance, trial ended), `RemoteLLM` finishes the beat with FakeLLM and the page Backend becomes `out of usage`. Later remote calls in that process stay off. Other failures stay visible locally so a bad model reply is not hidden.

---

## Hosted demo

The page is `python -m nightguard.ui_server` plus `web/`, not Gradio or Streamlit. Hugging Face now charges to **create** Docker and Gradio Spaces. Static Spaces cannot run Python. The public demo is a **Render** free web service: same HTTP page, no reskin, no credit card.

| Host | Fits |
| --- | --- |
| **Render free web service** | Yes. `render.yaml` starts `--llm nemotron` on `0.0.0.0:$PORT` |
| Hugging Face Docker / Gradio | Paid to create as of 2026-10. Skip |
| Hugging Face Static | No. No Python backend |

A public host uses **Nemotron on Token Factory** for morning **Update tomorrow's rules**. Night Pass A / Pass B stay FakeLLM. Page Backend says `nano` when the dashboard key is set. No key → `fake`; the page still opens. `hour cap` is this UTC hour’s `$0.10` spent. `out of usage` is a refused Token Factory bill.

`NEMOTRON_API_KEY` lives in the Render dashboard only (`sync: false` in `render.yaml`). Never put the key in the repo, the page, or response JSON. Model, base URL, and the `$0.10` hour purse are non-secret env vars in `render.yaml`. This service already exists: a later Blueprint sync **will not** prompt for the key. If the secret is missing the host boots as FakeLLM and only the Backend label / start log show it.

Local: `127.0.0.1:8765`. Hosted: listen `0.0.0.0:$PORT` (Render injects `PORT`). Judges open [https://nightguard-h18y.onrender.com/](https://nightguard-h18y.onrender.com/).

The free instance sleeps after about 15 idle minutes. The first open can take about a minute.

| Item | Decision |
| --- | --- |
| Default inference | `--llm nemotron`. Morning Update hits Nano. Night stays local |
| Refresh | `GET` the current room. Do not `POST /session` on every open |
| Reset | **Start this example** is the only full-room reset |
| Seat | One operator. Same browser = same token = same seat. Every page refreshes the shared room every 2.5s. Writes send `X-Operator-Token`. A second writer gets `429 busy` and can only watch. Idle 3 minutes releases the seat |
| Backend label | `nano` when the key is set; `fake` if the secret is missing; `hour cap` or `out of usage` when those fire |
| Do not | one session per visitor, visitor-supplied keys, port-forward, ngrok as the demo URL |

### Render (free web service)

1. In the existing service dashboard, add `NEMOTRON_API_KEY` as a secret **before** the `--llm nemotron` deploy. This service already exists, so a later Blueprint sync will not prompt for `sync: false` keys.
2. Push this repo (including `render.yaml`) to GitHub.
3. [render.com](https://render.com) → sign in with GitHub. No card.
4. **New → Blueprint**, pick `xiaotongyuan/NightGuard`. Or **New → Web Service** on the same repo; Render reads `render.yaml`.
5. Plan: **Free**. Do not set `PORT`.
6. Wait for the log: `NightGuard UI  http://0.0.0.0:<port>/  llm=nano`. Then open the page: Backend must say `nano`. Missing key prints `NEMOTRON_API_KEY missing; using FakeLLM` and `llm=fake`. Add the secret and redeploy. The page still opens either way.
7. Live URL: [https://nightguard-h18y.onrender.com/](https://nightguard-h18y.onrender.com/). Same address on Devpost and in this README.

---

## Example on the page

The short list: sigh shift → leave bed → repeat two more nights → Update tomorrow's rules → next night the sigh is skipped, scratch left calf is still asked. **Start this example** returns the room to night one, 02:00, 26.4°C, empty memory.
