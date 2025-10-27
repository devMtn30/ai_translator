console.log("✅ register.js loaded with verification code flow");

const form = document.getElementById("registerForm");
const sendCodeBtn = document.getElementById("sendCodeBtn");
const verificationSection = document.getElementById("verificationSection");
const verificationInput = document.getElementById("verificationCode");
const registerBtn = document.querySelector(".btn-register");

const RESEND_COOLDOWN_MS = 60000;
const PASSWORD_REGEX = /^(?=.*[A-Za-z])(?=.*[!@#$%^&*(),.?':{}|<>]).{8,}$/;

let codeSnapshot = null;
let resendTimerId = null;

updateSubmitAvailability();

const trackedInputs = ["firstName", "lastName", "studentId", "email", "password", "confirmPassword"];
const trackedSelects = ["year", "gender"];

trackedInputs.forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("input", handleRegistrationFieldChange);
});

trackedSelects.forEach((id) => {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener("change", handleRegistrationFieldChange);
});

sendCodeBtn.addEventListener("click", async () => {
  const payload = collectFormPayload();
  const validationError = validateFormForCode(payload);
  if (validationError) {
    alert(validationError);
    return;
  }

  const { confirm_password, ...requestBody } = payload;
  toggleSendButton(true, "Sending...");

  try {
    const res = await fetch("/api/register/send-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(requestBody),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data?.success === false) {
      const message = data?.message || data?.error || `Request failed (${res.status})`;
      throw new Error(message);
    }

    codeSnapshot = snapshotRegistrationPayload(payload);
    verificationSection.classList.remove("hidden");
    verificationInput.value = "";
    alert(data?.message || "✅ Verification code sent! Please check your email.");
    toggleSendButton(true, "Code Sent");
    startResendCooldown();
    updateSubmitAvailability();
    verificationInput.focus();
  } catch (err) {
    console.error("❌ Send code error:", err);
    alert(err.message || "Failed to send verification code. Please try again.");
    toggleSendButton(false);
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = collectFormPayload();
  const validationError = validateFormForCode(payload);
  if (validationError) {
    alert(validationError);
    return;
  }

  if (!codeSnapshot) {
    alert("Please send the verification code to your email before completing registration.");
    return;
  }

  const currentSnapshot = snapshotRegistrationPayload(payload);
  if (currentSnapshot !== codeSnapshot) {
    alert("Your registration details changed. Please request a new verification code.");
    clearVerificationState();
    return;
  }

  const code = verificationInput.value.trim();
  if (!/^\d{6}$/.test(code)) {
    alert("Please enter the 6-digit verification code from your email.");
    verificationInput.focus();
    return;
  }

  toggleSubmitButton(true);

  try {
    const res = await fetch("/api/register/verify-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        email: payload.email.trim().toLowerCase(),
        code,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data?.success === false) {
      const message = data?.message || data?.error || `Request failed (${res.status})`;
      throw new Error(message);
    }

    alert(data?.message || "✅ Registration complete! You can now log in.");
    window.location.href = "../login/login.html";
  } catch (err) {
    console.error("❌ Verification error:", err);
    alert(err.message || "Verification failed. Please try again.");
    toggleSubmitButton(false);

    if (/expired|new code|request a new/i.test(err.message || "")) {
      clearVerificationState();
    }
  }
});

function collectFormPayload() {
  return {
    firstname: document.getElementById("firstName").value.trim(),
    lastname: document.getElementById("lastName").value.trim(),
    student_id: document.getElementById("studentId").value.trim(),
    email: document.getElementById("email").value.trim(),
    password: document.getElementById("password").value,
    confirm_password: document.getElementById("confirmPassword").value,
    year: document.getElementById("year").value,
    gender: document.getElementById("gender").value,
  };
}

function validateFormForCode(payload) {
  const missing = [];
  if (!payload.firstname) missing.push("First Name");
  if (!payload.lastname) missing.push("Last Name");
  if (!payload.student_id) missing.push("Student ID");
  if (!payload.email) missing.push("Email");
  if (!payload.password) missing.push("Password");
  if (!payload.year) missing.push("Year");
  if (!payload.gender) missing.push("Gender");

  if (missing.length) {
    return `Please fill out: ${missing.join(", ")}.`;
  }

  if (!/^\d{11}$/.test(payload.student_id)) {
    return "Student ID must be exactly 11 digits.";
  }

  if (payload.password !== payload.confirm_password) {
    return "Passwords do not match!";
  }

  if (!PASSWORD_REGEX.test(payload.password)) {
    return "Password must be at least 8 characters and contain at least 1 letter and 1 special character.";
  }

  return null;
}

function snapshotRegistrationPayload(payload) {
  return JSON.stringify({
    firstname: payload.firstname,
    lastname: payload.lastname,
    student_id: payload.student_id,
    email: payload.email.trim().toLowerCase(),
    password: payload.password,
    year: payload.year,
    gender: payload.gender,
  });
}

function updateSubmitAvailability() {
  if (!registerBtn) return;
  const enabled = Boolean(codeSnapshot);
  registerBtn.disabled = !enabled;
  if (!enabled) {
    registerBtn.textContent = "Complete Registration";
  }
}

function handleRegistrationFieldChange() {
  if (!codeSnapshot) return;
  clearVerificationState();
}

function clearVerificationState() {
  codeSnapshot = null;
  verificationInput.value = "";
  verificationSection.classList.add("hidden");
  clearTimeout(resendTimerId);
  resendTimerId = null;
  toggleSendButton(false);
  updateSubmitAvailability();
}

function toggleSendButton(disabled, label) {
  if (!sendCodeBtn) return;
  sendCodeBtn.disabled = !!disabled;
  if (label) {
    sendCodeBtn.textContent = label;
  } else if (!disabled) {
    sendCodeBtn.textContent = "Send Verification Code";
  }
}

function startResendCooldown() {
  clearTimeout(resendTimerId);
  resendTimerId = window.setTimeout(() => {
    toggleSendButton(false, "Resend Verification Code");
    resendTimerId = null;
  }, RESEND_COOLDOWN_MS);
}

function toggleSubmitButton(disabled) {
  if (!registerBtn) return;
  registerBtn.disabled = !!disabled;
  registerBtn.textContent = disabled ? "Submitting..." : "Complete Registration";
}
