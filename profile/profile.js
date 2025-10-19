const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

// Open sidebar
menuBtn.addEventListener("click", () => {
  sidebar.classList.add("open");
});

// Close sidebar
closeBtn.addEventListener("click", () => {
  sidebar.classList.remove("open");
});

// 🔹 Load profile info
document.addEventListener("DOMContentLoaded", async () => {
  const studentId = localStorage.getItem("studentId");
  if (!studentId) {
    alert("Login required.");
    window.location.href = "../login/login.html";
    return;
  }

  console.log("👉 Fetching studentId:", studentId);

  try {
    const res = await fetch(`https://pronocoach.duckdns.org/api/profile/${studentId}`);
    const data = await res.json();

    console.log("📌 Profile response:", data);

    if (res.ok) {
      // Top name/gender
      document.querySelector(".player-name").textContent = data.firstname + " " + data.lastname;
      document.querySelector(".player-gender").textContent = data.gender;

      // Info card values
      const infoValues = document.querySelectorAll(".info-card .value");
      infoValues[0].textContent = data.firstname;
      infoValues[1].textContent = data.lastname;
      infoValues[2].textContent = data.year + " Year";
      infoValues[3].textContent = data.student_id;
      infoValues[4].textContent = data.gender;
      infoValues[5].textContent = data.email;
    } else {
      alert(data.error || "Failed to load profile.");
    }
  } catch (err) {
    console.error("❌ Profile Error:", err);
    alert("Server connection failed.");
  }
  
  // profile.js 맨 아래
document.getElementById("editBtn").addEventListener("click", () => {
  // 필요에 따라 경로 조정 (예: /profile/edit.html)
  window.location.href = "/profile/edit.html";
});

  
});
