// ---------------------------------------------
// book_viewer.js (Reader activity logger)
// ---------------------------------------------

const params = new URLSearchParams(location.search);
const file = params.get("file");

const pdfFrame = document.getElementById("pdfFrame");
const lastReadLabel = document.getElementById("lastReadLabel");

if (file) {
  pdfFrame.src = `./books/${file}#toolbar=0`;
  recordReadingActivity();
} else if (lastReadLabel) {
  lastReadLabel.textContent = "No book selected";
}

function recordReadingActivity() {
  if (!file) return;
  if (lastReadLabel) {
    lastReadLabel.textContent = "Logging...";
  }

  fetch("/api/save_progress", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ book_name: file })
  })
    .then(res => res.json())
    .then(payload => {
      if (!payload || !payload.success) {
        throw new Error(payload?.message || "Failed to record reading activity.");
      }
      const lastRead = payload.data?.entry?.last_read_at || new Date().toISOString();
      updateLastReadLabel(lastRead);
    })
    .catch(err => {
      console.error("❌ failed to record reading activity:", err);
      if (lastReadLabel) {
        lastReadLabel.textContent = "Last update failed";
      }
    });
}

function updateLastReadLabel(isoString) {
  if (!lastReadLabel) return;
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    lastReadLabel.textContent = isoString;
    return;
  }
  lastReadLabel.textContent = parsed.toLocaleString();
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    recordReadingActivity();
  }
});
