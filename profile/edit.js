document.addEventListener("DOMContentLoaded", async () => {
  // ✅ 로그인한 사용자의 학번(student_id) 가져오기
  const studentId = localStorage.getItem("studentId");
  if (!studentId) {
    alert("Please log in first.");
    window.location.href = "/login/login.html";
    return;
  }

  // ✅ 1. 현재 프로필 정보 불러오기
  try {
    const res = await fetch(`https://pronocoach.duckdns.org/api/profile/${studentId}`);
    const data = await res.json();

    if (res.ok) {
      document.getElementById("firstname").value = data.firstname || "";
      document.getElementById("lastname").value = data.lastname || "";
      document.getElementById("year").value = data.year || "";
      document.getElementById("student_id").value = data.student_id || "";
      document.getElementById("gender").value = data.gender || "";
    } else {
      alert("⚠️ Failed to load profile information.");
    }
  } catch (err) {
    console.error("❌ Error fetching profile:", err);
    alert("Error connecting to server.");
  }
});

// ✅ 2. 수정 후 저장
document.getElementById("editForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    student_id: localStorage.getItem("studentId"),
    firstname: document.getElementById("firstname").value.trim(),
    lastname: document.getElementById("lastname").value.trim(),
    year: document.getElementById("year").value.trim(),
    gender: document.getElementById("gender").value.trim()
  };

  try {
    const res = await fetch("https://pronocoach.duckdns.org/api/profile/update", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (data.success) {
      alert("✅ Profile updated successfully!");
      window.location.href = "./profile.html"; // ✅ 자동 이동
    } else {
      alert("❌ Update failed: " + (data.message || "Unknown error"));
    }
  } catch (err) {
    console.error("❌ Update error:", err);
    alert("Server error while saving changes.");
  }
});
