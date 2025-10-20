// ===============================
// main.js
// ===============================
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
const historyGrid = document.querySelector(".history-grid");
const navAvatar = document.querySelector(".profile-icon");
const DEFAULT_AVATAR = "../assets/avatar.png";

const BOOK_TITLES = {
  "cebuano.pdf": "Cebuano For Beginners",
  "bikol.pdf": "Bikol Grammar Notes",
  "sabayan.pdf": "Sa Bayan ng Anihan"
};

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

document.addEventListener("DOMContentLoaded", () => {
  updateWelcomeText();
  loadHistory();
});

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
    if (navAvatar) {
      navAvatar.src = profile.profile_image_url || DEFAULT_AVATAR;
    }
  } catch (err) {
    console.error("❌ failed to update welcome text:", err);
  }
}

function loadHistory() {
  setHistoryMessage("Loading...", "muted");

  fetch("/api/history")
    .then(res => res.json())
    .then(payload => {
      if (!payload || !payload.success) {
        throw new Error(payload?.message || "Failed to load history.");
      }
      const history = (payload.data && payload.data.history) || [];
      renderHistory(history);
    })
    .catch(err => {
      console.error("❌ failed to load reading history:", err);
      setHistoryMessage("Unable to load history.", "error");
    });
}

function renderHistory(entries) {
  if (!historyGrid) return;
  historyGrid.innerHTML = "";

  if (!entries.length) {
    setHistoryMessage("No activity yet.", "muted");
    return;
  }

  entries.forEach(entry => {
    historyGrid.appendChild(createHistoryCard(entry));
  });
}

function setHistoryMessage(message, tone = "muted") {
  if (!historyGrid) return;
  const paragraph = document.createElement("p");
  paragraph.className = `history-message history-message--${tone}`;
  paragraph.textContent = message;
  historyGrid.innerHTML = "";
  historyGrid.appendChild(paragraph);
}

function createHistoryCard(entry) {
  const type = entry.type === "quiz" ? "quiz" : entry.type === "reading" ? "reading" : "general";
  const badgeLabel = type === "quiz" ? "Quiz" : type === "reading" ? "Reading" : "Activity";
  const timestampIso = extractTimestamp(entry);
  const displayTime = formatTimestamp(timestampIso);
  const relativeTime = formatRelativeTime(timestampIso);

  const card = document.createElement("article");
  card.className = `history-card history-card--${type}`;

  const header = document.createElement("div");
  header.className = "history-card__header";

  const badge = document.createElement("span");
  badge.className = `history-card__badge history-card__badge--${type}`;
  badge.textContent = badgeLabel;

  const time = document.createElement("time");
  time.className = "history-card__time";
  if (timestampIso) {
    time.setAttribute("datetime", timestampIso);
  }
  time.textContent = relativeTime || displayTime;
  time.title = displayTime;

  header.appendChild(badge);
  header.appendChild(time);
  card.appendChild(header);

  const title = document.createElement("h4");
  title.className = "history-card__title";
  const detail = document.createElement("p");
  detail.className = "history-card__meta";

  if (type === "reading") {
    const label = BOOK_TITLES[entry.book_name] || entry.book_name || "Unknown book";
    title.textContent = label;
    detail.textContent = `Last read on ${displayTime}`;
  } else if (type === "quiz") {
    title.textContent = entry.quiz_title || "Quiz attempt";
    const total = entry.total_questions || entry.total || 0;
    const score = typeof entry.score === "number" ? entry.score : entry.correct_answers;
    const scoreText = total ? `${score}/${total}` : `${score || 0}`;
    detail.textContent = `Score: ${scoreText}`;

    if (entry.language) {
      const pill = document.createElement("span");
      pill.className = "history-card__pill";
      pill.textContent = entry.language;
      card.appendChild(pill);
    }
  } else {
    title.textContent = entry.title || "Activity";
    detail.textContent = displayTime;
  }

  card.appendChild(title);
  card.appendChild(detail);

  if (type === "reading" && entry.progress) {
    const pill = document.createElement("span");
    pill.className = "history-card__pill history-card__pill--reading";
    pill.textContent = `Progress: ${entry.progress}`;
    card.appendChild(pill);
  }

  if (type === "quiz") {
    const completion = document.createElement("p");
    completion.className = "history-card__meta history-card__meta--muted";
    completion.textContent = `Completed: ${displayTime}`;
    card.appendChild(completion);
  } else if (relativeTime) {
    const caption = document.createElement("p");
    caption.className = "history-card__meta history-card__meta--muted";
    caption.textContent = `Updated ${relativeTime}`;
    card.appendChild(caption);
  }

  return card;
}

function formatTimestamp(isoString) {
  if (!isoString) return "Unknown time";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return isoString;
  return parsed.toLocaleString();
}

function extractTimestamp(entry) {
  return entry.occurred_at || entry.completed_at || entry.last_read_at || entry.updated_at || entry.created_at || "";
}

function formatRelativeTime(isoString) {
  if (typeof Intl === "undefined" || typeof Intl.RelativeTimeFormat === "undefined") {
    return "";
  }
  if (!isoString) return "";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return "";

  const diffMs = parsed.getTime() - Date.now();
  const diffSeconds = Math.round(diffMs / 1000);
  const absSeconds = Math.abs(diffSeconds);

  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

  if (absSeconds < 60) {
    return rtf.format(Math.round(diffSeconds), "second");
  }
  if (absSeconds < 60 * 60) {
    return rtf.format(Math.round(diffSeconds / 60), "minute");
  }
  if (absSeconds < 60 * 60 * 24) {
    return rtf.format(Math.round(diffSeconds / (60 * 60)), "hour");
  }
  if (absSeconds < 60 * 60 * 24 * 7) {
    return rtf.format(Math.round(diffSeconds / (60 * 60 * 24)), "day");
  }
  if (absSeconds < 60 * 60 * 24 * 30) {
    return rtf.format(Math.round(diffSeconds / (60 * 60 * 24 * 7)), "week");
  }
  return parsed.toLocaleDateString();
}
