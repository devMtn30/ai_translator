// ===============================
// main.js
// ===============================
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
const historyBox = document.querySelector(".history-box");

const BOOK_TITLES = {
  "cebuano.pdf": "Cebuano For Beginners",
  "bikol.pdf": "Bikol Grammar Notes",
  "sabayan.pdf": "Sa Bayan ng Anihan"
};

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

document.addEventListener("DOMContentLoaded", () => {
  loadHistory();
});

function loadHistory() {
  historyBox.innerHTML = "<p style='text-align:center;color:#555;'>Loading...</p>";

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
      historyBox.innerHTML = "<p style='text-align:center;color:#b91c1c;'>Unable to load history.</p>";
    });
}

function renderHistory(entries) {
  historyBox.innerHTML = "";

  if (!entries.length) {
    historyBox.innerHTML = "<p style='text-align:center;color:#555;'>No activity yet.</p>";
    return;
  }

  entries.forEach(entry => {
    const paragraph = document.createElement("p");
    paragraph.style.margin = "4px 10px";
    paragraph.style.color = "#000";

    if (entry.type === "reading") {
      const label = BOOK_TITLES[entry.book_name] || entry.book_name || "Unknown book";
      const lastRead = formatTimestamp(entry.last_read_at || entry.occurred_at);
      paragraph.textContent = `• ${label} — Last read: ${lastRead}`;
    } else if (entry.type === "quiz") {
      const completed = formatTimestamp(entry.completed_at || entry.occurred_at);
      paragraph.textContent = `• Quiz: ${entry.quiz_title} — Score ${entry.score}/${entry.total_questions} (${completed})`;
    } else {
      const time = formatTimestamp(entry.occurred_at || entry.completed_at || entry.last_read_at);
      paragraph.textContent = `• Activity — ${time}`;
    }

    historyBox.appendChild(paragraph);
  });
}

function formatTimestamp(isoString) {
  if (!isoString) return "Unknown time";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return isoString;
  return parsed.toLocaleString();
}
