const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

const profileMessage = document.getElementById("profileMessage");
const profileSections = document.querySelectorAll("[data-profile-section]");
const elements = {
  name: document.querySelector("[data-profile-name]"),
  genderHeadline: document.querySelector("[data-profile-gender]"),
  firstName: document.querySelector("[data-profile-firstname]"),
  lastName: document.querySelector("[data-profile-lastname]"),
  year: document.querySelector("[data-profile-year]"),
  student: document.querySelector("[data-profile-student]"),
  genderDetail: document.querySelector("[data-profile-gender-detail]"),
  email: document.querySelector("[data-profile-email]"),
  avatar: document.querySelector("[data-profile-avatar]"),
  headerIcon: document.querySelector(".profile-icon"),
};

const editBtn = document.getElementById("editBtn");
const editModal = document.getElementById("editModal");
const editCloseBtn = document.getElementById("editCloseBtn");
const editCancelBtn = document.getElementById("editCancelBtn");
const editForm = document.getElementById("editForm");
const editSubmitBtn = document.getElementById("editSubmitBtn");
const changeAvatarBtn = document.getElementById("changeAvatarBtn");
const avatarInput = document.getElementById("avatarInput");

const DEFAULT_AVATAR =
  elements.avatar?.dataset.defaultAvatar ||
  "../assets/avatar.png";
const MAX_AVATAR_BYTES = 5 * 1024 * 1024;
const AVATAR_BUTTON_DEFAULT_TEXT = changeAvatarBtn?.textContent || "Change Photo";

let currentProfile = null;

menuBtn.addEventListener("click", () => sidebar.classList.add("open"));
closeBtn.addEventListener("click", () => sidebar.classList.remove("open"));

document.addEventListener("DOMContentLoaded", () => {
  initializeProfile();
  setupEditHandlers();
  setupAvatarUpload();
});

async function initializeProfile() {
  setProfileVisible(false);
  showMessage("Loading profile…");

  try {
    const res = await fetch("/api/profile/me", { credentials: "include" });
    if (res.status === 401) {
      window.location.href = "../login/login.html";
      return;
    }
    const payload = await res.json();
    if (!payload.success || !payload?.data?.profile) {
      throw new Error(payload.message || "Failed to load profile.");
    }

    currentProfile = payload.data.profile;
    persistProfile(currentProfile);
    renderProfile(currentProfile);
    showMessage(""); // hide
    setProfileVisible(true);
    editBtn.hidden = false;
  } catch (error) {
    console.error("Failed to load profile:", error);
    showMessage(error.message || "Unable to load profile.", "error");
    editBtn.hidden = true;
  }
}

function renderProfile(profile) {
  const fullName = [profile.firstname, profile.lastname].filter(Boolean).join(" ") || profile.email || "—";
  elements.name.textContent = fullName;

  const genderText = profile.gender || "—";
  elements.genderHeadline.textContent = genderText;
  elements.genderDetail.textContent = genderText;

  elements.firstName.textContent = profile.firstname || "—";
  elements.lastName.textContent = profile.lastname || "—";
  elements.year.textContent = profile.year || "—";
  elements.student.textContent = profile.student_id || "—";
  elements.email.textContent = profile.email || "—";

  applyAvatarSource(profile.profile_image_url);
}

function setProfileVisible(isVisible) {
  profileSections.forEach(section => {
    section.style.display = isVisible ? "" : "none";
  });
}

function showMessage(message, tone = "info") {
  if (!message) {
    profileMessage.hidden = true;
    profileMessage.textContent = "";
    profileMessage.classList.remove("profile-message--error", "profile-message--success");
    return;
  }

  profileMessage.hidden = false;
  profileMessage.textContent = message;
  profileMessage.classList.remove("profile-message--error", "profile-message--success");
  if (tone === "error") {
    profileMessage.classList.add("profile-message--error");
  } else if (tone === "success") {
    profileMessage.classList.add("profile-message--success");
  }
}

function setupEditHandlers() {
  editBtn.addEventListener("click", () => {
    if (!currentProfile) return;
    populateEditForm(currentProfile);
    openEditModal();
  });

  editCloseBtn.addEventListener("click", closeEditModal);
  editCancelBtn.addEventListener("click", closeEditModal);

  editForm.addEventListener("submit", async event => {
    event.preventDefault();
    if (!currentProfile) return;

    const formData = new FormData(editForm);
    const payload = {
      firstname: formData.get("firstname")?.trim() || "",
      lastname: formData.get("lastname")?.trim() || "",
      year: formData.get("year")?.trim() || "",
      student_id: formData.get("student_id")?.trim() || "",
      gender: formData.get("gender")?.trim() || "",
    };

    if (!payload.firstname || !payload.lastname) {
      showMessage("First and last name are required.", "error");
      return;
    }

    await submitProfileUpdate(payload);
  });
}

function populateEditForm(profile) {
  editForm.firstname.value = profile.firstname || "";
  editForm.lastname.value = profile.lastname || "";
  editForm.year.value = profile.year || "";
  editForm.student_id.value = profile.student_id || "";
  editForm.gender.value = profile.gender || "";
}

function openEditModal() {
  editModal.classList.add("open");
  editModal.setAttribute("aria-hidden", "false");
  editForm.firstname.focus();
}

function closeEditModal() {
  editModal.classList.remove("open");
  editModal.setAttribute("aria-hidden", "true");
}

async function submitProfileUpdate(payload) {
  try {
    toggleEditSubmitting(true);
    const res = await fetch("/api/profile/update", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });

    const responseBody = await res.json().catch(() => ({}));
    if (!res.ok || responseBody.success === false) {
      throw new Error(responseBody.message || "Failed to update profile.");
    }

    const updatedProfile = responseBody.data?.profile;
    if (updatedProfile) {
      currentProfile = updatedProfile;
      persistProfile(updatedProfile);
      renderProfile(updatedProfile);
    }

    showMessage("Profile updated successfully.", "success");
    closeEditModal();
  } catch (error) {
    console.error("Profile update failed:", error);
    showMessage(error.message || "Unable to save profile changes.", "error");
  } finally {
    toggleEditSubmitting(false);
  }
}

function toggleEditSubmitting(isSubmitting) {
  editSubmitBtn.disabled = isSubmitting;
  editCancelBtn.disabled = isSubmitting;
  editSubmitBtn.textContent = isSubmitting ? "Saving…" : "Save Changes";
}

function persistProfile(profile) {
  try {
    localStorage.setItem("authUser", JSON.stringify(profile));
    if (profile.student_id) {
      localStorage.setItem("studentId", profile.student_id);
    }
    if (profile.email) {
      localStorage.setItem("email", profile.email);
    }
  } catch (error) {
    console.warn("Unable to persist profile to localStorage:", error);
  }
}

function setupAvatarUpload() {
  if (!changeAvatarBtn || !avatarInput) return;

  changeAvatarBtn.addEventListener("click", () => {
    avatarInput.click();
  });

  avatarInput.addEventListener("change", async () => {
    const file = avatarInput.files?.[0];
    if (!file) return;

    if (file.size > MAX_AVATAR_BYTES) {
      showMessage("Please choose an image smaller than 5 MB.", "error");
      avatarInput.value = "";
      return;
    }

    await uploadAvatar(file);
    avatarInput.value = "";
  });
}

async function uploadAvatar(file) {
  const formData = new FormData();
  formData.append("file", file, file.name);

  try {
    toggleAvatarUploading(true);
    showMessage("Uploading photo…");
    const res = await fetch("/api/profile/avatar", {
      method: "POST",
      credentials: "include",
      body: formData,
    });

    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload?.success === false) {
      throw new Error(payload?.message || "Failed to update profile photo.");
    }

    const updatedProfile = payload.data?.profile;
    if (updatedProfile) {
      currentProfile = updatedProfile;
      persistProfile(updatedProfile);
      renderProfile(updatedProfile);
    }
    showMessage("Profile photo updated.", "success");
  } catch (error) {
    console.error("Avatar upload failed:", error);
    showMessage(error.message || "Unable to update profile photo.", "error");
  } finally {
    toggleAvatarUploading(false);
  }
}

function toggleAvatarUploading(isUploading) {
  if (changeAvatarBtn) {
    changeAvatarBtn.disabled = isUploading;
    changeAvatarBtn.textContent = isUploading ? "Uploading…" : AVATAR_BUTTON_DEFAULT_TEXT;
  }
}

function applyAvatarSource(url) {
  const fallback = url || DEFAULT_AVATAR;
  if (elements.avatar) {
    elements.avatar.src = fallback;
  }
  if (elements.headerIcon) {
    elements.headerIcon.src = fallback;
  }
}
