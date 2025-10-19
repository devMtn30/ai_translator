document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();

  const studentId = document.getElementById("studentId").value.trim();
  const password = document.getElementById("password").value;

  console.log("👉 Entered studentId:", studentId);

  try {
    const res = await fetch("https://pronocoach.duckdns.org/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_id: studentId, password: password })
    });

    const data = await res.json();
    console.log("📌 Server response:", data);

    if (res.ok) {
      localStorage.setItem("studentId", studentId);
      console.log("✅ Saved studentId:", localStorage.getItem("studentId"));
      alert(data.message || "Login successful!");
      window.location.href = "../main/main.html";
    } else {
      alert(data.error || "Login failed. Please check your Student ID and password.");
    }
  } catch (err) {
    console.error("❌ Login Error:", err);
    alert("Server connection failed.");
  }
});
