document.getElementById("confirmBtn").addEventListener("click", async () => {
  const email = document.getElementById("email").value.trim();

  if (!email) {
    alert("Please enter your email address.");
    return;
  }

  try {
    const res = await fetch("https://pronocoach.duckdns.org/api/forgot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    const data = await res.json();
    if (res.ok) {
      alert("✅ Password reset link sent! Please check your email.");
    } else {
      alert(data.error || "Failed to send reset email.");
    }
  } catch (err) {
    console.error(err);
    alert("Server error. Please try again later.");
  }
});
