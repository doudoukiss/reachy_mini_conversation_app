const companionState = {
  submitting: false,
};

function companionBanner(message, tone = "neutral") {
  const el = document.getElementById("companion-test-banner");
  el.textContent = message;
  el.className = `banner ${tone}`;
}

async function companionRequestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401) {
    window.location.assign("/login");
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
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function companionSessionId() {
  return document.getElementById("companion-session-id").value.trim() || "companion-test";
}

function companionUserId() {
  return document.getElementById("companion-user-id").value.trim() || "visitor-001";
}

function appendTurn(role, text, meta = "") {
  const transcript = document.getElementById("companion-transcript");
  const card = document.createElement("div");
  card.className = "transcript-entry";
  card.innerHTML = `
    <div class="meta-row">
      <strong>${role}</strong>
      <span>${meta}</span>
    </div>
    <div>${text || "(empty)"}</div>
  `;
  transcript.prepend(card);
}

async function ensureSession() {
  await companionRequestJson("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      session_id: companionSessionId(),
      user_id: companionUserId(),
    }),
  }).catch(async (error) => {
    const sessions = await companionRequestJson("/api/sessions");
    const exists = (sessions.items || []).some((item) => item.session_id === companionSessionId());
    if (!exists) {
      throw error;
    }
  });
}

async function refreshCompanionSummary() {
  const [health, appliance] = await Promise.all([
    companionRequestJson("/health"),
    companionRequestJson("/api/appliance/status"),
  ]);
  document.getElementById("companion-runtime-summary").textContent = [
    `text=${health.dialogue_backend || "-"}`,
    `voice=${health.tts_backend || "-"}`,
    `runtime=${appliance.runtime_mode || "-"}`,
    `setup=${appliance.setup_complete ? "complete" : "needs_review"}`,
    `camera=${appliance.selected_camera_label || "-"}`,
    `mic=${appliance.selected_microphone_label || "-"}`,
    `pending_actions=${appliance.pending_action_count || 0}`,
    `waiting_workflows=${appliance.waiting_workflow_count || 0}`,
  ].join(" | ");
}

async function sendCompanionTurn() {
  if (companionState.submitting) {
    return;
  }
  const input = document.getElementById("companion-input");
  const text = input.value.trim();
  if (!text) {
    companionBanner("Type a message first.", "warning");
    return;
  }
  companionState.submitting = true;
  input.disabled = true;
  document.getElementById("companion-send-btn").disabled = true;
  appendTurn("You", text, companionSessionId());
  companionBanner("Sending message to the companion…", "neutral");
  try {
    await ensureSession();
    const result = await companionRequestJson("/api/operator/text-turn", {
      method: "POST",
      body: JSON.stringify({
        session_id: companionSessionId(),
        input_text: text,
        voice_mode: document.getElementById("companion-voice-mode").value,
        speak_reply: document.getElementById("companion-speak-reply").checked,
      }),
    });
    appendTurn("Blink", result.response?.reply_text || "(no reply text)", result.outcome || "ok");
    input.value = "";
    await refreshCompanionSummary();
    companionBanner("Reply received.", "success");
  } catch (error) {
    appendTurn("System", `Error: ${error.message}`, "failed");
    companionBanner(`Request failed: ${error.message}`, "danger");
  } finally {
    companionState.submitting = false;
    input.disabled = false;
    document.getElementById("companion-send-btn").disabled = false;
    input.focus();
  }
}

document.getElementById("companion-send-btn").addEventListener("click", () => {
  sendCompanionTurn().catch((error) => companionBanner(`Request failed: ${error.message}`, "danger"));
});

document.getElementById("companion-input").addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    sendCompanionTurn().catch((error) => companionBanner(`Request failed: ${error.message}`, "danger"));
  }
});

document.getElementById("companion-refresh-btn").addEventListener("click", () => {
  refreshCompanionSummary().catch((error) => companionBanner(`Unable to refresh status: ${error.message}`, "danger"));
});

document.getElementById("companion-open-console-btn").addEventListener("click", () => {
  window.location.assign("/console");
});

window.addEventListener("DOMContentLoaded", () => {
  refreshCompanionSummary()
    .then(() => {
      companionBanner("Companion test page ready. Type a message and send it.", "neutral");
      document.getElementById("companion-input").focus();
    })
    .catch((error) => companionBanner(`Unable to load runtime summary: ${error.message}`, "danger"));
});
