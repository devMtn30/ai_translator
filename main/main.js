// ===============================
// main.js
// ===============================
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");
const historyBox = document.querySelector(".history-box");

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

document.addEventListener("DOMContentLoaded", () => {
  const history = JSON.parse(localStorage.getItem("userHistory")) || [];
  historyBox.innerHTML = "";

  if (history.length === 0) {
    historyBox.innerHTML = "<p style='text-align:center;color:#555;'>No activity yet.</p>";
  } else {
    history.forEach(item => {
      const p = document.createElement("p");
      p.textContent = "• " + item;
      p.style.margin = "4px 10px";
      p.style.color = "#000";
      historyBox.appendChild(p);
    });
  }
});
