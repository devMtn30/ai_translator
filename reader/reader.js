// ---------------------------------------------
// reader.js (Reader last-read timestamp sync)
// ---------------------------------------------

// 사이드바
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

updateWelcomeText();

const navAvatar = document.querySelector(".profile-icon");
const DEFAULT_AVATAR = "../assets/avatar.png";

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

// "읽기" 버튼 클릭 시 책 열기
document.querySelectorAll(".read-btn").forEach(btn => {
  btn.addEventListener("click", e => {
    const card = e.target.closest(".book-card");
    const filename = card.dataset.file;
    window.location.href = `book_viewer.html?file=${encodeURIComponent(filename)}`;
  });
});

const cardLookup = Array.from(document.querySelectorAll(".book-card")).reduce((acc, card) => {
  const file = (card.dataset.file || "").toLowerCase();
  if (file) acc[file] = card;
  return acc;
}, {});

// 📡 서버에서 최근 읽기 이력 불러오기
fetch("/api/get_progress")
  .then(res => res.json())
  .then(payload => {
    if (!payload || !payload.success) {
      throw new Error(payload?.message || "Unknown error");
    }
    const history = (payload.data && payload.data.history) || [];
    history.forEach(entry => {
      const key = (entry.book_name || "").toLowerCase();
      const card = cardLookup[key];
      if (!card) return;
      const label = card.querySelector("[data-last-read]");
      if (!label) return;
      label.textContent = formatLastRead(entry.last_read_at);
    });
  })
  .catch(err => console.error("❌ failed loading reading history:", err));

function formatLastRead(isoString) {
  if (!isoString) return "Last read: Unknown";
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return "Last read: Unknown";
  return `Last read: ${parsed.toLocaleString()}`;
}
