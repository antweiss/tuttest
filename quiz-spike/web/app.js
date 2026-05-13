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

/** טביעת אצבע של הבנק — אם הקובץ מתעדכן, לא משחזרים סשן ישן */
function bankFingerprint() {
  const m = state.bank?.["מטא"] || {};
  const n = m["מספר_נושאים"] ?? 0;
  const per = m["שאלות_לכל_נושא"] ?? 0;
  const topics = state.bank?.["נושאים"] || [];
  let qc = 0;
  for (const t of topics) qc += (t["שאלות"] || []).length;
  return `${n}-${per}-${qc}`;
}

function progressStorageKey(topicId) {
  return `quizSpike:v1:p:${encodeURIComponent(bankUrl())}:${topicId}`;
}

function resultsStorageKey() {
  return `quizSpike:v1:r:${encodeURIComponent(bankUrl())}`;
}

function saveQuizProgress() {
  if (!state.bank) return;
  const topics = state.bank["נושאים"] || [];
  const t = topics[state.topicIndex];
  if (!t) return;
  const hasAnswer = state.answers.some((a) => a !== undefined);
  if (!hasAnswer && state.qIndex === 0) return;
  const id = topicId(t, state.topicIndex);
  try {
    sessionStorage.setItem(
      progressStorageKey(id),
      JSON.stringify({
        bankSig: bankFingerprint(),
        topicIndex: state.topicIndex,
        topicId: id,
        qIndex: state.qIndex,
        answers: state.answers,
      }),
    );
  } catch (_) {
    /* quota / private mode */
  }
}

function loadQuizProgress(topicId) {
  try {
    const raw = sessionStorage.getItem(progressStorageKey(topicId));
    if (!raw) return null;
    const d = JSON.parse(raw);
    if (d.bankSig !== bankFingerprint()) return null;
    return d;
  } catch {
    return null;
  }
}

function clearQuizProgress(topicId) {
  try {
    sessionStorage.removeItem(progressStorageKey(topicId));
  } catch (_) {}
}

function saveQuizResults() {
  if (!state.bank) return;
  const topics = state.bank["נושאים"] || [];
  const t = topics[state.topicIndex];
  if (!t) return;
  const id = topicId(t, state.topicIndex);
  try {
    sessionStorage.setItem(
      resultsStorageKey(),
      JSON.stringify({
        bankSig: bankFingerprint(),
        topicIndex: state.topicIndex,
        topicId: id,
        answers: state.answers,
      }),
    );
  } catch (_) {}
}

function loadQuizResults() {
  try {
    const raw = sessionStorage.getItem(resultsStorageKey());
    if (!raw) return null;
    const d = JSON.parse(raw);
    if (d.bankSig !== bankFingerprint()) return null;
    return d;
  } catch {
    return null;
  }
}

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
  const id = topicId(t, topicIndex);
  clearQuizProgress(id);
  state.topicIndex = topicIndex;
  state.qIndex = 0;
  state.answers = [];
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
      saveQuizProgress();
    });
    choices.appendChild(btn);
  });
  $("btn-next").disabled = selected === undefined;
  saveQuizProgress();
}

function nextQuestion() {
  const topics = state.bank["נושאים"] || [];
  const questions = topics[state.topicIndex]["שאלות"] || [];
  if (state.qIndex < questions.length - 1) {
    state.qIndex += 1;
    renderQuiz();
  } else {
    const tid = topicId(topics[state.topicIndex], state.topicIndex);
    clearQuizProgress(tid);
    saveQuizResults();
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
    const topics = state.bank["נושאים"] || [];
    const nq = (topics[idx]["שאלות"] || []).length;
    const saved = loadQuizProgress(topicId);
    if (
      saved &&
      saved.bankSig === bankFingerprint() &&
      saved.topicIndex === idx &&
      Array.isArray(saved.answers) &&
      saved.answers.length > 0
    ) {
      state.topicIndex = idx;
      state.qIndex = Math.min(Math.max(0, saved.qIndex | 0), Math.max(0, nq - 1));
      state.answers = saved.answers.slice();
      while (state.answers.length < nq) state.answers.push(undefined);
    } else if (state.topicIndex !== idx || state.answers.length === 0) {
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
      const res = loadQuizResults();
      if (
        res &&
        res.bankSig === bankFingerprint() &&
        res.topicId &&
        typeof res.topicIndex === "number" &&
        Array.isArray(res.answers) &&
        findTopicIndexById(res.topicId) >= 0
      ) {
        state.topicIndex = res.topicIndex;
        state.answers = res.answers.slice();
      }
    }
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
