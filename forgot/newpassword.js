// /reset/<token> 형태에서 토큰 추출
console.log("찾은 버튼:", document.getElementById("confirmPasswordBtn"));

console.log("✅ newpassword.js loaded!");

const token = window.location.pathname.split("/").pop();

document.getElementById("confirmPasswordBtn").addEventListener("click", async () => {
const pw = document.getElementById("password").value.trim();
const cpw = document.getElementById("confirm").value.trim();

  if (!pw || !cpw) { alert("Please fill in all fields."); return; }
  if (pw !== cpw) { alert("Passwords do not match."); return; }

  try {
    const res = await fetch(`/api/reset/${token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ new_password: pw }),
    });
    const data = await res.json();
    if (data.success) {
      alert(data.message || "✅ Password changed successfully!");
      window.location.href = "../login/login.html";
    } else {
      alert(data.message || data.error || "Failed to reset password.");
    }
  } catch (err) {
    console.error("❌ Reset error:", err);
    alert("Server error. Please try again later.");
  }
});
