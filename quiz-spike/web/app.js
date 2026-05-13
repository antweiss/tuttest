/**
 * דמו חידון: טוען spike_bank.json (או כתובת מ־?bank=).
 * מזהי נושא: שדה מזהה_נושא ב־JSON או t{index}.
 */
const LABELS = ["א", "ב", "ג", "ד"];

function bankUrl() {
  const q = new URLSearchParams(window.location.search).get("bank");
  if (q) return q;
  return "spike_bank.json";
}

function topicId(topic, index) {
  return topic["מזהה_נושא"] != null ? String(topic["מזהה_נושא"]) : `t${index}`;
}

function parseRoute() {
  const hash = (window.location.hash || "").replace(/^#/, "");
  if (hash.startsWith("quiz/")) {
    const id = hash.slice("quiz/".length);
    return { view: "quiz", topicId: id || null };
  }
  if (hash === "results") return { view: "results", topicId: null };
  return { view: "home", topicId: null };
}

function setRoute(view, topicId) {
  if (view === "home") window.location.hash = "";
  else if (view === "quiz" && topicId) window.location.hash = `quiz/${topicId}`;
  else if (view === "results") window.location.hash = "results";
}

const state = {
  bank: null,
  loadError: null,
  topicIndex: 0,
  qIndex: 0,
  answers: [],
};

const els = {};

function $(id) {
  return document.getElementById(id);
}

function showView(name) {
  document.querySelectorAll(".views section").forEach((sec) => {
    sec.classList.toggle("is-active", sec.dataset.view === name);
  });
}

async function loadBank() {
  const url = bankUrl();
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    state.bank = await r.json();
    state.loadError = null;
  } catch (e) {
    state.loadError = e.message || String(e);
    state.bank = null;
  }
}

function findTopicIndexById(id) {
  if (!state.bank || !id) return -1;
  const topics = state.bank["נושאים"] || [];
  const i = topics.findIndex((t, idx) => topicId(t, idx) === id);
  return i;
}

function renderHome() {
  const meta = state.bank["מטא"] || {};
  $("bank-meta").textContent = [
    meta["מספר_נושאים"] != null ? `${meta["מספר_נושאים"]} נושאים` : "",
    meta["שאלות_לכל_נושא"] != null ? `${meta["שאלות_לכל_נושא"]} שאלות לנושא` : "",
    meta["מקור_חלוקת_נושאים"] || "",
  ]
    .filter(Boolean)
    .join(" · ");

  const ul = $("topic-list");
  ul.innerHTML = "";
  const topics = state.bank["נושאים"] || [];
  topics.forEach((t, idx) => {
    const id = topicId(t, idx);
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    const title = t["כותרת"] || id;
    const nq = (t["שאלות"] || []).length;
    btn.innerHTML = `<span>${escapeHtml(title)}</span><span class="topic-meta">${nq} שאלות · ${escapeHtml(id)}</span>`;
    btn.addEventListener("click", () => startQuiz(idx));
    li.appendChild(btn);
    ul.appendChild(li);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function startQuiz(topicIndex) {
  const topics = state.bank["נושאים"] || [];
  const t = topics[topicIndex];
  if (!t || !(t["שאלות"] || []).length) return;
  state.topicIndex = topicIndex;
  state.qIndex = 0;
  state.answers = [];
  const id = topicId(t, topicIndex);
  setRoute("quiz", id);
  renderQuiz();
  showView("quiz");
}

function renderQuiz() {
  const topics = state.bank["נושאים"] || [];
  const t = topics[state.topicIndex];
  const questions = t["שאלות"] || [];
  const q = questions[state.qIndex];
  $("quiz-title").textContent = t["כותרת"] || "";
  $("quiz-progress").textContent = `שאלה ${state.qIndex + 1} מתוך ${questions.length}`;
  $("question-text").textContent = q["ניסוח"] || "";
  const choices = $("choices");
  choices.innerHTML = "";
  const selected = state.answers[state.qIndex];
  (q["אפשרויות"] || []).forEach((text, j) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "choice" + (selected === j ? " is-selected" : "");
    btn.innerHTML = `<span class="mark">${LABELS[j]}</span><span class="text">${escapeHtml(text)}</span>`;
    btn.addEventListener("click", () => {
      state.answers[state.qIndex] = j;
      renderQuiz();
    });
    choices.appendChild(btn);
  });
  $("btn-next").disabled = selected === undefined;
}

function nextQuestion() {
  const topics = state.bank["נושאים"] || [];
  const questions = topics[state.topicIndex]["שאלות"] || [];
  if (state.qIndex < questions.length - 1) {
    state.qIndex += 1;
    renderQuiz();
  } else {
    setRoute("results");
    renderResults();
    showView("results");
  }
}

function scoreTopic() {
  const topics = state.bank["נושאים"] || [];
  const t = topics[state.topicIndex];
  const questions = t["שאלות"] || [];
  let ok = 0;
  questions.forEach((q, i) => {
    if (state.answers[i] === q["אינדקס_תשובה_נכונה"]) ok += 1;
  });
  return { ok, total: questions.length };
}

function renderResults() {
  const { ok, total } = scoreTopic();
  const topics = state.bank["נושאים"] || [];
  const t = topics[state.topicIndex];
  $("result-title").textContent = t["כותרת"] || "";
  $("result-score").textContent = `${ok} / ${total}`;
  const ul = $("result-detail");
  ul.innerHTML = "";
  (t["שאלות"] || []).forEach((q, i) => {
    const li = document.createElement("li");
    const correct = q["אינדקס_תשובה_נכונה"];
    const mine = state.answers[i];
    const good = mine === correct;
    li.className = good ? "ok" : "bad";
    li.textContent = `ש${i + 1}: ${good ? "נכון" : "לא נכון"} (נבחר ${LABELS[mine] ?? "—"}, נכון ${LABELS[correct]})`;
    ul.appendChild(li);
  });
}

function goHome() {
  setRoute("home");
  showView("home");
}

function applyRoute() {
  const { view, topicId } = parseRoute();
  if (!state.bank) return;
  if (view === "home") {
    showView("home");
    return;
  }
  if (view === "quiz" && topicId) {
    const idx = findTopicIndexById(topicId);
    if (idx < 0) {
      goHome();
      return;
    }
    if (state.topicIndex !== idx || state.answers.length === 0) {
      state.topicIndex = idx;
      state.qIndex = 0;
      state.answers = [];
    }
    renderQuiz();
    showView("quiz");
    return;
  }
  if (view === "results") {
    if (state.answers.length === 0) {
      goHome();
      return;
    }
    renderResults();
    showView("results");
    return;
  }
  showView("home");
}

async function init() {
  $("bank-url-hint").textContent = bankUrl();
  await loadBank();
  if (state.loadError) {
    $("load-error").innerHTML = `<p class="err">לא ניתן לטעון את בנק השאלות (<code>${escapeHtml(bankUrl())}</code>): ${escapeHtml(state.loadError)}</p><p class="lead">הרץ שרת מקומי מתיקיית web והעתק את <code>spike_bank.json</code> לכאן, או פתח עם <code>?bank=</code> לנתיב מלא.</p>`;
    $("load-error").hidden = false;
    $("main-views").hidden = true;
    return;
  }
  $("load-error").hidden = true;
  $("main-views").hidden = false;
  renderHome();
  window.addEventListener("hashchange", applyRoute);
  applyRoute();
}

document.addEventListener("DOMContentLoaded", () => {
  $("btn-next").addEventListener("click", nextQuestion);
  $("btn-back-quiz").addEventListener("click", goHome);
  $("btn-back-results").addEventListener("click", goHome);
  init();
});
