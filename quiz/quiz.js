// ===============================
// quiz.js (dynamic quiz engine)
// ===============================

const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

const quizButtonsContainer = document.getElementById("quizButtons");
const quizStatus = document.getElementById("quizStatus");
const quizContainer = document.getElementById("quizContainer");
const questionView = document.getElementById("questionView");
const resultView = document.getElementById("resultView");
const wordDisplay = document.getElementById("wordDisplay");
const optionsContainer = document.getElementById("optionsContainer");
const title = document.querySelector(".title");
const subtitle = document.querySelector(".subtitle");

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

let quizzes = [];
let currentQuiz = null;
let currentQuestions = [];
let currentQuestionIndex = 0;
let responses = [];
let locked = false;
let nextControls = null;

const JSON_HEADERS = { "Content-Type": "application/json" };

async function updateWelcomeText() {
  const label = document.querySelector(".welcome-text");
  if (!label) return;

  try {
    const response = await fetch("/api/profile/me", { credentials: "include" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.success === false) {
      const message = payload?.message || `Request failed (${response.status})`;
      throw new Error(message);
    }
    const profile = payload.data?.profile || {};
    const displayName = profile.firstname || profile.lastname || profile.email;
    if (displayName) {
      label.textContent = `Hi, ${displayName}`;
    }
  } catch (err) {
    console.error("❌ failed to update welcome text:", err);
  }
}

function fetchJSON(url, options = {}) {
  const init = {
    credentials: "include",
    ...options,
  };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = {
      ...JSON_HEADERS,
      ...(options.headers || {}),
    };
  }
  return fetch(url, init).then(async response => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.success === false) {
      const message = payload?.message || `Request failed (${response.status})`;
      throw new Error(message);
    }
    return payload;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  updateWelcomeText();
  resetView();
  loadQuizzes();
});

function loadQuizzes() {
  quizButtonsContainer.innerHTML = "";
  quizStatus.textContent = "Loading quizzes...";

  fetchJSON("/api/quizzes")
    .then(payload => {
      quizzes = (payload.data && payload.data.quizzes) || [];
      renderQuizButtons();
    })
    .catch(err => {
      console.error("❌ failed loading quiz list:", err);
      quizStatus.textContent = err.message || "Unable to load quizzes. Please try again.";
    });
}

function renderQuizButtons() {
  quizButtonsContainer.innerHTML = "";

  if (!quizzes.length) {
    quizStatus.textContent = "No quizzes available yet.";
    return;
  }

  quizStatus.textContent = "";
  quizzes.forEach(quiz => {
    const button = document.createElement("button");
    button.className = "quiz-btn";
    button.textContent = quiz.title;
    button.addEventListener("click", () => startQuiz(quiz.id));
    quizButtonsContainer.appendChild(button);
  });
}

function startQuiz(quizId) {
  quizStatus.textContent = "Loading quiz...";
  fetchJSON(`/api/quizzes/${quizId}`)
    .then(payload => {
      const quiz = payload.data?.quiz;
      if (!quiz || !Array.isArray(quiz.questions) || !quiz.questions.length) {
        throw new Error("Quiz has no questions.");
      }
      setupQuiz(quiz);
    })
    .catch(err => {
      console.error("❌ failed loading quiz:", err);
      quizStatus.textContent = err.message || "Unable to open the quiz.";
    });
}

function setupQuiz(quiz) {
  currentQuiz = quiz;
  currentQuestions = quiz.questions;
  currentQuestionIndex = 0;
  responses = [];
  locked = false;

  title.textContent = quiz.title;
  subtitle.textContent = quiz.description || `Answer ${currentQuestions.length} questions.`;

  quizButtonsContainer.style.display = "none";
  quizStatus.textContent = "";
  quizContainer.style.display = "block";
  questionView.hidden = false;
  resultView.hidden = true;
  resultView.innerHTML = "";

  displayQuestion();
}

function displayQuestion() {
  locked = false;
  questionView.hidden = false;
  resultView.hidden = true;
  hideFeedback();
  disposeNextButton();

  const question = currentQuestions[currentQuestionIndex];
  wordDisplay.textContent = question.prompt;

  optionsContainer.innerHTML = "";
  question.options.forEach(option => {
    const button = document.createElement("button");
    button.className = "option-btn";
    button.textContent = option.text;
    button.dataset.optionId = option.id;
    button.addEventListener("click", () => handleOptionClick(button, question, option));
    optionsContainer.appendChild(button);
  });
}

function handleOptionClick(button, question, option) {
  if (locked) return;
  locked = true;

  const correctOptionId = question.correct_option_id;
  const selectedOptionId = option.id;
  const isCorrect = selectedOptionId === correctOptionId;

  responses = responses.filter(entry => entry.question_id !== question.id);
  responses.push({ question_id: question.id, option_id: selectedOptionId });

  highlightOptions(question, selectedOptionId);
  const nextAction = {
    label: currentQuestionIndex === currentQuestions.length - 1 ? "Submit Quiz" : "Next Question",
    isFinal: currentQuestionIndex === currentQuestions.length - 1,
  };
  showFeedback(question, isCorrect, nextAction);
}

function highlightOptions(question, selectedOptionId) {
  const correctOptionId = question.correct_option_id;
  optionsContainer.querySelectorAll("button").forEach(btn => {
    const optionId = Number(btn.dataset.optionId);
    btn.disabled = true;
    btn.classList.add("disabled");
    if (optionId === correctOptionId) {
      btn.classList.add("correct");
    }
    if (optionId === selectedOptionId && optionId !== correctOptionId) {
      btn.classList.add("incorrect");
    }
  });
}

function showFeedback(question, isCorrect, nextAction) {
  disposeNextButton();
  feedbackBanner.hidden = false;
  feedbackBanner.classList.remove("feedback-banner--correct", "feedback-banner--incorrect");
  feedbackBanner.classList.add(isCorrect ? "feedback-banner--correct" : "feedback-banner--incorrect");
  feedbackIcon.textContent = isCorrect ? "✅" : "❌";
  feedbackText.textContent = isCorrect ? "Correct!" : "Incorrect.";

  if (question.explanation) {
    noteBox.hidden = false;
    noteBox.innerHTML = `<p><strong>Note:</strong> ${question.explanation}</p>`;
  } else {
    noteBox.hidden = true;
    noteBox.innerHTML = "";
  }

  if (nextAction) {
    renderNextButton(nextAction);
  }
}

function hideFeedback() {
  feedbackBanner.hidden = true;
  feedbackBanner.classList.remove("feedback-banner--correct", "feedback-banner--incorrect");
  feedbackIcon.textContent = "";
  feedbackText.textContent = "";
  noteBox.hidden = true;
  noteBox.innerHTML = "";
}

function renderNextButton(nextAction) {
  disposeNextButton();
  nextControls = document.createElement("div");
  nextControls.className = "next-controls";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "next-btn next-btn--progress";
  button.textContent = nextAction.label;
  button.addEventListener(
    "click",
    () => {
      if (!locked) return;
      button.disabled = true;
      if (nextAction.isFinal) {
        submitAttempt();
      } else {
        currentQuestionIndex += 1;
        displayQuestion();
      }
    },
    { once: true },
  );
  nextControls.appendChild(button);
  questionView.appendChild(nextControls);
}

function disposeNextButton() {
  if (nextControls) {
    nextControls.remove();
    nextControls = null;
  }
}

function submitAttempt() {
  quizStatus.textContent = "Submitting quiz...";
  disposeNextButton();

  fetchJSON(`/api/quizzes/${currentQuiz.id}/attempts`, {
    method: "POST",
    body: JSON.stringify({ responses }),
  })
    .then(payload => {
      renderResults(payload.data);
    })
    .catch(err => {
      console.error("❌ failed submitting quiz:", err);
      quizStatus.textContent = err.message || "Unable to submit the quiz. Please try again.";
      locked = true;
      renderNextButton(
        {
          label: "Submit Quiz",
          isFinal: true,
        },
      );
    });
}

function renderResults(result) {
  quizStatus.textContent = "";
  const completedAt = formatTimestamp(result.completed_at);

  questionView.hidden = true;
  resultView.hidden = false;
  resultView.innerHTML = `
    <h2>${currentQuiz.title} — Results</h2>
    <p class="result-score">Your score: ${result.score} / ${result.total_questions}</p>
    <p class="result-meta">Completed at: ${completedAt}</p>
  `;

  const breakdownWrapper = document.createElement("div");
  breakdownWrapper.className = "breakdown";

  result.breakdown.forEach(item => {
    const question = currentQuestions.find(q => q.id === item.question_id);
    const correctText = getOptionText(question, item.correct_option_id);
    const selectedText = getOptionText(question, item.selected_option_id);

    const block = document.createElement("div");
    block.className = "breakdown__item";
    block.innerHTML = `
      <h3>${question?.prompt || "Question"}</h3>
      <p>Status: <strong>${item.is_correct ? "Correct" : "Wrong"}</strong></p>
      <p>Answer: ${selectedText || "No answer selected"}</p>
      <p>Correct: ${correctText || "Unknown"}</p>
      ${question?.explanation ? `<p class="breakdown__note">${question.explanation}</p>` : ""}
    `;
    breakdownWrapper.appendChild(block);
  });

  resultView.appendChild(breakdownWrapper);

  const actionWrapper = document.createElement("div");
  actionWrapper.className = "quiz-actions";

  const retryBtn = document.createElement("button");
  retryBtn.className = "next-btn";
  retryBtn.textContent = "Play Again";
  retryBtn.addEventListener("click", () => startQuiz(currentQuiz.id));

  const backBtn = document.createElement("button");
  backBtn.className = "next-btn secondary";
  backBtn.textContent = "Choose Another Quiz";
  backBtn.addEventListener("click", () => {
    resetView();
    loadQuizzes();
  });

  actionWrapper.appendChild(retryBtn);
  actionWrapper.appendChild(backBtn);
  resultView.appendChild(actionWrapper);
}

function getOptionText(question, optionId) {
  if (!question || !optionId) return null;
  const option = (question.options || []).find(opt => opt.id === optionId);
  return option ? option.text : null;
}

function resetView() {
  currentQuiz = null;
  currentQuestions = [];
  currentQuestionIndex = 0;
  responses = [];
  locked = false;
  disposeNextButton();

  title.textContent = "Welcome To Quiz";
  subtitle.textContent = "Please select a dialect";
  quizButtonsContainer.style.display = "";
  quizContainer.style.display = "none";
  quizStatus.textContent = "";
  questionView.hidden = false;
  resultView.hidden = true;
  resultView.innerHTML = "";
}

function formatTimestamp(isoString) {
  if (!isoString) return "Unknown time";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return isoString;
  return parsed.toLocaleString();
}
