const LABELS = {
  "open.scratch.head": "scratch head",
  "open.scratch.left_calf": "scratch left calf",
  "open.scratch.right_calf": "scratch right calf",
  "open.scratch.left_foot": "rub left foot",
  "open.scratch.right_foot": "rub right foot",
  "open.curl.torso": "curl",
  "open.sigh.torso": "sigh shift",
  "open.slow.torso": "slow roll",
  "open.lie": "lie down",
  "open.sit": "sit",
  "open.leave": "leave bed",
  "follow.scratch.plus2": "scratch same place (+2 min)",
  "follow.scratch.plus6": "scratch same place (+6 min)",
  "follow.sit.plus1": "sit (+1 min)",
  "follow.leave.plus1": "leave bed (+1 min)",
  "follow.wait15": "wait 15 min, no new motion",
};

// Keys must match last_step.kind. morning_label is a field, not a kind.
const KIND_WORDS = {
  none: "none",
  gated: "blocked by a hard rule",
  filtered: "personal rule matched — model not called",
  pass_a: "first judgment",
  follow: "still watching",
  upgrade: "second lamp on",
  pass_b: "window closed",
  morning: "morning update",
  label: "human feedback",
};
const CORR_WORDS = {
  none: "none",
  upgraded_on: "on",
};
const HARD_RULE_WORDS = {
  "temp_c<=10": "indoor temperature ≤ 10°C",
  "sit|off_bed": "person already up",
  leave_bed: "person leaves bed",
  "not a trigger": "no triggering motion",
  "settled lie": "settled back down",
  "night llm budget": "nightly model budget",
};

const HL = new Set(["belief_state", "reasoning", "verdict", "reason"]);
const ERRORS = {
  busy: "Someone else is operating. You can watch.",
  morning_cooldown: "Morning Update is cooling down. Try again in a moment.",
};
let feedback = "none";
let busy = false;
let exampleOn = false;
let watchTimer = null;

function operatorToken() {
  const key = "nightguard.operator";
  try {
    let token = localStorage.getItem(key);
    if (!token) {
      token = crypto.randomUUID();
      localStorage.setItem(key, token);
    }
    return token;
  } catch (_) {
    if (!window.__nightguardToken) {
      window.__nightguardToken = crypto.randomUUID();
    }
    return window.__nightguardToken;
  }
}

function setBusy(on, text) {
  busy = on;
  const kind = document.getElementById("step-kind");
  if (on && text) kind.textContent = text;
  for (const btn of document.querySelectorAll("#choices button")) {
    if (on) btn.disabled = true;
  }
}

async function api(path, method, body) {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Operator-Token": operatorToken(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(ERRORS[data.error] || data.error || res.status);
  }
  return data;
}

function pretty(obj) {
  if (!obj) return "(none)";
  return JSON.stringify(obj, null, 2);
}

function paintJson(el, obj) {
  const text = pretty(obj);
  if (!obj) {
    el.textContent = text;
    return;
  }
  el.innerHTML = "";
  for (const line of text.split("\n")) {
    const wrap = document.createElement("span");
    const key = (line.match(/"([^"]+)":/) || [])[1];
    if (HL.has(key)) wrap.className = "hl";
    wrap.textContent = line + "\n";
    el.appendChild(wrap);
  }
}

function nightLabel(nightId) {
  const n = parseInt(String(nightId).slice(1), 10);
  if (!n) return String(nightId);
  const rem = n % 100;
  const suf = rem >= 11 && rem <= 13
    ? "th"
    : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th");
  return `Night ${n}${suf}`;
}

function render(snap) {
  const backend = snap.llm_backend || "fake";
  const clock = document.getElementById("clock");
  clock.textContent =
    `${nightLabel(snap.night_id)}  ${snap.t}  Temperature ${snap.temp_c}  Backend: ${backend}`;
  clock.classList.toggle(
    "usage-out",
    backend === "out of usage" || backend === "hour cap" || backend === "remote error",
  );
  document.getElementById("clock-mode").value = "";
  const box = document.getElementById("choices");
  box.innerHTML = "";
  const all = [...snap.enabled_choices, ...snap.disabled_choices];
  for (const id of all) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.dataset.choice = id;
    btn.textContent = LABELS[id] || id;
    btn.disabled = snap.disabled_choices.includes(id);
    btn.addEventListener("click", () => play(id));
    box.appendChild(btn);
  }
  const llmOn = snap.last_step.llm_called;
  const panel = document.getElementById("llm-panel");
  panel.classList.toggle("lit", llmOn);
  panel.classList.toggle("dim", !llmOn);
  const stepKind = snap.last_step.kind;
  document.getElementById("llm-kind").textContent = llmOn
    ? `${snap.last_step.llm_kind} · called${snap.last_step.llm_parse_failed ? " · parse failed" : ""}`
    : stepKind === "filtered"
      ? "personal rule · model not called"
      : `${stepKind} · no LLM`;
  const remoteEl = document.getElementById("llm-remote");
  const remote = snap.llm && snap.llm.remote;
  const fallback = snap.llm && snap.llm.fallback;
  if (remote && remote.url) {
    remoteEl.hidden = false;
    remoteEl.textContent = `model  ${remote.model}\nurl    ${remote.url}`;
  } else if (fallback) {
    remoteEl.hidden = false;
    remoteEl.textContent = fallback;
  } else {
    remoteEl.hidden = true;
    remoteEl.textContent = "";
  }
  paintJson(document.getElementById("llm-in"), snap.llm.input);
  paintJson(document.getElementById("llm-out"), snap.llm.output);

  const hard = document.getElementById("hard");
  hard.innerHTML = "";
  for (const row of snap.rules.hard) {
    const li = document.createElement("li");
    li.textContent = HARD_RULE_WORDS[row.text] || row.text;
    if (row.hit) li.className = "hit";
    hard.appendChild(li);
  }
  const soft = document.getElementById("soft");
  soft.innerHTML = "";
  for (const row of snap.rules.soft) {
    const li = document.createElement("li");
    li.textContent = row.line;
    if (row.hit) li.className = "hit";
    soft.appendChild(li);
  }
  const on = snap.action.light === "on";
  const lamp = document.getElementById("lamp");
  lamp.className = on ? "lamp on" : "lamp";
  document.getElementById("lamp-text").textContent = on
    ? `on · ${snap.action.aim}`
    : "off";

  const habit = snap.memory.habit_text;
  document.getElementById("habit").textContent =
    !habit || habit === "none"
      ? "none yet — a habit appears after 3 similar nights"
      : habit;
  const cards = document.getElementById("cards");
  cards.innerHTML = "";
  for (const line of snap.memory.cards) {
    const li = document.createElement("li");
    li.textContent = line;
    cards.appendChild(li);
  }
  const step = snap.last_step;
  const stepKindEl = document.getElementById("step-kind");
  stepKindEl.textContent = KIND_WORDS[step.kind] || step.kind;
  stepKindEl.classList.toggle("rule-hit", step.kind === "filtered");
  document.getElementById("step-move").textContent = LABELS[step.choice_id] || step.choice_id;
  document.getElementById("step-corr").textContent = CORR_WORDS[step.correction] || step.correction;

  const zones = {
    wall_head: "wall-head",
    wall_side: "wall-side",
    wall_right: "wall-right",
    floor_left: "floor-left",
    floor_right: "floor-right",
  };
  for (const id of Object.values(zones)) {
    document.getElementById(id).classList.remove("on");
  }
  if (on && zones[snap.action.aim]) {
    document.getElementById(zones[snap.action.aim]).classList.add("on");
  }

  posePerson(snap.person.posture);
  document.getElementById("btn-morning").disabled = snap.window.open;
  paintFeedback();
  paintExample(snap);
  applySeat(snap);
}

function applySeat(snap) {
  const seat = snap.operator || { held: false, you: false, seconds_left: 0 };
  const watching = Boolean(seat.held && !seat.you);
  const el = document.getElementById("seat");
  el.className = watching ? "seat watch" : "seat";
  if (watching) {
    el.textContent = "Someone else is operating. You can watch.";
    for (const node of document.querySelectorAll("button, select")) {
      node.disabled = true;
    }
  } else {
    el.textContent = seat.you ? "You have the controls." : "";
    for (const id of ["btn-example", "clock-mode", "temp", "fb-mosquito", "fb-not", "fb-none"]) {
      const node = document.getElementById(id);
      if (node) node.disabled = false;
    }
    const morning = document.getElementById("btn-morning");
    if (morning) morning.disabled = Boolean(snap.window && snap.window.open);
  }
  if (!watchTimer) {
    watchTimer = setInterval(() => {
      if (busy) return;
      loadRoom().catch(() => {});
    }, 2500);
  }
}

function exampleCue(snap) {
  const night = parseInt(String(snap.night_id).slice(1), 10) || 1;
  const kind = snap.last_step.kind;
  const choice = snap.last_step.choice_id;
  if (night >= 4 && choice === "open.scratch.left_calf" && kind === "pass_a") {
    return { text: "Example finished. The scratch asked for a judgment.", step: 4, done: true };
  }
  if (snap.window.open) {
    return { text: "Next: leave bed (+1 min)", choice: "follow.leave.plus1", step: 1 };
  }
  if (night >= 4 && kind === "filtered") {
    return { text: "Next: scratch left calf", choice: "open.scratch.left_calf", step: 4 };
  }
  if (night >= 4) {
    return { text: "Next: sigh shift", choice: "open.sigh.torso", step: 4 };
  }
  if (kind === "pass_b" && night < 3) {
    return { text: "Next: Time → next night", select: true, step: 2 };
  }
  if (kind === "pass_b" && night === 3) {
    return { text: "Next: Update tomorrow's rules", morning: true, step: 3 };
  }
  return { text: "Next: sigh shift", choice: "open.sigh.torso", step: 0 };
}

function paintExample(snap) {
  const status = document.getElementById("example-status");
  const start = document.getElementById("btn-example");
  for (const el of document.querySelectorAll(".next-cue")) el.classList.remove("next-cue");
  for (const el of document.querySelectorAll(".example-steps li")) el.classList.remove("current");
  start.classList.toggle("picked", exampleOn);
  if (!exampleOn) {
    status.textContent = "";
    status.hidden = true;
    return;
  }
  const cue = exampleCue(snap);
  status.hidden = false;
  status.textContent = cue.text;
  const items = document.querySelectorAll(".example-steps li");
  if (items[cue.step]) items[cue.step].classList.add("current");
  if (cue.choice) {
    const btn = document.querySelector(`#choices button[data-choice="${cue.choice}"]`);
    if (btn) btn.classList.add("next-cue");
  }
  if (cue.select) document.getElementById("clock-mode").classList.add("next-cue");
  if (cue.morning) document.getElementById("btn-morning").classList.add("next-cue");
}

function paintFeedback() {
  document.getElementById("fb-mosquito").classList.toggle("picked", feedback === "mosquito");
  document.getElementById("fb-not").classList.toggle("picked", feedback === "not_mosquito");
  document.getElementById("fb-none").classList.toggle("picked", feedback === "none");
}

function setLine(id, x1, y1, x2, y2) {
  const el = document.getElementById(id);
  el.setAttribute("x1", x1);
  el.setAttribute("y1", y1);
  el.setAttribute("x2", x2);
  el.setAttribute("y2", y2);
}

function posePerson(posture) {
  const head = document.getElementById("person-head");
  let x = 160;
  let hy = 104;
  if (posture === "off_bed") {
    x = 86;
    hy = 150;
  } else if (posture === "sit") {
    hy = 112;
  }
  const neck = hy + 10;
  const hip = posture === "sit" ? neck + 22 : neck + 34;
  head.setAttribute("cx", x);
  head.setAttribute("cy", hy);
  setLine("person-body", x, neck, x, hip);
  if (posture === "sit") {
    setLine("person-arm-l", x, neck + 8, x - 14, hip - 2);
    setLine("person-arm-r", x, neck + 8, x + 14, hip - 2);
    setLine("person-leg-l", x, hip, x - 16, hip + 6);
    setLine("person-leg-r", x, hip, x + 16, hip + 6);
  } else {
    setLine("person-arm-l", x, neck + 8, x - 12, neck + 24);
    setLine("person-arm-r", x, neck + 8, x + 12, neck + 24);
    setLine("person-leg-l", x, hip, x - 10, hip + 20);
    setLine("person-leg-r", x, hip, x + 10, hip + 20);
  }
}

async function play(choiceId) {
  if (busy) return;
    setBusy(true, "working…");
  try {
    render(await api("/play", "POST", { choice_id: choiceId }));
  } catch (err) {
    document.getElementById("step-kind").textContent = String(err);
    try {
      const snap = await api("/session", "GET");
      render(snap);
    } catch (_) {
      /* keep the error text */
    }
    document.getElementById("step-kind").textContent = String(err);
  } finally {
    busy = false;
  }
}

async function loadRoom() {
  render(await api("/session", "GET"));
}

async function newSession() {
  feedback = "none";
  const temp = Number(document.getElementById("temp").value);
  render(await api("/session", "POST", {
    mode: "continue",
    temp_c: temp,
  }));
}

document.getElementById("clock-mode").addEventListener("change", async (ev) => {
  const cmd = ev.target.value;
  ev.target.value = "";
  if (cmd === "new") {
    await newSession();
  } else if (cmd === "reset") {
    render(await api("/reset", "POST", {}));
  } else if (cmd === "next") {
    render(await api("/next-night", "POST", {}));
  }
});
document.getElementById("btn-morning").addEventListener("click", async () => {
  render(await api("/morning", "POST", { morning_label: feedback }));
});
document.getElementById("fb-mosquito").addEventListener("click", async () => {
  feedback = "mosquito";
  render(await api("/label", "POST", { morning_label: "mosquito" }));
});
document.getElementById("fb-not").addEventListener("click", async () => {
  feedback = "not_mosquito";
  render(await api("/label", "POST", { morning_label: "not_mosquito" }));
});
document.getElementById("fb-none").addEventListener("click", () => {
  feedback = "none";
  paintFeedback();
});
document.getElementById("temp").addEventListener("change", async (ev) => {
  render(await api("/ui", "POST", { temp_c: Number(ev.target.value) }));
});
document.getElementById("btn-example").addEventListener("click", async () => {
  if (busy) {
    const status = document.getElementById("example-status");
    status.hidden = false;
    status.textContent = "Still working…";
    return;
  }
  setBusy(true, "working…");
  exampleOn = true;
  feedback = "none";
  document.getElementById("temp").value = "26.4";
  try {
    render(await api("/session", "POST", {
      mode: "continue",
      temp_c: 26.4,
      filter_text: "none",
    }));
  } catch (err) {
    document.getElementById("example-status").textContent = String(err);
  } finally {
    busy = false;
  }
});

loadRoom().catch((err) => {
  document.getElementById("step-kind").textContent = String(err);
});
