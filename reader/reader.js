// ---------------------------------------------
// reader.js (Flask 세션 기반 진행률 표시)
// ---------------------------------------------

// 사이드바
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

// "읽기" 버튼 클릭 시 책 열기
document.querySelectorAll(".read-btn").forEach(btn => {
  btn.addEventListener("click", e => {
    const card = e.target.closest(".book-card");
    const filename = card.dataset.file;
    window.location.href = `book_viewer.html?file=${encodeURIComponent(filename)}`;
  });
});

// 📡 서버에서 현재 계정의 진행률 불러오기
fetch("/api/get_progress")
  .then(res => res.json())
  .then(data => {
    data.forEach(item => {
      const card = Array.from(document.querySelectorAll(".book-card"))
        .find(c => c.dataset.file.toLowerCase() === item.book_name.toLowerCase());
      if (card) {
        const progressBar = card.querySelector("progress");
        const progressText = card.querySelector(".progress-text");
        progressBar.value = item.progress;
        progressText.textContent = item.progress + "%";
      }
    });
  })
  .catch(err => console.error("❌ faild loading:", err));
