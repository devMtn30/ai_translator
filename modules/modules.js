const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
const moduleCardsEl = document.getElementById("moduleCards");
const moduleTitleEl = document.getElementById("activeModuleTitle");
const moduleSummaryEl = document.getElementById("activeModuleSummary");
const moduleDialectEl = document.getElementById("activeModuleDialect");
const moduleProgressValueEl = document.getElementById("moduleProgressValue");
const moduleProgressFillEl = document.getElementById("moduleProgressFill");
const moduleProgressMetaEl = document.getElementById("moduleProgressMeta");
const stepChipsEl = document.getElementById("stepChips");
const stepContentEl = document.getElementById("stepContent");
const stepTypeLabelEl = document.getElementById("stepTypeLabel");
const stepTitleEl = document.getElementById("stepTitle");
const stepCountLabelEl = document.getElementById("stepCountLabel");
const skipBannerEl = document.getElementById("skipBanner");
const prevBtn = document.getElementById("modulePrev");
const nextBtn = document.getElementById("moduleNext");
const syncBtn = document.getElementById("syncModules");

const navAvatar = document.querySelector(".profile-icon");
const DEFAULT_AVATAR = "../assets/avatar.png";
const pageBody = document.body;

const state = {
  modules: [],
  activeModuleIndex: 0,
  stepIndex: 0,
  skipNoticeTimer: null,
  quizCache: new Map(),
  quizSession: null,
  loadingModules: false,
  autoRefreshTimer: null,
  pdfFocus: false,
  pdfFocusPreference: null,
};

menuBtn?.addEventListener("click", () => sidebar?.classList.add("open"));
closeBtn?.addEventListener("click", () => sidebar?.classList.remove("open"));
prevBtn?.addEventListener("click", () => advanceStep(-1));
nextBtn?.addEventListener("click", () => advanceStep(1));
syncBtn?.addEventListener("click", () => loadModules({ preserveSelection: true, showSkeleton: true }));

document.addEventListener("DOMContentLoaded", () => {
  updateWelcomeText();
  loadModules()
    .catch(() => {})
    .finally(() => startAutoRefresh());
});

window.addEventListener("beforeunload", () => {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
  }
  setPdfFocus(false);
});

async function updateWelcomeText() {
  const label = document.querySelector(".welcome-text");
  if (!label) return;

  try {
    const response = await fetch("/api/profile/me", { credentials: "include" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.success === false) {
      throw new Error(payload?.message || `Request failed (${response.status})`);
    }
    const profile = payload.data?.profile || {};
    const displayName = profile.firstname || profile.lastname || profile.email;
    if (displayName) {
      label.textContent = `Hi, ${displayName}`;
    }
    if (navAvatar) {
      navAvatar.src = profile.profile_image_url || DEFAULT_AVATAR;
    }
  } catch (err) {
    console.error("❌ failed to update welcome text:", err);
  }
}

async function loadModules(options = {}) {
  const {
    preserveSelection = false,
    showSkeleton = false,
    keepQuizSession = false,
    silent = false,
  } = options;

  if (state.loadingModules) {
    if (silent) {
      return;
    }
  }

  const previousModuleId = preserveSelection ? getActiveModule()?.id : null;
  const previousSignature = preserveSelection ? getCurrentStepSignature() : null;

  if (showSkeleton && moduleCardsEl) {
    moduleCardsEl.innerHTML = `
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
    `;
  }

  try {
    state.loadingModules = true;
    const payload = await fetchJSON("/api/course_modules");
    const modules = payload.data?.modules || [];
    const previousModules = state.modules;
    const hasChange = !areModulesEqual(previousModules, modules);
    state.modules = modules;
    if (hasChange) {
      state.quizCache.clear();
      if (!keepQuizSession) {
        state.quizSession = null;
      }
    } else if (!keepQuizSession) {
      state.quizSession = null;
    }

    if (!modules.length) {
      if (!silent) {
        renderEmptyModuleState("아직 등록된 모듈이 없습니다.");
      }
      return;
    }

    let nextModuleIndex = 0;
    if (previousModuleId) {
      const idx = modules.findIndex(module => module.id === previousModuleId);
      nextModuleIndex = idx >= 0 ? idx : 0;
    } else {
      const firstPending = modules.findIndex(module => (module.progress?.percentage || 0) < 100);
      nextModuleIndex = firstPending >= 0 ? firstPending : 0;
    }
    state.activeModuleIndex = nextModuleIndex;

    const activeModule = getActiveModule();
    if (!activeModule) {
      if (!silent) {
        renderEmptyModuleState("모듈 정보를 불러오지 못했습니다.");
      }
      return;
    }

    let nextStepIndex =
      typeof activeModule.actionable_step_index === "number"
        ? activeModule.actionable_step_index
        : 0;

    if (previousSignature) {
      const candidate = findStepIndexBySignature(activeModule, previousSignature);
      if (candidate >= 0) {
        nextStepIndex = candidate;
      }
    }

    const flowLength = Math.max((activeModule.flow || []).length - 1, 0);
    state.stepIndex = clamp(nextStepIndex, 0, flowLength);

    if (silent && !hasChange) {
      return;
    }

    renderModuleCards();
    renderModuleHero();
    renderStepChips();
    renderStep();
  } catch (err) {
    console.error("❌ failed to load modules:", err);
    if (!silent) {
      renderEmptyModuleState(err.message || "Unable to load modules right now.");
    }
  } finally {
    state.loadingModules = false;
  }
}

function renderEmptyModuleState(message) {
  if (moduleCardsEl) {
    moduleCardsEl.innerHTML = `<p class="empty-state">${message}</p>`;
  }
  if (stepContentEl) {
    stepContentEl.innerHTML = `<p class="empty-state">${message}</p>`;
  }
  moduleTitleEl.textContent = "Modules unavailable";
  moduleSummaryEl.textContent = message;
  moduleDialectEl.textContent = "—";
  moduleProgressValueEl.textContent = "0%";
  moduleProgressMetaEl.textContent = "0 of 0 steps complete";
  if (moduleProgressFillEl) {
    moduleProgressFillEl.style.width = "0%";
  }
  stepTypeLabelEl.textContent = "—";
  stepTitleEl.textContent = "Module data unavailable.";
  stepCountLabelEl.textContent = "Step 0 / 0";
  prevBtn.disabled = true;
  nextBtn.disabled = true;
}

function renderModuleCards() {
  if (!moduleCardsEl) return;
  moduleCardsEl.innerHTML = "";
  state.modules.forEach((module, index) => {
    const card = document.createElement("article");
    card.className = "module-card";
    if (index === state.activeModuleIndex) {
      card.classList.add("module-card--active");
    }

    const percent = formatPercent(module.progress?.percentage);
    card.innerHTML = `
      <p class="module-card__title">${module.title}</p>
      <p class="module-card__dialect">${module.dialect || ""}</p>
      <div class="module-card__progress">
        <span>${module.progress?.completed_steps || 0} / ${module.progress?.total_steps || 0} steps</span>
        <span class="progress-pill">${percent}%</span>
      </div>
    `;
    card.addEventListener("click", () => {
      if (state.activeModuleIndex === index) return;
      state.activeModuleIndex = index;
      state.stepIndex =
        typeof module.actionable_step_index === "number"
          ? module.actionable_step_index
          : 0;
      state.quizSession = null;
      setPdfFocus(false);
      renderModuleCards();
      renderModuleHero();
      renderStepChips();
      renderStep();
    });
    moduleCardsEl.appendChild(card);
  });
}

function renderModuleHero() {
  const module = getActiveModule();
  if (!module) return;
  moduleDialectEl.textContent = module.dialect || "Module";
  moduleTitleEl.textContent = module.title || "Module";
  moduleSummaryEl.textContent = module.summary || "Tap a module to start learning.";
  const percent = formatPercent(module.progress?.percentage);
  moduleProgressValueEl.textContent = `${percent}%`;
  moduleProgressMetaEl.textContent = `${module.progress?.completed_steps || 0} of ${
    module.progress?.total_steps || 0
  } steps complete`;
  if (moduleProgressFillEl) {
    moduleProgressFillEl.style.width = `${Math.min(Math.max(percent, 0), 100)}%`;
  }
}

function renderStepChips() {
  if (!stepChipsEl) return;
  const module = getActiveModule();
  if (!module || !Array.isArray(module.flow)) {
    stepChipsEl.innerHTML = "";
    return;
  }

  const actionableIndex =
    typeof module.actionable_step_index === "number" ? module.actionable_step_index : 0;

  stepChipsEl.innerHTML = "";
  module.flow.forEach((step, index) => {
    const button = document.createElement("button");
    button.className = "step-chip";
    if (index === state.stepIndex) button.classList.add("step-chip--active");
    if (step.status === "completed") button.classList.add("step-chip--done");
    const label = step.type === "course" ? "Course" : "Quiz";
    button.textContent = `${step.step_number}. ${label}`;

    const canAccess =
      step.status === "completed" || index <= actionableIndex || index <= state.stepIndex;
    button.disabled = !canAccess;

    if (canAccess) {
      button.addEventListener("click", () => {
        state.stepIndex = index;
        state.quizSession = null;
        renderStepChips();
        renderStep();
      });
    }
    stepChipsEl.appendChild(button);
  });
}

function renderStep() {
  const module = getActiveModule();
  if (!module) {
    stepContentEl.innerHTML = `<p class="empty-state">Select a module to get started.</p>`;
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    return;
  }

  const flow = module.flow || [];
  if (!flow.length) {
    stepContentEl.innerHTML = `<p class="empty-state">This module has no steps yet.</p>`;
    prevBtn.disabled = true;
    nextBtn.disabled = true;
    return;
  }

  const total = flow.length;
  state.stepIndex = clamp(state.stepIndex, 0, total - 1);
  const step = flow[state.stepIndex];

  stepTypeLabelEl.textContent = step.type === "course" ? "Course Step" : "Quiz Step";
  stepTitleEl.textContent = step.title || (step.type === "course" ? "Course" : "Quiz");
  stepCountLabelEl.textContent = `Step ${step.step_number} / ${total}`;

  prevBtn.disabled = state.stepIndex === 0;
  const nextActionableIndex = findNextActionableIndex(flow, state.stepIndex + 1);
  const canAdvance = step.status === "completed" && nextActionableIndex !== -1;
  nextBtn.disabled = !canAdvance;
  skipBannerEl.hidden = true;

  if (step.type === "course") {
    const hasPdf = Boolean(step.book?.pdf_url);
    applyPdfFocusDefault(hasPdf);
    state.quizSession = null;
    renderCourseStep(step);
  } else {
    setPdfFocus(false);
    renderQuizStep(step);
  }
}

function renderCourseStep(step) {
  const book = step.book || {};
  const badgeClass = step.status === "completed" ? "badge badge--course" : "badge badge--course";
  const lastRead = book.last_read_at ? formatTimestamp(book.last_read_at) : "Not started yet";
  const handoutMeta = [book.handout_label, book.page_range].filter(Boolean).join(" · ");

  const pdfSrc = book.pdf_url ? `${book.pdf_url}#toolbar=0&navpanes=0` : null;

  stepContentEl.innerHTML = `
    <div class="course-view__meta">
      <span class="${badgeClass}">${step.status === "completed" ? "Completed" : "PDF Lesson"}</span>
      <p class="viewer-meta">${handoutMeta || "Self-paced handout"}</p>
      <h4>${book.display_name || step.title || "Handout"}</h4>
      <p class="viewer-meta">Last marked: ${lastRead}</p>
    </div>
    ${
      pdfSrc
        ? `<iframe class="pdf-frame" title="PDF preview" src="${pdfSrc}"></iframe>`
        : `<p class="viewer-meta">PDF file not found.</p>`
    }
    <div class="course-actions">
      <button class="pill-btn pill-btn--primary js-open-pdf" ${book.file ? "" : "disabled"}>View fullscreen</button>
      <button class="pill-btn js-focus-pdf" ${book.file ? "" : "disabled"}>Focus Mode</button>
      <button class="pill-btn js-mark-course" ${
        step.status === "completed" || !book.file ? "disabled" : ""
      }>Mark as read</button>
    </div>
  `;

  const openBtn = stepContentEl.querySelector(".js-open-pdf");
  if (openBtn && book.file) {
    openBtn.addEventListener("click", () => openPdf(book.file));
  }

  const focusBtn = stepContentEl.querySelector(".js-focus-pdf");
  if (focusBtn && book.file) {
    focusBtn.addEventListener("click", () => {
      const desired = !(state.pdfFocusPreference ?? state.pdfFocus);
      state.pdfFocusPreference = desired;
      setPdfFocus(desired);
    });
  }

  const markBtn = stepContentEl.querySelector(".js-mark-course");
  if (markBtn && book.file) {
    markBtn.addEventListener("click", () => recordCourseProgress(book.file, markBtn));
  }

  updateFocusModeUI();
}

async function renderQuizStep(step) {
  setPdfFocus(false);
  const quizInfo = step.quiz || {};
  const courseId = step.course_id;
  const quizId = quizInfo.id;

  if (!courseId || !quizId) {
    stepContentEl.innerHTML = `<p class="empty-state">Quiz metadata missing for this step.</p>`;
    nextBtn.disabled = true;
    return;
  }

  if (step.status === "completed") {
    renderQuizCompletedView(step);
    return;
  }

  stepContentEl.innerHTML = `<p class="viewer-meta">Loading quiz...</p>`;
  try {
    const session = await ensureQuizSession(step);
    if (!session) {
      stepContentEl.innerHTML = `<p class="empty-state">Unable to load quiz details.</p>`;
      return;
    }
    renderQuizQuestion(step, session);
  } catch (err) {
    console.error("❌ failed to load quiz detail:", err);
    stepContentEl.innerHTML = `<p class="empty-state">${err.message || "Failed to load quiz."}</p>`;
  }
}

function renderQuizCompletedView(step) {
  const quiz = step.quiz || {};
  const courseId = step.course_id;
  const score =
    quiz.score_label ||
    (quiz.score && quiz.total_questions ? `${quiz.score}/${quiz.total_questions}` : "Submitted");
  const completedAt = quiz.completed_at ? formatTimestamp(quiz.completed_at) : "—";

  stepContentEl.innerHTML = `
    <div class="quiz-summary">
      <span class="badge badge--quiz">Completed</span>
      <h4>${quiz.title || "Quiz completed"}</h4>
      <p class="viewer-meta">Latest score: ${score}</p>
      <p class="viewer-meta">Completed at: ${completedAt}</p>
    </div>
    <div class="quiz-actions">
      <button class="pill-btn pill-btn--primary js-reset-quiz" ${courseId ? "" : "disabled"}>Reset Quiz</button>
    </div>
  `;

  const resetBtn = stepContentEl.querySelector(".js-reset-quiz");
  if (resetBtn && courseId) {
    resetBtn.addEventListener("click", () => resetQuizProgress(courseId));
  }
}

function renderQuizQuestion(step, session) {
  const quiz = session.quiz;
  const question = quiz.questions[session.currentIndex];
  if (!question) {
    stepContentEl.innerHTML = `<p class="empty-state">Quiz has no questions.</p>`;
    return;
  }
  session.locked = false;

  const total = quiz.questions.length;
  const progressText = `Question ${session.currentIndex + 1} of ${total}`;

  stepContentEl.innerHTML = `
    <div class="quiz-view__meta">
      <span class="badge badge--quiz">${step.status === "completed" ? "Completed" : "Quiz"}</span>
      <p class="quiz-progress">${progressText}</p>
      <h4>${quiz.title || step.title || "Quiz"}</h4>
      <p class="viewer-meta">${step.quiz?.description || ""}</p>
    </div>
    <div class="quiz-question">
      <p class="quiz-question__prompt">${question.prompt}</p>
      <div class="option-list">
        ${question.options
          .map(
            option => `
          <button class="option-btn" data-option-id="${option.id}">
            ${option.text}
          </button>
        `,
          )
          .join("")}
      </div>
      <div class="quiz-feedback" hidden></div>
    </div>
    <div class="quiz-actions">
      <button class="pill-btn js-reset-quiz" ${quiz.id ? "" : "disabled"}>Reset Quiz</button>
      <button class="pill-btn pill-btn--primary js-next-question" hidden>Next Question</button>
      <button class="pill-btn pill-btn--primary js-submit-quiz" hidden>Submit Quiz</button>
    </div>
  `;

  const optionButtons = Array.from(stepContentEl.querySelectorAll(".option-btn"));
  const feedbackBox = stepContentEl.querySelector(".quiz-feedback");
  const nextQuestionBtn = stepContentEl.querySelector(".js-next-question");
  const submitBtn = stepContentEl.querySelector(".js-submit-quiz");
  const resetBtn = stepContentEl.querySelector(".js-reset-quiz");

  optionButtons.forEach(button => {
    button.addEventListener("click", () => {
      handleQuizOptionClick(button, question, session, {
        feedbackBox,
        nextQuestionBtn,
        submitBtn,
      });
    });
  });

  if (resetBtn && quiz.id) {
    resetBtn.addEventListener("click", () => resetQuizProgress(quiz.id));
  }

  if (nextQuestionBtn) {
    nextQuestionBtn.addEventListener("click", () => {
      session.currentIndex += 1;
      session.locked = false;
      renderQuizQuestion(step, session);
    });
  }

  if (submitBtn) {
    submitBtn.addEventListener("click", () => {
      submitQuizResponses(step, session, submitBtn);
    });
  }
}

function handleQuizOptionClick(button, question, session, controls) {
  if (session.locked) return;
  session.locked = true;

  const selectedOptionId = Number(button.dataset.optionId);
  const correctOptionId = question.correct_option_id;
  const isCorrect = selectedOptionId === correctOptionId;

  session.responses = session.responses.filter(entry => entry.question_id !== question.id);
  session.responses.push({ question_id: question.id, option_id: selectedOptionId });

  const optionButtons = button
    .closest(".option-list")
    .querySelectorAll(".option-btn");
  optionButtons.forEach(btn => {
    const optionId = Number(btn.dataset.optionId);
    btn.classList.remove("option-btn--selected", "option-btn--correct", "option-btn--incorrect");
    if (optionId === selectedOptionId) {
      btn.classList.add("option-btn--selected");
    }
    if (optionId === correctOptionId) {
      btn.classList.add("option-btn--correct");
    } else if (optionId === selectedOptionId && optionId !== correctOptionId) {
      btn.classList.add("option-btn--incorrect");
    }
  });

  const feedbackBox = controls.feedbackBox;
  if (feedbackBox) {
    feedbackBox.hidden = false;
    feedbackBox.textContent = isCorrect ? "Correct!" : "Not quite. Try to remember the explanation.";
    feedbackBox.classList.toggle("quiz-feedback--correct", isCorrect);
    feedbackBox.classList.toggle("quiz-feedback--incorrect", !isCorrect);
  }

  const isFinalQuestion = session.currentIndex === session.quiz.questions.length - 1;
  if (controls.submitBtn) {
    controls.submitBtn.hidden = !isFinalQuestion;
  }
  if (controls.nextQuestionBtn) {
    controls.nextQuestionBtn.hidden = isFinalQuestion;
  }
}

async function submitQuizResponses(step, session, submitButton) {
  if (!session.courseId) return;
  if (session.responses.length < session.quiz.questions.length) {
    showSkipBanner("Please answer all questions before submitting.");
    return;
  }
  const originalText = submitButton.textContent;
  submitButton.textContent = "Submitting...";
  submitButton.disabled = true;
  try {
    await fetchJSON(`/api/module_courses/${session.courseId}/quiz/attempts`, {
      method: "POST",
      body: JSON.stringify({ responses: session.responses }),
    });
    showSkipBanner("Quiz submitted! Progress updated.");
    state.quizSession = null;
    await loadModules({ preserveSelection: true });
  } catch (err) {
    console.error("❌ failed to submit quiz:", err);
    showSkipBanner(err.message || "Failed to submit quiz.");
  } finally {
    submitButton.textContent = originalText;
    submitButton.disabled = false;
  }
}

function openPdf(file) {
  const url = `../reader/book_viewer.html?file=${encodeURIComponent(file)}`;
  window.open(url, "_blank", "noopener");
}

async function recordCourseProgress(bookName, button) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Saving...";
  try {
    await fetchJSON("/api/save_progress", {
      method: "POST",
      body: JSON.stringify({ book_name: bookName }),
    });
    showSkipBanner("Handout marked complete.");
    await loadModules({ preserveSelection: true, keepQuizSession: true });
  } catch (err) {
    console.error("❌ failed to record progress:", err);
    showSkipBanner(err.message || "Failed to mark handout.");
  } finally {
    button.textContent = originalText;
    button.disabled = false;
  }
}

async function resetQuizProgress(courseId) {
  if (!courseId) return;
  try {
    await fetchJSON(`/api/module_courses/${courseId}/quiz/reset`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    showSkipBanner("Quiz reset. It will appear again in the flow.");
    state.quizSession = null;
    await loadModules({ preserveSelection: true });
  } catch (err) {
    console.error("❌ failed to reset quiz:", err);
    showSkipBanner(err.message || "Unable to reset quiz.");
  }
}

function advanceStep(direction) {
  const module = getActiveModule();
  if (!module) return;
  const flow = module.flow || [];
  const total = flow.length;
  if (!total) return;

  if (direction > 0) {
    const nextIndex = findNextActionableIndex(flow, state.stepIndex + 1);
    if (nextIndex === -1) return;
    for (let i = state.stepIndex + 1; i < nextIndex; i += 1) {
      if (shouldSkipStep(flow[i])) {
        showSkipBanner(`Skipped ${flow[i].title || "quiz"} (already completed).`);
      }
    }
    state.stepIndex = nextIndex;
  } else {
    state.stepIndex = clamp(state.stepIndex - 1, 0, total - 1);
  }

  const targetStep = flow[state.stepIndex];
  if (targetStep?.type !== "quiz") {
    state.quizSession = null;
  }
  renderStepChips();
  renderStep();
}

function shouldSkipStep(step) {
  return step?.type === "quiz" && step.status === "completed";
}

function getActiveModule() {
  return state.modules[state.activeModuleIndex] || null;
}

function getCurrentStepSignature() {
  const module = getActiveModule();
  if (!module || !module.flow) return null;
  const step = module.flow[state.stepIndex];
  if (!step) return null;
  return {
    moduleId: module.id,
    courseId: step.course_id,
    type: step.type,
    quizId: step.quiz_id,
  };
}

function findStepIndexBySignature(module, signature) {
  if (!module || !signature || !Array.isArray(module.flow)) return -1;
  return module.flow.findIndex(step => {
    if (!step) return false;
    if (step.course_id !== signature.courseId) return false;
    if (signature.type && step.type !== signature.type) return false;
    if (signature.type === "quiz" && signature.quizId) {
      return step.quiz_id === signature.quizId;
    }
    return true;
  });
}

function findNextActionableIndex(flow, startIndex) {
  if (!Array.isArray(flow)) return -1;
  for (let i = startIndex; i < flow.length; i += 1) {
    if (!shouldSkipStep(flow[i])) {
      return i;
    }
  }
  return -1;
}

function areModulesEqual(prevModules, nextModules) {
  if (!Array.isArray(prevModules) || !Array.isArray(nextModules)) {
    return false;
  }
  if (prevModules.length !== nextModules.length) {
    return false;
  }
  for (let i = 0; i < prevModules.length; i += 1) {
    const prev = prevModules[i];
    const next = nextModules[i];
    if (!prev || !next) {
      return false;
    }
    if (prev.id !== next.id) {
      return false;
    }
    if (JSON.stringify(prev) !== JSON.stringify(next)) {
      return false;
    }
  }
  return true;
}

function hasActivePdf() {
  const module = getActiveModule();
  const step = module?.flow ? module.flow[state.stepIndex] : null;
  return step?.type === "course" && Boolean(step.book?.pdf_url);
}

function setPdfFocus(enabled) {
  const allowFocus = hasActivePdf();
  const normalized = Boolean(enabled && allowFocus);
  state.pdfFocus = normalized;
  pageBody.classList.toggle("modules--pdf-focus", normalized);
  updateFocusModeUI();
}

function applyPdfFocusDefault(hasPdf) {
  if (!hasPdf) {
    setPdfFocus(false);
    return;
  }
  if (state.pdfFocusPreference === null) {
    state.pdfFocusPreference = true;
  }
  const desired =
    state.pdfFocusPreference === null ? true : Boolean(state.pdfFocusPreference);
  setPdfFocus(desired);
}

function updateFocusModeUI() {
  const focusBtn = stepContentEl?.querySelector(".js-focus-pdf");
  if (focusBtn) {
    if (focusBtn.disabled) {
      focusBtn.textContent = "Focus Mode";
      focusBtn.classList.remove("pill-btn--primary");
      focusBtn.removeAttribute("aria-pressed");
      return;
    }
    focusBtn.textContent = state.pdfFocus ? "Exit Focus" : "Focus Mode";
    focusBtn.classList.toggle("pill-btn--primary", state.pdfFocus);
    focusBtn.setAttribute("aria-pressed", state.pdfFocus ? "true" : "false");
  }
}

async function ensureQuizSession(step) {
  const courseId = step?.course_id;
  if (!courseId) return null;

  if (state.quizSession && state.quizSession.courseId === courseId) {
    return state.quizSession;
  }

  const quizDetail = await loadModuleCourseQuiz(courseId);
  if (!quizDetail) return null;

  state.quizSession = {
    courseId,
    quizId: quizDetail.id,
    quiz: quizDetail,
    currentIndex: 0,
    responses: [],
    locked: false,
  };
  return state.quizSession;
}

async function loadModuleCourseQuiz(courseId) {
  if (state.quizCache.has(courseId)) {
    return state.quizCache.get(courseId);
  }
  const payload = await fetchJSON(`/api/module_courses/${courseId}/quiz`);
  const quiz = payload.data?.quiz;
  if (quiz) {
    state.quizCache.set(courseId, quiz);
  }
  return quiz;
}

function showSkipBanner(message) {
  if (!skipBannerEl) return;
  skipBannerEl.textContent = message;
  skipBannerEl.hidden = false;
  clearTimeout(state.skipNoticeTimer);
  state.skipNoticeTimer = window.setTimeout(() => {
    skipBannerEl.hidden = true;
  }, 4000);
}

function startAutoRefresh() {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
  }
  state.autoRefreshTimer = window.setInterval(() => {
    if (state.loadingModules) return;
    if (state.quizSession) return;
    if (state.pdfFocus) return;
    const module = getActiveModule();
    const step = module?.flow ? module.flow[state.stepIndex] : null;
    if (step && step.type === "course" && step.status !== "completed") {
      return;
    }
    loadModules({
      preserveSelection: true,
      keepQuizSession: true,
      silent: true,
    }).catch(err => console.error("❌ auto refresh failed:", err));
  }, 3000);
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return 0;
  }
  return Math.round(value * 10) / 10;
}

function formatTimestamp(isoString) {
  if (!isoString) return "—";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    return isoString;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function fetchJSON(url, options = {}) {
  const init = {
    credentials: "include",
    ...options,
  };
  if (init.body && !(init.body instanceof FormData)) {
    init.headers = {
      "Content-Type": "application/json",
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
