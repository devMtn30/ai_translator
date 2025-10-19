// ---------------------------------------------
// book_viewer.js (Flask + localStorage 병행형)
// ---------------------------------------------

const params = new URLSearchParams(location.search);
const file = params.get("file");

const pdfFrame = document.getElementById("pdfFrame");
const percentEl = document.getElementById("percent");

if (file) pdfFrame.src = `./books/${file}#toolbar=0`;

let progress = 0;
let timer = null;

// ------------------------------
// 1️⃣ 서버에서 진행률 불러오기
// ------------------------------
fetch("/api/get_progress")
  .then(res => res.json())
  .then(data => {
    const book = data.find(b => b.book_name === file);
    if (book) progress = book.progress;
    percentEl.textContent = progress + "%";
    startTimer();

    // ✅ 히스토리 기록 (책을 열었을 때)
    const history = JSON.parse(localStorage.getItem("userHistory")) || [];
    const now = new Date().toLocaleString();
    history.unshift(`[${now}] Started reading: ${file}`);
    if (history.length > 10) history.pop();
    localStorage.setItem("userHistory", JSON.stringify(history));
  })
  .catch(err => {
    console.error("❌ failed to fetch progress:", err);
    startTimer(); // 서버 불러오기 실패해도 타이머는 작동
  });

// ------------------------------
// 2️⃣ 진행률 자동 저장 (5초마다 +1%)
// ------------------------------
function startTimer() {
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    if (progress < 100) {
      progress++;
      percentEl.textContent = progress + "%";
      saveProgress(progress);
    } else {
      clearInterval(timer);
    }
  }, 5000);
}

// ------------------------------
// 3️⃣ Flask 서버로 저장
// ------------------------------
function saveProgress(p) {
  fetch("/api/save_progress", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ book_name: file, progress: p })
  })
    .then(r => r.json())
    .then(() => console.log(`✅ ${file}: ${p}% saved to DB`))
    .catch(err => console.error("❌ failed saving:", err));
}

// ------------------------------
// 4️⃣ 페이지 닫기 / 새로고침 시 타이머 정리 + 세션 저장
// ------------------------------
window.addEventListener("beforeunload", () => {
  clearInterval(timer);
  sessionStorage.setItem(`${file}_progress`, progress);
  console.log("💾 세션에 진행률 저장 후 종료");
});

// ------------------------------
// 5️⃣ 포커스 이동 시 타이머 일시정지 / 재개
// ------------------------------
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    console.log("⏸️ 다른 탭으로 이동 - 타이머 일시정지");
    clearInterval(timer);
  } else {
    console.log("▶️ 다시 돌아옴 - 타이머 재개");
    startTimer();
  }
});
