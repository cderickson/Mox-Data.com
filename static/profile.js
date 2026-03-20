let originalProfileState = null;

function normalizeProfileValue(value, fallback = "") {
  const normalized = String(value ?? "").trim();
  return normalized || fallback;
}

function setProfileEditMode(editMode) {
  const cancelBtn = document.getElementById("CancelProfileButton");
  const editBtn = document.getElementById("EditProfileButton");
  const saveBtn = document.getElementById("SaveProfileButton");
  const usernameDisplay = document.getElementById("ProfileUsernameDisplay");
  const usernameInputWrap = document.getElementById("ProfileUsernameInput");
  const profileImageInput = document.getElementById("ProfileImageInput");

  if (cancelBtn) cancelBtn.style.display = editMode ? "block" : "none";
  if (editBtn) editBtn.style.display = editMode ? "none" : "block";
  if (saveBtn) saveBtn.style.display = editMode ? "block" : "none";
  if (usernameDisplay) usernameDisplay.style.display = editMode ? "none" : "flex";
  if (usernameInputWrap) usernameInputWrap.style.display = editMode ? "block" : "none";
  if (profileImageInput) profileImageInput.style.display = editMode ? "flex" : "none";
}

function applyProfileState(state) {
  const usernameDisplay = document.getElementById("ProfileUsernameDisplay");
  const usernameInput = document.getElementsByName("ProfileUsernameInputText")[0];
  const imageSelect = document.getElementById("ProfileImageSelect");
  const imagePreview = document.getElementById("ProfileImagePreview");

  const username = normalizeProfileValue(state?.username, "");
  const profileImage = normalizeProfileValue(state?.profileImage, "");

  if (usernameDisplay) usernameDisplay.textContent = username;
  if (usernameInput) usernameInput.value = username;
  if (imageSelect && profileImage) imageSelect.value = profileImage;
  if (imagePreview && profileImage) {
    imagePreview.src = `/static/images/profile/${encodeURIComponent(profileImage)}`;
  }
}

function readCurrentProfileState() {
  const usernameInput = document.getElementsByName("ProfileUsernameInputText")[0];
  const imageSelect = document.getElementById("ProfileImageSelect");
  return {
    username: normalizeProfileValue(usernameInput?.value, ""),
    profileImage: normalizeProfileValue(imageSelect?.value, "")
  };
}

function isProfileStateChanged(nextState) {
  if (!originalProfileState) return true;
  return (
    normalizeProfileValue(nextState.username, "") !== normalizeProfileValue(originalProfileState.username, "") ||
    normalizeProfileValue(nextState.profileImage, "") !== normalizeProfileValue(originalProfileState.profileImage, "")
  );
}

function editProfile() {
  const usernameDisplay = document.getElementById("ProfileUsernameDisplay");
  const imageSelect = document.getElementById("ProfileImageSelect");
  originalProfileState = {
    username: normalizeProfileValue(usernameDisplay?.textContent, ""),
    profileImage: normalizeProfileValue(imageSelect?.value, "")
  };
  setProfileEditMode(true);
}

function addNewUsername() {
  document.getElementById("ProfileUsernameInput").innerHTML += '<div class="col mb-1"><div class="input-group input-group"><input type="text" class="form-control" name="ProfileUsernameInputText" placeholder="Username" value=""></div></div>'
};

function cancelEditProfile() {
  if (originalProfileState) {
    applyProfileState(originalProfileState);
  }
  setProfileEditMode(false);
}

function editUserDB() {
  const nextState = readCurrentProfileState();
  if (!isProfileStateChanged(nextState)) {
    setProfileEditMode(false);
    return;
  }

  const data = { 
    //ProfileEmailInputText: document.getElementsByName("ProfileEmailInputText")[0].value, 
    //ProfileNameInputText: document.getElementsByName("ProfileNameInputText")[0].value,
    ProfileUsernameInputText: nextState.username,
    ProfileImageInputValue: nextState.profileImage,
  };

  fetch('/edit_profile', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
    .then(response => response.ok ? response.json() : Promise.reject(new Error('Failed to save profile')))
    .then(result => {
      if (!result || result.success !== true) {
        throw new Error(result?.error || 'Failed to save profile');
      }
      const appliedState = {
        username: normalizeProfileValue(result.username, nextState.username),
        profileImage: normalizeProfileValue(result.profile_image, nextState.profileImage)
      };
      originalProfileState = appliedState;
      applyProfileState(appliedState);
      setProfileEditMode(false);
    })
    .catch(error => {
      console.error('Error saving profile:', error);
      alert('Failed to save profile changes. Please try again.');
    });
}

function formatSecondsForExportStatus(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins <= 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function setExportStatusMessage(text) {
  const statusEl = document.getElementById("ExportStatusMessage");
  if (statusEl) statusEl.textContent = text;
}

async function refreshExportStatus() {
  const requestBtn = document.getElementById("ExportRequestButton");

  if (!requestBtn) return;

  try {
    const response = await fetch("/api/export/latest-status");
    if (!response.ok) throw new Error("Failed to fetch export status");

    const data = await response.json();
    const latestStatus = data.latest_status;
    const cooldownRemaining = Number(data.cooldown_remaining_seconds || 0);
    const hasActiveJob = !!data.active_job;
    const hasCompletedNonExpiredExport = (latestStatus === "completed") && !!data.download_available;

    if (hasActiveJob) {
      requestBtn.disabled = true;
      setExportStatusMessage("Export in progress. Refresh this page in a moment to check completion.");
      return;
    }

    if (hasCompletedNonExpiredExport) {
      requestBtn.disabled = cooldownRemaining > 0;
      setExportStatusMessage("Check email for download link.");
      return;
    }

    if (cooldownRemaining > 0) {
      requestBtn.disabled = true;
      setExportStatusMessage(`Export cooldown active (${formatSecondsForExportStatus(cooldownRemaining)} remaining).`);
      return;
    }

    requestBtn.disabled = false;

    if (latestStatus === "completed") {
      setExportStatusMessage("Latest export is ready. A download link was emailed to you (expires after 1 hour).");
    } else if (latestStatus === "failed") {
      setExportStatusMessage("Latest export failed. You can request a new export.");
    } else if (latestStatus === "expired") {
      setExportStatusMessage("Latest export expired. Request a new export.");
    } else if (latestStatus === "queued" || latestStatus === "running") {
      setExportStatusMessage("Export in progress.");
    } else {
      setExportStatusMessage("No export requested yet.");
    }
  } catch (error) {
    console.error("Failed to refresh export status:", error);
    setExportStatusMessage("Unable to load export status.");
  }
}

async function requestDataExport() {
  const requestBtn = document.getElementById("ExportRequestButton");
  if (requestBtn) requestBtn.disabled = true;
  setExportStatusMessage("Queuing export job...");

  try {
    const response = await fetch("/api/export/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to queue export");
    }
    setExportStatusMessage("Export queued. We will email you a download link when it is ready.");
  } catch (error) {
    console.error("Export request failed:", error);
    setExportStatusMessage(error.message || "Failed to queue export.");
  } finally {
    refreshExportStatus();
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const imageSelect = document.getElementById('ProfileImageSelect');
  const imagePreview = document.getElementById('ProfileImagePreview');
  const usernameDisplay = document.getElementById("ProfileUsernameDisplay");
  if (imageSelect && imagePreview) {
    originalProfileState = {
      username: normalizeProfileValue(usernameDisplay?.textContent, ""),
      profileImage: normalizeProfileValue(imageSelect.value, "")
    };

    imageSelect.addEventListener('change', function () {
      const fileName = imageSelect.value;
      if (!fileName) return;
      imagePreview.src = `/static/images/profile/${encodeURIComponent(fileName)}`;
    });
  }

  refreshExportStatus();
});