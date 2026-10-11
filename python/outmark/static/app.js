const statusNode = document.querySelector("#status");
const modelNote = document.querySelector("#model-note");
const setup = document.querySelector("#setup");
const proposalPanel = document.querySelector("#proposal");
const activePanel = document.querySelector("#active");
const proposalTitle = document.querySelector("#proposal-title");
const proposalInstructions = document.querySelector("#proposal-instructions");
const proposalMeta = document.querySelector("#proposal-meta");
const proposalQuestion = document.querySelector("#proposal-question");
const activeTitle = document.querySelector("#active-title");
const activeQuest = document.querySelector("#active-quest");
const timerNode = document.querySelector("#timer");
const activeQuestion = document.querySelector("#active-question");
const reflectionNode = document.querySelector("#reflection");
const gridNode = document.querySelector("#grid");
const sessionsNode = document.querySelector("#sessions");
const historyRange = document.querySelector("#history-range");
const plantLabel = document.querySelector("#plant-label");
const plantDrawing = document.querySelector("#plant-drawing");
const matrixNote = document.querySelector("#matrix-note");
const categoryLabels = new Map(
  [...document.querySelectorAll("#category option")].map((option) => [option.value, option.textContent]),
);

const timerState = document.querySelector("#timer-state");
const activeMeta = document.querySelector("#active-meta");
const ring = document.querySelector("#ring");
const ringLength = 2 * Math.PI * 52;

let modelPresent = false;
let proposalId = null;
let sessionId = null;
let poll = null;
let reportOpen = false;
let plantStage = null;

setup.addEventListener("submit", (event) => {
  event.preventDefault();
  suggest();
});
document.querySelector("#accept").addEventListener("click", accept);
document.querySelector("#reject").addEventListener("click", reject);
document.querySelector("#kept").addEventListener("click", () => report("kept"));
document.querySelector("#not-kept").addEventListener("click", () => report("not_kept"));
for (const input of document.querySelectorAll("input[name=matrix]")) {
  input.addEventListener("change", () => {
    if (input.checked) {
      setMatrix(input.value);
    }
  });
}

boot();

async function boot() {
  statusNode.textContent = "Checking the local service…";
  try {
    const health = await readJson("/health");
    if (health.status !== "ok" || health.data_dir_ready !== true) {
      statusNode.textContent = "The local service responded, but storage is not ready.";
      return;
    }
    modelPresent = health.model_present === true;
    showModel(null);
    const state = await readJson("/api/session");
    renderState(state);
    await renderHistory();
    statusNode.textContent = statusFor(state.phase);
  } catch (error) {
    statusNode.textContent = error.message || "The local service did not respond.";
  }
}

async function suggest() {
  const duration = document.querySelector("input[name=duration]:checked");
  setBusy(true);
  statusNode.textContent = "Writing a suggestion…";
  try {
    const state = await sendJson("/api/quest", {
      duration_minutes: Number(duration.value),
      category: document.querySelector("#category").value,
    });
    showModel(state.source);
    renderState(state);
    statusNode.textContent = "One suggestion. Accept it, or reject it and ask again.";
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function accept() {
  setBusy(true);
  try {
    const state = await sendJson("/api/session/start", { proposal_id: proposalId });
    renderState(state);
    statusNode.textContent = "Your commitment is in progress.";
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function reject() {
  setBusy(true);
  try {
    const state = await sendJson("/api/proposal/reject", { id: proposalId });
    renderState(state);
    statusNode.textContent = "Rejected. Ask for another suggestion when you are ready.";
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function report(outcome) {
  const reflection = reflectionNode.value.trim();
  setBusy(true);
  try {
    const state = await sendJson("/api/session/report", {
      session_id: sessionId,
      outcome,
      reflection: reflection === "" ? null : reflection,
    });
    renderState(state);
    await renderHistory();
    statusNode.textContent = "Recorded. Only a kept commitment lights a cell.";
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function statusFor(phase) {
  if (phase === "proposed") {
    return "One suggestion. Accept it, or reject it and ask again.";
  }
  if (phase === "active") {
    return "Your commitment is in progress.";
  }
  if (phase === "awaiting_report") {
    return "Time's up. How did it go?";
  }
  return "Choose a duration and a category.";
}

function renderState(state) {
  showPlant(state.plant);
  applyDisplay(state);
  if (state.phase === "proposed" && state.proposal) {
    showProposal(state.proposal);
    return;
  }
  if ((state.phase === "active" || state.phase === "awaiting_report") && state.session) {
    showActive(state.session);
    return;
  }
  showSetup();
}

function showSetup() {
  stopPoll();
  proposalId = null;
  sessionId = null;
  reportOpen = false;
  setup.hidden = false;
  proposalPanel.hidden = true;
  activePanel.hidden = true;
}

function showProposal(proposal) {
  stopPoll();
  proposalId = proposal.id;
  sessionId = null;
  proposalTitle.textContent = proposal.title;
  proposalInstructions.textContent = proposal.instructions;
  proposalMeta.textContent = `${proposal.duration_minutes} minutes · ${labelFor(proposal.category)}`;
  proposalQuestion.textContent = proposal.reflection_question;
  setup.hidden = true;
  proposalPanel.hidden = false;
  activePanel.hidden = true;
}

function showActive(session) {
  const changed = sessionId !== session.id;
  sessionId = session.id;
  proposalId = null;
  reportOpen = session.deadline_passed === true;
  if (changed) {
    activeTitle.textContent = session.title;
    activeQuest.textContent = session.quest;
    activeQuestion.textContent = session.reflection_question;
    activeMeta.textContent = `${session.duration_minutes} minutes · ${labelFor(session.category)}`;
    reflectionNode.value = "";
    startPoll();
  }
  timerState.textContent = reportOpen
    ? "Time's up. How did it go?"
    : "Your commitment is in progress.";
  timerNode.textContent = formatRemaining(session.remaining_seconds);
  paintRing(session);
  lockReports();
  setup.hidden = true;
  proposalPanel.hidden = true;
  activePanel.hidden = false;
}

function paintRing(session) {
  const total = session.duration_minutes * 60;
  const elapsed = Math.min(total, Math.max(0, session.elapsed_seconds));
  const ratio = total === 0 ? 0 : elapsed / total;
  ring.style.strokeDasharray = String(ringLength);
  ring.style.strokeDashoffset = String(ringLength * (1 - ratio));
}

function lockReports() {
  document.querySelector("#kept").disabled = !reportOpen;
  document.querySelector("#not-kept").disabled = !reportOpen;
  reflectionNode.disabled = !reportOpen;
}

function showModel(source) {
  if (source === "fallback") {
    modelNote.hidden = false;
    modelNote.textContent = "The local model did not answer. This suggestion comes from the catalog.";
    return;
  }
  if (!modelPresent) {
    modelNote.hidden = false;
    modelNote.textContent = "No model file is installed. Suggestions come from the built-in catalog.";
    return;
  }
  modelNote.hidden = true;
  modelNote.textContent = "";
}

function applyDisplay(state) {
  if (!state || !state.display_mode) {
    return;
  }
  for (const input of document.querySelectorAll("input[name=matrix]")) {
    input.checked = input.value === state.display_mode;
  }
  matrixNote.textContent = state.display_connected
    ? "Sent to the board. This page cannot see the glass."
    : "Saved here. The board has not accepted it.";
}

async function setMatrix(mode) {
  setBusy(true);
  try {
    const state = await sendJson("/api/display-mode", { display_mode: mode });
    renderState(state);
    statusNode.textContent = statusFor(state.phase);
  } catch (error) {
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function showPlant(plant) {
  if (!plant) {
    return;
  }
  const next = Number(plant.stage);
  const grew = plantStage !== null && next > plantStage;
  plantStage = next;
  plantLabel.textContent = plant.label;
  plantDrawing.dataset.stage = String(next);
  plantDrawing.classList.toggle("grew", grew);
}

async function renderHistory() {
  const history = await readJson("/api/history");
  showPlant(history.plant);
  historyRange.textContent = `${history.start_date} through ${history.end_date}. A filled cell is a kept commitment.`;
  gridNode.replaceChildren();
  for (const row of history.rows) {
    const name = document.createElement("span");
    name.className = "row-label";
    name.textContent = row.label;
    gridNode.append(name);
    for (const lit of row.cells) {
      const cell = document.createElement("span");
      cell.className = lit ? "cell lit" : "cell";
      gridNode.append(cell);
    }
  }
  sessionsNode.replaceChildren();
  if (history.sessions.length === 0) {
    const item = document.createElement("li");
    item.className = "empty";
    item.textContent = "No sessions in the last 13 days.";
    sessionsNode.append(item);
    return;
  }
  let day = "";
  for (const session of history.sessions) {
    const stamp = session.started_at || "";
    const nextDay = stamp.slice(0, 10);
    if (nextDay !== day) {
      day = nextDay;
      const heading = document.createElement("li");
      heading.className = "log-day";
      heading.textContent = day;
      sessionsNode.append(heading);
    }
    const item = document.createElement("li");
    item.className = "log-entry";
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = stamp.slice(11, 16);
    const title = document.createElement("span");
    title.className = "log-title";
    title.textContent = session.title;
    const outcome = document.createElement("span");
    outcome.className = "log-outcome";
    outcome.textContent = outcomeLabel(session.status);
    const detail = document.createElement("p");
    detail.className = "log-detail";
    detail.textContent = `${session.duration_minutes} min · ${labelFor(session.category)}`;
    item.append(time, title, outcome, detail);
    if (session.reflection) {
      const note = document.createElement("p");
      note.className = "log-note";
      note.textContent = session.reflection;
      item.append(note);
    }
    sessionsNode.append(item);
  }
}

function outcomeLabel(status) {
  if (status === "kept") {
    return "Kept";
  }
  if (status === "not_kept") {
    return "Not kept";
  }
  return "In progress";
}

function startPoll() {
  stopPoll();
  poll = setInterval(() => {
    readJson("/api/session")
      .then((state) => {
        if (state.phase === "active" || state.phase === "awaiting_report") {
          renderState(state);
        }
      })
      .catch((error) => {
        statusNode.textContent = error.message;
      });
  }, 1000);
}

function stopPoll() {
  if (poll !== null) {
    clearInterval(poll);
    poll = null;
  }
}

function setBusy(busy) {
  document.querySelector("#app").setAttribute("aria-busy", busy ? "true" : "false");
  for (const control of document.querySelectorAll("button, select, textarea, input")) {
    control.disabled = busy;
  }
  if (!busy) {
    lockReports();
  }
}

function formatRemaining(seconds) {
  const whole = Math.max(0, Math.ceil(seconds));
  const minutes = Math.floor(whole / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function labelFor(category) {
  return categoryLabels.get(category) || category;
}

async function sendJson(url, payload) {
  return readJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function readJson(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("The local service did not respond.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.error || "The request failed.");
  }
  return body;
}
