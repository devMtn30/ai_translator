document.getElementById("confirmBtn").addEventListener("click", async () => {
  const email = document.getElementById("email").value.trim();

  if (!email) {
    alert("Please enter your email address.");
    return;
  }

  try {
    const res = await fetch("/api/forgot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email }),
    });

    const data = await res.json();
    if (data.success) {
      alert("✅ Password reset link sent! Please check your email.");
    } else {
      alert(data.message || data.error || "Failed to send reset email.");
    }
  } catch (err) {
    console.error(err);
    alert("Server error. Please try again later.");
  }
});
