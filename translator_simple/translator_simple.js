console.log("✅ translator_simple.js loaded");

const input = document.getElementById("inputText");
const result = document.getElementById("resultBox");
const audioPlayer = document.getElementById("audioPlayer");

const chatBtn = document.getElementById("chatBtn");
const voiceBtn = document.getElementById("voiceBtn");
const micBtn = document.getElementById("micBtn");
const navAvatar = document.querySelector(".profile-icon");
const DEFAULT_AVATAR = "../assets/avatar.png";

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
    if (navAvatar) {
      navAvatar.src = profile.profile_image_url || DEFAULT_AVATAR;
    }
  } catch (err) {
    console.error("❌ failed to update welcome text:", err);
  }
}

// Chat Translation (Simple)
chatBtn.addEventListener("click", async () => {
  const text = input.value.trim();
  if (!text) {
    result.innerText = "⚠ Please enter text.";
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/translate_simple`, {
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

// Translate → TTS
voiceBtn.addEventListener("click", async () => {
  const text = input.value.trim();
  if (!text) {
    result.innerText = "⚠ Please enter text.";
    return;
  }
  try {
    hideAudioPlayer();
    const res1 = await fetch(`${API_BASE}/translate_simple`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const data1 = await res1.json();
    const translatedText = data1.translation;
    result.innerText = translatedText;

    await playTts(translatedText);
  } catch (err) {
    result.innerText = "❌ Error: " + err.message;
  }
});

// Speech → Translation (Simple)
micBtn.addEventListener("click", async () => {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("❌ Microphone not supported.");
    return;
  }
  try {
    hideAudioPlayer();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    let audioChunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
      const formData = new FormData();
      formData.append("file", audioBlob, "speech.webm");
      result.innerText = "⏳ Recognizing speech...";
      try {
        const res = await fetch(`${API_BASE}/stt_simple`, { method: "POST", body: formData });
        const data = await res.json();
        const original = data.original || "";
        const translation = data.translation || "";
        if (!res.ok) {
          throw new Error(data.error || `Request failed (${res.status})`);
        }
        const recognized = original ? `Recognized: ${original}\n\n` : "";
        result.innerText = recognized + (translation || "⚠ No translation received.");
        await playTts(translation);
      } catch (err) {
        result.innerText = "❌ Error: " + err.message;
      }
    };
    mediaRecorder.start();
    result.innerText = "🎙 Speak now... (press again to stop)";
    micBtn.onclick = () => { mediaRecorder.stop(); micBtn.onclick = null; };
  } catch (err) {
    result.innerText = "❌ Mic error: " + err.message;
  }
});

async function playTts(text) {
  if (!text) return;
  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `TTS failed (${res.status})`);
    }
    const blob = await res.blob();
    audioPlayer.src = URL.createObjectURL(blob);
    audioPlayer.style.display = "block";
    await audioPlayer.play().catch(() => {
      /* autoplay might be blocked; user can press play manually */
    });
  } catch (err) {
    console.error("❌ TTS error:", err);
    result.innerText += `\n\n⚠ TTS unavailable: ${err.message}`;
  }
}

function hideAudioPlayer() {
  try {
    audioPlayer.pause();
  } catch {
    /* ignore */
  }
  audioPlayer.removeAttribute("src");
  audioPlayer.style.display = "none";
  audioPlayer.load();
}
