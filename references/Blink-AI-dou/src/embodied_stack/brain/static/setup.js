const setupState = {
  status: null,
  devices: null,
};

async function requestSetupJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401) {
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    throw new Error("operator_auth_required");
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch (_) {
      // keep default detail
    }
    throw new Error(detail);
  }
  return response.json();
}

function setupBanner(message, tone = "neutral") {
  const el = document.getElementById("setup-banner");
  el.textContent = message;
  el.className = `banner ${tone}`;
}

function renderSetupIssues(issues) {
  const container = document.getElementById("setup-issue-list");
  container.innerHTML = "";
  if (!issues.length) {
    container.innerHTML = '<div class="log-card">No blocking setup issues detected.</div>';
    return;
  }
  for (const issue of issues) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${issue.category}</strong><span>${issue.severity}</span></div>
      <div>${issue.message}</div>
      <div class="subtle">blocking=${issue.blocking ? "true" : "false"}</div>
    `;
    container.appendChild(card);
  }
}

function populateSelect(selectId, items, selectedLabel, emptyLabel) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";
  const defaultOption = document.createElement("option");
  defaultOption.value = "default";
  defaultOption.textContent = emptyLabel;
  select.appendChild(defaultOption);
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.label;
    option.textContent = item.label;
    select.appendChild(option);
  }
  if (selectedLabel && items.some((item) => item.label === selectedLabel)) {
    select.value = selectedLabel;
  } else {
    select.value = "default";
  }
}

function renderSetup() {
  const status = setupState.status || {};
  const devices = setupState.devices || {};
  document.getElementById("device-preset-input").value = status.device_preset || "internal_macbook";
  populateSelect(
    "microphone-device-input",
    devices.microphones || [],
    status.selected_microphone_label,
    "Use preset default microphone",
  );
  populateSelect(
    "camera-device-input",
    devices.cameras || [],
    status.selected_camera_label,
    "Use preset default camera",
  );
  document.getElementById("speaker-device-input").value = status.selected_speaker_label || "system_default";
  document.getElementById("setup-summary").textContent = [
    `setup=${status.setup_complete ? "complete" : "needs_review"}`,
    `auth=${status.auth_mode || "-"}`,
    `config=${status.config_source || "-"}`,
    `preset=${status.device_preset || "-"}`,
    `ollama=${status.ollama_reachable === false ? "unreachable" : "ready_or_optional"}`,
    `models=${(status.missing_models || []).length ? `missing:${status.missing_models.join(", ")}` : "ready_or_optional"}`,
    `exports=${status.export_available ? status.export_dir || "enabled" : "unavailable"}`,
  ].join(" | ");
  document.getElementById("speaker-note").textContent = devices.speaker_note || "macOS say follows the current system default output device.";
  renderSetupIssues(status.setup_issues || []);
}

async function refreshSetup() {
  setupState.status = await requestSetupJson("/api/appliance/status");
  setupState.devices = await requestSetupJson("/api/appliance/devices");
  renderSetup();
}

async function saveSetupProfile() {
  const payload = {
    setup_complete: true,
    device_preset: document.getElementById("device-preset-input").value,
    microphone_device: document.getElementById("microphone-device-input").value,
    camera_device: document.getElementById("camera-device-input").value,
    speaker_device: document.getElementById("speaker-device-input").value,
  };
  setupBanner("Saving local appliance profile…", "neutral");
  setupState.status = await requestSetupJson("/api/appliance/profile", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setupBanner("Appliance profile saved. The browser console is ready.", "success");
  await refreshSetup();
}

document.getElementById("save-setup-btn").addEventListener("click", () => {
  saveSetupProfile().catch((error) => setupBanner(`Unable to save setup: ${error.message}`, "danger"));
});

document.getElementById("open-console-btn").addEventListener("click", () => {
  window.location.assign("/console");
});

refreshSetup()
  .then(() => {
    setupBanner("Review the detected devices, save the appliance profile, then open the console.", "neutral");
  })
  .catch((error) => setupBanner(`Unable to load setup status: ${error.message}`, "danger"));
