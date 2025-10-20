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
    alert("Please log in first.");
    window.location.href = "/login/login.html";
    return;
  }

  try {
    const res = await fetch(`/api/profile/${encodeURIComponent(email)}`, {
      credentials: "include"
    });
    const data = await res.json();

    if (data.success && data.data && data.data.profile) {
      const profile = data.data.profile;
      document.getElementById("firstname").value = profile.firstname || "";
      document.getElementById("lastname").value = profile.lastname || "";
      document.getElementById("year").value = profile.year || "";
      document.getElementById("student_id").value = profile.student_id || "";
      document.getElementById("gender").value = profile.gender || "";
    } else {
      alert(data.message || data.error || "⚠️ Failed to load profile information.");
    }
  } catch (err) {
    console.error("❌ Error fetching profile:", err);
    alert("Error connecting to server.");
  }
});

document.getElementById("editForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const payload = {
    firstname: document.getElementById("firstname").value.trim(),
    lastname: document.getElementById("lastname").value.trim(),
    year: document.getElementById("year").value.trim(),
    student_id: document.getElementById("student_id").value.trim(),
    gender: document.getElementById("gender").value.trim()
  };

  try {
    const res = await fetch("/api/profile/update", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (data.success && data.data && data.data.profile) {
      const updatedProfile = data.data.profile;
      localStorage.setItem("authUser", JSON.stringify(updatedProfile));
      if (updatedProfile.student_id) {
        localStorage.setItem("studentId", updatedProfile.student_id);
      }
      if (updatedProfile.email) {
        localStorage.setItem("email", updatedProfile.email);
      }
      alert(data.message || "✅ Profile updated successfully!");
      window.location.href = "./profile.html";
    } else {
      alert(data.message || data.error || "❌ Update failed.");
    }
  } catch (err) {
    console.error("❌ Update error:", err);
    alert("Server error while saving changes.");
  }
});
