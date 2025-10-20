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
  const stored = localStorage.getItem("authUser");
  let authUser = null;
  if (stored) {
    try {
      authUser = JSON.parse(stored);
    } catch (err) {
      console.warn("Failed to parse stored user:", err);
    }
  }

  const email = authUser && authUser.email ? authUser.email : localStorage.getItem("email");
  if (!email) {
    alert("Login required.");
    window.location.href = "../login/login.html";
    return;
  }

  try {
    const res = await fetch(`/api/profile/${encodeURIComponent(email)}`, {
      credentials: "include"
    });
    const data = await res.json();

    if (data.success && data.data && data.data.profile) {
      const profile = data.data.profile;
      localStorage.setItem("authUser", JSON.stringify(profile));
      if (profile.student_id) {
        localStorage.setItem("studentId", profile.student_id);
      }
      if (profile.email) {
        localStorage.setItem("email", profile.email);
      }

      document.querySelector(".player-name").textContent =
        `${profile.firstname || ""} ${profile.lastname || ""}`.trim();
      document.querySelector(".player-gender").textContent = profile.gender || "—";

      const infoValues = document.querySelectorAll(".info-card .value");
      infoValues[0].textContent = profile.firstname || "—";
      infoValues[1].textContent = profile.lastname || "—";
      infoValues[2].textContent = profile.year ? `${profile.year} Year` : "—";
      infoValues[3].textContent = profile.student_id || "—";
      infoValues[4].textContent = profile.gender || "—";
      infoValues[5].textContent = profile.email || email;
    } else if (res.status === 403) {
      alert("You can only view your own profile.");
      window.location.href = "../main/main.html";
    } else {
      alert(data.message || data.error || "Failed to load profile.");
    }
  } catch (err) {
    console.error("❌ Profile Error:", err);
    alert("Server connection failed.");
  }

  document.getElementById("editBtn").addEventListener("click", () => {
    window.location.href = "/profile/edit.html";
  });
});
