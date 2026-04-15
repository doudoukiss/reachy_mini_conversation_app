const presenceState = {
  refreshInFlight: false,
  timerId: null,
};
const presenceShell = window.BlinkPresenceShell;

function currentSessionId() {
  return document.getElementById("presence-session-id").value.trim();
}

function sessionIdFromQuery() {
  const params = new URLSearchParams(window.location.search);
  return params.get("session_id") || "";
}

function scheduleRefresh(delayMs = 900) {
  if (presenceState.timerId !== null) {
    window.clearTimeout(presenceState.timerId);
  }
  presenceState.timerId = window.setTimeout(() => {
    refreshPresence().catch(handleError);
  }, delayMs);
}

function renderPresence(data) {
  const shell = data.character_presence_shell || {};
  document.getElementById("presence-session-id").value = data.active_session_id || currentSessionId() || sessionIdFromQuery();
  document.getElementById("presence-headline").textContent = shell.headline || "Settled";
  document.getElementById("presence-surface-state").textContent = shell.surface_state || "idle";
  document.getElementById("presence-detail").textContent =
    shell.detail || shell.message || "Waiting for the next explicit fast-loop signal.";
  document.getElementById("presence-status-line").textContent = presenceShell.buildStatusLine(data, shell);
  document.getElementById("presence-expression").textContent = shell.expression_name || "-";
  document.getElementById("presence-gaze").textContent = shell.gaze_target || "-";
  document.getElementById("presence-gesture").textContent = shell.gesture_name || "-";
  document.getElementById("presence-animation").textContent = shell.animation_name || "-";
  document.getElementById("presence-warmth").textContent = presenceShell.formatFraction(shell.warmth);
  document.getElementById("presence-curiosity").textContent = presenceShell.formatFraction(shell.curiosity);
  document.getElementById("presence-runtime-state").textContent = data.presence_runtime?.state || "-";
  document.getElementById("presence-voice-state").textContent = data.voice_loop?.state || "-";
  document.getElementById("presence-initiative-state").textContent = [
    data.initiative_engine?.current_stage || "-",
    data.initiative_engine?.last_decision || "-",
  ].join(" / ");
  document.getElementById("presence-slow-path").textContent = shell.slow_path_active ? "active" : "clear";
  presenceShell.renderSignals(document.getElementById("presence-source-signals"), shell.source_signals || []);
  document.getElementById("presence-pose-json").textContent = presenceShell.formatJson(shell.pose || {});
  presenceShell.applyPose(document.getElementById("presence-shell-window"), shell);
}

async function refreshPresence() {
  if (presenceState.refreshInFlight) {
    return;
  }
  presenceState.refreshInFlight = true;
  try {
    const sessionId = currentSessionId() || sessionIdFromQuery();
    const params = new URLSearchParams();
    if (sessionId) {
      params.set("session_id", sessionId);
    }
    const data = await presenceShell.requestJson(`/api/operator/presence?${params.toString()}`);
    renderPresence(data);
  } finally {
    presenceState.refreshInFlight = false;
    scheduleRefresh(document.hidden ? 2400 : 900);
  }
}

function handleError(error) {
  document.getElementById("presence-status-line").textContent = `presence_refresh_error=${error.message}`;
  scheduleRefresh(2400);
}

function wireEvents() {
  const sessionInput = document.getElementById("presence-session-id");
  const querySessionId = sessionIdFromQuery();
  if (querySessionId) {
    sessionInput.value = querySessionId;
  }
  document.getElementById("presence-refresh-btn").addEventListener("click", () => {
    refreshPresence().catch(handleError);
  });
  sessionInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") {
      return;
    }
    refreshPresence().catch(handleError);
  });
  document.addEventListener("visibilitychange", () => {
    scheduleRefresh(document.hidden ? 2400 : 900);
  });
}

wireEvents();
refreshPresence().catch(handleError);
