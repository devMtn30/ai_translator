document.getElementById("registerForm").addEventListener("submit", async function(e) {
  e.preventDefault();

  const firstname = document.getElementById("firstName").value.trim();
  const lastname = document.getElementById("lastName").value.trim();
  const studentId = document.getElementById("studentId").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const confirmPassword = document.getElementById("confirmPassword").value;
  const year = document.getElementById("year").value;
  const gender = document.getElementById("gender").value;

  // 🔹 Password validation
  const passwordRegex = /^(?=.*[A-Za-z])(?=.*[!@#$%^&*(),.?':{}|<>]).{8,}$/;
  if (!passwordRegex.test(password)) {
    alert("Password must be at least 8 characters and contain at least 1 letter and 1 special character.");
    return;
  }

  if (password !== confirmPassword) {
    alert("Passwords do not match!");
    return;
  }

  try {
    const res = await fetch("https://pronocoach.duckdns.org/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        firstname: firstname,
        lastname: lastname,
        student_id: studentId,
        email: email,
        password: password,
        year: year,
        gender: gender
      })
    });

    const data = await res.json();

if (res.ok) {
  alert("✅ Verification email sent! Please check your inbox to verify your account.");
  window.location.href = "../login/login.html";
} else {
      alert(data.error || "Registration failed. Please try again.");
    }
  } catch (err) {
    console.error("❌ Register Error:", err);
    alert("Server error. Please try again later.");
  }
});
