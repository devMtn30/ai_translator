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
const voiceBtn = document.getElementById("voiceBtn"); // 🔊 Translate + Speak
const micBtn = document.getElementById("micBtn"); // 🎤 Speak & Translate
const navAvatar = document.querySelector(".profile-icon");
const DEFAULT_AVATAR = "../assets/avatar.png";

// const API_BASE = "https://pronocoach.duckdns.org";
const API_BASE = "http://127.0.0.1:5000";

let recorderState = null;

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

// -------------------- 2) Translate + Speak --------------------
voiceBtn.addEventListener("click", () => {
  handleRecordingFlow(voiceBtn, {
    activeLabel: "⏹ Stop",
    introMessage: "🎙 Speak now to translate.",
    onComplete: async (audioBlob) => {
      hideAudioPlayer();
      result.innerText = "⏳ Recognizing speech...";
      try {
        const translation = await transcribeAndTranslate(audioBlob);
        const { original, translatedText } = translation;
        result.innerText = formatVoiceResult(original, translatedText);
        await maybePlayTts(translatedText);
      } catch (err) {
        console.error("❌ Voice translate failed:", err);
        result.innerText = `❌ Error: ${err.message}`;
      }
    },
  });
});

// -------------------- 3) Speak + Translate (Explain + optional TTS) --------------------
micBtn.addEventListener("click", () => {
  handleRecordingFlow(micBtn, {
    activeLabel: "⏹ Stop",
    introMessage: "🎙 Speak now... tap stop when finished.",
    onComplete: async (audioBlob) => {
      hideAudioPlayer();
      result.innerText = "⏳ Recognizing speech...";
      try {
        const translation = await transcribeAndTranslate(audioBlob);
        const { original, translatedText } = translation;
        result.innerText = formatVoiceResult(original, translatedText);
        await maybePlayTts(translatedText);
      } catch (err) {
        console.error("❌ Speak+Translate failed:", err);
        result.innerText = `❌ Error: ${err.message}`;
      }
    },
  });
});

// -------------------- Shared Voice Utilities --------------------
function formatVoiceResult(original, translationText) {
  const recognized = original ? `Recognized: ${original}\n\n` : "";
  return `${recognized}${translationText || "⚠ No translation received."}`;
}

async function transcribeAndTranslate(audioBlob) {
  const formData = new FormData();
  formData.append("file", audioBlob, "speech.webm");
  const response = await fetch(`${API_BASE}/stt_explain`, { method: "POST", body: formData });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Unexpected server response (${response.status})`);
  }
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return {
    original: payload.original || "",
    translatedText: payload.translation || "",
  };
}

async function maybePlayTts(text) {
  if (!text) return;
  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `TTS failed (${res.status})`);
    }
    const blob = await res.blob();
    audioPlayer.src = URL.createObjectURL(blob);
    audioPlayer.style.display = "block";
    await audioPlayer.play().catch(() => {
      /* Autoplay might be blocked; user can play manually. */
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

function handleRecordingFlow(button, options) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("❌ Microphone not supported.");
    return;
  }

  if (button.dataset.recording === "true") {
    stopCurrentRecording();
    return;
  }

  stopCurrentRecording();
  startRecording(button, options);
}

async function startRecording(button, options) {
  const idleLabel = button.textContent;
  let state;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream);
    const audioChunks = [];

    state = { mediaRecorder, stream, button, idleLabel, options, audioChunks };
    recorderState = state;
    button.dataset.recording = "true";
    button.textContent = options.activeLabel || "⏹ Stop";
    if (options.introMessage) {
      result.innerText = options.introMessage;
    }

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(state.audioChunks, { type: "audio/webm" });
      cleanupRecorder(state);
      try {
        await options.onComplete(blob);
      } catch (err) {
        console.error("❌ Voice handling failed:", err);
        result.innerText = `❌ Error: ${err.message}`;
      }
    };

    mediaRecorder.start();
  } catch (err) {
    if (state) {
      cleanupRecorder(state);
    } else {
      resetButton(button, idleLabel);
    }
    result.innerText = "❌ Mic error: " + err.message;
  }
}

function stopCurrentRecording() {
  if (recorderState && recorderState.mediaRecorder.state !== "inactive") {
    recorderState.mediaRecorder.stop();
  }
}

function cleanupRecorder(state) {
  try {
    state.stream.getTracks().forEach((track) => track.stop());
  } catch {
    /* ignore */
  }
  resetButton(state.button, state.idleLabel);
  if (recorderState === state) {
    recorderState = null;
  }
}

function resetButton(button, idleLabel) {
  if (!button) return;
  button.dataset.recording = "false";
  button.textContent = idleLabel;
}
