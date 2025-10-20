// ======================================
// admin.js (Demo-only admin dashboard)
// ======================================

const ADMIN_PASSWORD = "demo123";

const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

const lockScreen = document.getElementById("lockScreen");
const passwordInput = document.getElementById("passwordInput");
const unlockBtn = document.getElementById("unlockBtn");
const unlockError = document.getElementById("unlockError");

const metricCards = document.getElementById("metricCards");
const onlineCount = document.getElementById("onlineCount");
const refreshOnlineBtn = document.getElementById("refreshOnlineBtn");
const refreshUsersBtn = document.getElementById("refreshUsersBtn");
const refreshQuizzesBtn = document.getElementById("refreshQuizzesBtn");
const createQuizBtn = document.getElementById("createQuizBtn");
const userSearch = document.getElementById("userSearch");
const usersTableBody = document.getElementById("usersTableBody");
const quizList = document.getElementById("quizList");
const quizChartCanvas = document.getElementById("quizChart");
const signupChartCanvas = document.getElementById("signupChart");

let quizChartInstance = null;
let signupChartInstance = null;

const state = {
  unlocked: false,
  users: [],
  quizzes: [],
  analytics: null,
  search: "",
};

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

unlockBtn.addEventListener("click", handleUnlock);
passwordInput.addEventListener("keyup", event => {
  if (event.key === "Enter") {
    handleUnlock();
  }
});

refreshOnlineBtn.addEventListener("click", loadOnline);
refreshUsersBtn.addEventListener("click", () => loadUsers(state.search));
refreshQuizzesBtn.addEventListener("click", loadQuizzes);
createQuizBtn.addEventListener("click", handleCreateQuiz);

userSearch.addEventListener("input", debounce(event => {
  state.search = event.target.value.trim();
  loadUsers(state.search);
}, 350));

usersTableBody.addEventListener("click", event => {
  const editBtn = event.target.closest("[data-action='edit-user']");
  const verifyBtn = event.target.closest("[data-action='verify-user']");
  if (editBtn) {
    const userId = Number(editBtn.dataset.userId);
    const user = state.users.find(u => u.id === userId);
    if (user) {
      handleEditUser(user);
    }
  }
  if (verifyBtn) {
    const userId = Number(verifyBtn.dataset.userId);
    handleVerifyUser(userId);
  }
});

quizList.addEventListener("click", event => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  const quizId = Number(button.dataset.quizId);
  const quiz = state.quizzes.find(q => q.id === quizId);

  if (action === "toggle") {
    toggleQuizActive(quiz);
  } else if (action === "delete") {
    deleteQuiz(quiz);
  } else if (action === "edit") {
    editQuiz(quizId);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  passwordInput.focus();
});

function handleUnlock() {
  const inputValue = passwordInput.value.trim();
  if (!inputValue) {
    unlockError.textContent = "Please enter the demo password.";
    return;
  }
  if (inputValue !== ADMIN_PASSWORD) {
    unlockError.textContent = "Incorrect password. Try 'demo123'.";
    passwordInput.value = "";
    passwordInput.focus();
    return;
  }

  state.unlocked = true;
  lockScreen.classList.add("hidden");
  initializeDashboard();
}

function initializeDashboard() {
  Promise.all([loadAnalytics(), loadOnline(), loadUsers(state.search), loadQuizzes()]).catch(err => {
    console.error("Dashboard init failed:", err);
  });
}

async function loadAnalytics() {
  try {
    const { data } = await fetchJSON("/api/admin/analytics");
    state.analytics = data.analytics;
    renderAnalytics(data.analytics);
  } catch (error) {
    console.error("Failed to load analytics", error);
    showAlert("Failed to load analytics.");
  }
}

async function loadOnline() {
  try {
    const { data } = await fetchJSON("/api/admin/online");
    onlineCount.textContent = data.online ?? 0;
  } catch (error) {
    console.error("Failed to load online count", error);
    showAlert("Unable to fetch online users.");
  }
}

async function loadUsers(searchValue = "") {
  try {
    const params = new URLSearchParams({ limit: "200" });
    if (searchValue) params.set("search", searchValue);
    const { data } = await fetchJSON(`/api/admin/users?${params.toString()}`);
    state.users = data.users || [];
    renderUsers(state.users);
  } catch (error) {
    console.error("Failed to load users", error);
    showAlert("Unable to load users.");
  }
}

async function loadQuizzes() {
  try {
    const { data } = await fetchJSON("/api/admin/quizzes?include_inactive=1");
    state.quizzes = data.quizzes || [];
    renderQuizzes(state.quizzes);
  } catch (error) {
    console.error("Failed to load quizzes", error);
    showAlert("Unable to load quizzes.");
  }
}

function renderAnalytics(analytics) {
  const metrics = [
    {
      title: "Total Users",
      value: analytics.total_users,
    },
    {
      title: "Verified Users",
      value: analytics.verified_users,
    },
    {
      title: "New Users (7d)",
      value: analytics.new_users_last_7_days,
    },
    {
      title: "Active Sessions",
      value: analytics.active_sessions,
    },
    {
      title: "Total Quizzes",
      value: analytics.total_quizzes,
    },
    {
      title: "Attempts (24h)",
      value: analytics.attempts_last_24h,
    },
  ];

  metricCards.innerHTML = "";
  metrics.forEach(metric => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <span class="card__title">${metric.title}</span>
      <span class="card__value">${metric.value ?? 0}</span>
    `;
    metricCards.appendChild(card);
  });

  renderCharts(analytics);
}

function renderUsers(users) {
  usersTableBody.innerHTML = "";
  if (!users.length) {
    const emptyRow = document.createElement("tr");
    emptyRow.innerHTML = `<td colspan="5" style="text-align:center; padding:20px;">No users found.</td>`;
    usersTableBody.appendChild(emptyRow);
    return;
  }

  users.forEach(user => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${formatName(user)}</td>
      <td>${user.email}</td>
      <td>${user.year || "—"}</td>
      <td>${user.verified ? "✅" : "⛔"}</td>
      <td>
        <div class="table-actions">
          <button class="table-action-btn table-action-btn--edit" data-action="edit-user" data-user-id="${user.id}">Edit</button>
          ${
            user.verified
              ? ""
              : `<button class="table-action-btn table-action-btn--verify" data-action="verify-user" data-user-id="${user.id}">Mark Verified</button>`
          }
        </div>
      </td>
    `;
    usersTableBody.appendChild(tr);
  });
}

function renderQuizzes(quizzes) {
  quizList.innerHTML = "";

  if (!quizzes.length) {
    quizList.innerHTML =
      '<p style="text-align:center; margin:0; padding:20px; color:#475569;">No quizzes available yet.</p>';
    return;
  }

  quizzes.forEach(quiz => {
    const card = document.createElement("div");
    card.className = "quiz-card";
    card.innerHTML = `
      <h4 class="quiz-card__title">${quiz.title}</h4>
      <div class="quiz-card__meta">Language: ${quiz.language || "—"}</div>
      <div class="quiz-card__meta">Questions: ${quiz.question_count}</div>
      <div class="quiz-card__meta">Status: ${quiz.is_active ? "Active ✅" : "Archived ⛔"}</div>
      <div class="quiz-card__actions">
        <button class="primary" data-action="edit" data-quiz-id="${quiz.id}">Edit</button>
        <button class="secondary" data-action="toggle" data-quiz-id="${quiz.id}">
          ${quiz.is_active ? "Deactivate" : "Activate"}
        </button>
        <button class="danger" data-action="delete" data-quiz-id="${quiz.id}">Delete</button>
      </div>
    `;
    quizList.appendChild(card);
  });
}

async function handleEditUser(user) {
  const firstname = prompt("First name", user.firstname || "") ?? null;
  if (firstname === null) return;
  const lastname = prompt("Last name", user.lastname || "") ?? null;
  if (lastname === null) return;
  const year = prompt("Year level", user.year || "") ?? null;
  if (year === null) return;
  const gender = prompt("Gender", user.gender || "") ?? null;
  if (gender === null) return;
  const verified = confirm("Mark account as verified?");

  try {
    await fetchJSON(`/api/admin/users/${user.id}`, {
      method: "PUT",
      body: JSON.stringify({
        firstname,
        lastname,
        year,
        gender,
        verified,
      }),
    });
    showAlert("User updated successfully.", false);
    loadUsers(state.search);
  } catch (error) {
    console.error("Failed to update user", error);
    showAlert("Failed to update user.");
  }
}

async function handleVerifyUser(userId) {
  if (!confirm("Mark this account as verified?")) return;
  try {
    await fetchJSON(`/api/admin/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ verified: true }),
    });
    showAlert("User marked as verified.", false);
    loadUsers(state.search);
  } catch (error) {
    console.error("Failed to verify user", error);
    showAlert("Failed to mark user verified.");
  }
}

async function toggleQuizActive(quiz) {
  if (!quiz) return;
  const desired = !quiz.is_active;
  try {
    await fetchJSON(`/api/admin/quizzes/${quiz.id}`, {
      method: "PUT",
      body: JSON.stringify({ is_active: desired }),
    });
    showAlert(`Quiz ${desired ? "activated" : "archived"}.`, false);
    loadQuizzes();
  } catch (error) {
    console.error("Failed to toggle quiz", error);
    showAlert("Unable to update quiz state.");
  }
}

async function deleteQuiz(quiz) {
  if (!quiz) return;
  if (!confirm(`Delete quiz "${quiz.title}"? This cannot be undone.`)) return;
  try {
    await fetchJSON(`/api/admin/quizzes/${quiz.id}`, { method: "DELETE" });
    showAlert("Quiz removed.", false);
    loadQuizzes();
  } catch (error) {
    console.error("Failed to delete quiz", error);
    showAlert("Unable to delete quiz.");
  }
}

async function editQuiz(quizId) {
  try {
    const { data } = await fetchJSON(`/api/admin/quizzes/${quizId}`);
    const payload = await buildQuizPayload(data.quiz);
    if (!payload) return;
    await fetchJSON(`/api/admin/quizzes/${quizId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    showAlert("Quiz updated.", false);
    loadQuizzes();
  } catch (error) {
    console.error("Failed to edit quiz", error);
    showAlert("Unable to edit quiz.");
  }
}

async function handleCreateQuiz() {
  try {
    const payload = await buildQuizPayload();
    if (!payload) return;
    await fetchJSON("/api/admin/quizzes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showAlert("Quiz created.", false);
    loadQuizzes();
  } catch (error) {
    console.error("Failed to create quiz", error);
    showAlert("Unable to create quiz.");
  }
}

async function buildQuizPayload(existing) {
  const title = prompt("Quiz title", existing?.title || "");
  if (title === null || !title.trim()) return null;

  const language = prompt("Language / dialect", existing?.language || "") ?? "";
  if (language === null) return null;

  const description =
    prompt("Short description (optional)", existing?.description || "") ?? existing?.description ?? "";

  let questionCount = existing?.questions?.length || 4;
  const countInput = prompt(
    "How many questions? (1-10)",
    String(questionCount),
  );
  if (countInput === null) return null;
  questionCount = clamp(parseInt(countInput, 10) || questionCount, 1, 10);

  const questions = [];
  for (let i = 0; i < questionCount; i += 1) {
    const existingQuestion = existing?.questions?.[i];
    const promptText = prompt(`Question ${i + 1} prompt`, existingQuestion?.prompt || "");
    if (promptText === null || !promptText.trim()) {
      return null;
    }

    const explanation =
      prompt(`Explanation for question ${i + 1} (optional)`, existingQuestion?.explanation || "") ?? "";

    const options = [];
    const existingOptions = existingQuestion?.options || [];
    for (let optIndex = 0; optIndex < 4; optIndex += 1) {
      const template = existingOptions[optIndex]?.text || "";
      const optionText = prompt(
        `Question ${i + 1} - option ${optIndex + 1} (leave blank to skip)`,
        template,
      );
      if (optionText === null) {
        return null;
      }
      const trimmed = optionText.trim();
      if (!trimmed) continue;
      options.push(trimmed);
    }

    if (options.length < 2) {
      alert("Each question needs at least two answer options.");
      return null;
    }

    let defaultCorrect = 1;
    if (existingQuestion?.correct_option_id) {
      const correctOption = existingOptions.findIndex(opt => opt.id === existingQuestion.correct_option_id);
      if (correctOption >= 0) {
        defaultCorrect = correctOption + 1;
      }
    }

    const correctPrompt = prompt(
      `Which option number is correct? (1-${options.length})`,
      String(defaultCorrect),
    );
    if (correctPrompt === null) return null;
    const correctIndex = clamp(parseInt(correctPrompt, 10) || defaultCorrect, 1, options.length);

    questions.push({
      prompt: promptText.trim(),
      explanation: explanation.trim(),
      options: options.map((optText, idx) => ({
        text: optText,
        is_correct: idx + 1 === correctIndex,
      })),
    });
  }

  return {
    title: title.trim(),
    language: language.trim(),
    description: description.trim(),
    questions,
  };
}

function formatName(user) {
  const first = user.firstname || "";
  const last = user.lastname || "";
  const full = `${first} ${last}`.trim();
  return full || "—";
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function debounce(callback, delay) {
  let timeout;
  return function debounced(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => callback.apply(this, args), delay);
  };
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    const message = payload.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

function showAlert(message, isError = true) {
  const finalMessage = message || (isError ? "Something went wrong." : "Done.");
  if (isError) {
    console.warn(finalMessage);
  } else {
    console.info(finalMessage);
  }
  // For simplicity, surface via browser alert for now.
  alert(finalMessage);
}

function renderCharts(analytics) {
  if (!quizChartCanvas || !signupChartCanvas || typeof Chart === "undefined") return;

  const dailySeries = normalizeDailySeries(analytics.daily_activity);
  const labels = dailySeries.map(item => formatDateLabel(item.date));
  const quizCounts = dailySeries.map(item => item.quiz_attempts);
  const signupCounts = dailySeries.map(item => item.signups);

  const quizConfig = {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Quiz Attempts",
          data: quizCounts,
          backgroundColor: "#304ffe",
          borderRadius: 6,
          maxBarThickness: 48,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#475569", font: { size: 12 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(71, 85, 105, 0.12)", drawBorder: false },
          ticks: { color: "#475569", precision: 0, font: { size: 12 } },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1f2933",
          titleFont: { size: 13, weight: "600" },
          bodyFont: { size: 12 },
          padding: 12,
        },
      },
    },
  };

  const signupConfig = {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "New Signups",
          data: signupCounts,
          tension: 0.35,
          borderColor: "#00b894",
          backgroundColor: "rgba(0, 184, 148, 0.15)",
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#475569", font: { size: 12 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(15, 118, 110, 0.12)", drawBorder: false },
          ticks: { color: "#475569", precision: 0, font: { size: 12 } },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1f2933",
          titleFont: { size: 13, weight: "600" },
          bodyFont: { size: 12 },
          padding: 12,
        },
      },
    },
  };

  if (quizChartInstance) quizChartInstance.destroy();
  quizChartInstance = new Chart(quizChartCanvas, quizConfig);

  if (signupChartInstance) signupChartInstance.destroy();
  signupChartInstance = new Chart(signupChartCanvas, signupConfig);
}

function normalizeDailySeries(activity) {
  if (Array.isArray(activity) && activity.length) {
    return activity.map(item => ({
      date: item.date,
      quiz_attempts: item.quiz_attempts ?? 0,
      signups: item.signups ?? 0,
    }));
  }

  const today = new Date();
  const fallback = [];
  for (let offset = 6; offset >= 0; offset -= 1) {
    const date = new Date(today);
    date.setDate(today.getDate() - offset);
    fallback.push({
      date: date.toISOString().slice(0, 10),
      quiz_attempts: 0,
      signups: 0,
    });
  }
  return fallback;
}

function formatDateLabel(isoDate) {
  const parsed = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
    }).format(parsed);
  } catch (err) {
    console.warn("Failed to format date label", err);
    return isoDate;
  }
}
