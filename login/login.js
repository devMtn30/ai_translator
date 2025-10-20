document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const identifier = document.getElementById("studentId").value.trim();
  const password = document.getElementById("password").value;

  const payload = { password };
  if (identifier.includes("@")) {
    payload.email = identifier;
  } else {
    payload.student_id = identifier;
  }

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.success) {
      const user = data.data && data.data.user ? data.data.user : {};
      localStorage.setItem("authUser", JSON.stringify(user));
      if (user.student_id) {
        localStorage.setItem("studentId", user.student_id);
      }
      if (user.email) {
        localStorage.setItem("email", user.email);
      }
      alert(data.message || "Login successful!");
      window.location.href = "../main/main.html";
    } else {
      alert(data.message || data.error || "Login failed. Please check your credentials.");
    }
  } catch (err) {
    console.error("❌ Login Error:", err);
    alert("Server connection failed.");
  }
});
