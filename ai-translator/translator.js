console.log("✅ translator.js (Explain) loaded");

// -------------------- Sidebar Control --------------------
const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

menuBtn.addEventListener("click", () => {
  sidebar.classList.add("open");
});

closeBtn.addEventListener("click", () => {
  sidebar.classList.remove("open");
});

// -------------------- Main Elements --------------------
const input = document.getElementById("inputText");
const result = document.getElementById("resultBox");
const audioPlayer = document.getElementById("audioPlayer");

const chatBtn = document.getElementById("chatBtn");
const voiceBtn = document.getElementById("voiceBtn");
const micBtn = document.getElementById("micBtn");

// const API_BASE = "https://pronocoach.duckdns.org";
const API_BASE = "http://127.0.0.1:5000";

updateWelcomeText();

async function updateWelcomeText() {
  const label = document.querySelector(".welcome-text");
  if (!label) return;

  try {
    const response = await fetch("/api/profile/me", { credentials: "include" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload?.success === false) {
      const message = payload?.message || `Request failed (${response.status})`;
      throw new Error(message);
    }
    const profile = payload.data?.profile || {};
    const displayName = profile.firstname || profile.lastname || profile.email;
    if (displayName) {
      label.textContent = `Hi, ${displayName}`;
    }
  } catch (err) {
    console.error("❌ failed to update welcome text:", err);
  }
}

// -------------------- 1) Chat Translation (Explain) --------------------
chatBtn.addEventListener("click", async () => {
  const text = input.value.trim();
  if (!text) {
    result.innerText = "⚠ Please enter text.";
    return;
  }
  result.innerText = "⏳ Translating...";
  try {
    const res = await fetch(`${API_BASE}/translate_explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    result.innerText = data.translation || "⚠ Error: " + data.error;
  } catch (err) {
    result.innerText = "❌ Server error: " + err.message;
  }
});

// -------------------- 2) Translate → TTS --------------------
voiceBtn.addEventListener("click", async () => {
  const text = input.value.trim();
  if (!text) {
    result.innerText = "⚠ Please enter text.";
    return;
  }
  try {
    const res1 = await fetch(`${API_BASE}/translate_explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const data1 = await res1.json();
    const translatedText = data1.translation;
    result.innerText = translatedText;

    const res2 = await fetch(`${API_BASE}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: translatedText })
    });
    const blob = await res2.blob();
    audioPlayer.src = URL.createObjectURL(blob);
    audioPlayer.style.display = "block";
    await audioPlayer.play();
  } catch (err) {
    result.innerText = "❌ Error: " + err.message;
  }
});

// -------------------- 3) Speech → Translation (Explain) --------------------
micBtn.addEventListener("click", async () => {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("❌ Microphone not supported.");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    let audioChunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("file", audioBlob, "speech.webm");
      result.innerText = "⏳ Recognizing speech...";
      const res = await fetch(`${API_BASE}/stt_explain`, { method: "POST", body: formData });
      const data = await res.json();
      result.innerText = data.translation || "⚠ Error: " + data.error;
    };
    mediaRecorder.start();
    result.innerText = "🎙 Speak now... (press again to stop)";
    micBtn.onclick = () => { mediaRecorder.stop(); micBtn.onclick = null; };
  } catch (err) {
    result.innerText = "❌ Mic error: " + err.message;
  }
});
