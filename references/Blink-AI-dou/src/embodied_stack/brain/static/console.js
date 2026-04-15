const state = {
  selectedSessionId: null,
  latestSnapshot: null,
  voiceMode: "stub_demo",
  scenarios: [],
  scenes: [],
  perceptionFixtures: [],
  browserSpeechSupported: false,
  browserRecognition: null,
  browserRecognitionStartedAt: null,
  browserAudioSupported: Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder),
  browserAudioRecorder: null,
  browserAudioChunks: [],
  browserAudioStream: null,
  browserListening: false,
  browserSubmitting: false,
  browserManualStop: false,
  browserShortcutHeld: false,
  browserDevicesSupported: Boolean(navigator.mediaDevices && navigator.mediaDevices.enumerateDevices),
  browserSinkSelectionSupported:
    typeof HTMLMediaElement !== "undefined" && typeof HTMLMediaElement.prototype.setSinkId === "function",
  browserDevices: {
    audioInputs: [],
    audioOutputs: [],
    videoInputs: [],
  },
  selectedBrowserMicrophoneId: "",
  selectedBrowserSpeakerId: "",
  selectedBrowserCameraId: "",
  cameraSupported: Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
  cameraStream: null,
  uploadedImage: null,
  replayInspector: null,
  episodes: [],
  benchmarkRuns: [],
  latestDemoRuns: [],
  selectedEpisodeId: null,
  selectedIncidentId: null,
  bodySemanticLibrary: [],
  bodyServoLabCatalog: null,
  selectedServoLabJoint: "",
  actionPlaneConnectors: [],
  actionPlaneApprovals: [],
  actionPlaneHistory: [],
  actionPlaneBrowserStatus: null,
  actionPlaneWorkflows: [],
  actionPlaneWorkflowRuns: [],
  actionPlaneBundles: [],
  actionPlaneOverview: null,
  actionCenterSelection: null,
  actionCenterAnnouncedKey: null,
  applianceStatus: null,
  selectedActionBundle: null,
  lastActionBundleReplay: null,
  turnInFlight: false,
  periodicRefreshInFlight: false,
};

const pollIntervalMs = 5000;
const desktopStoryScenes = [
  "greeting_presence",
  "attentive_listening",
  "wayfinding_usefulness",
  "memory_followup",
  "safe_fallback_failure",
];
const localCompanionStoryScenes = [
  "natural_discussion",
  "observe_and_comment",
  "companion_memory_follow_up",
  "knowledge_grounded_help",
  "safe_degraded_behavior",
];
const embodiedCommandTypes = new Set([
  "set_expression",
  "set_gaze",
  "perform_gesture",
  "perform_animation",
  "safe_idle",
  "set_head_pose",
]);
const fallbackOutcomes = new Set(["safe_fallback", "fallback_reply", "error", "transport_error"]);
const browserStorageKeys = {
  microphone: "blink.console.browser.microphone",
  speaker: "blink.console.browser.speaker",
  camera: "blink.console.browser.camera",
};
const defaultConsoleSessionId = "console-live";
const preferredLgPatterns = [/lg ultrafine/i, /ultrafine/i, /display camera/i, /display audio/i];
const visualQueryPhrases = [
  "what do you see",
  "what can you see",
  "do you see",
  "can you see",
  "what do the cameras see",
  "what can the cameras see",
  "what do you see from the camera",
  "what do you see from the cameras",
  "what can you see from the camera",
  "what can you see from the cameras",
  "what's in the camera view",
  "what is in the camera view",
  "what's in the scene",
  "what is in the scene",
  "what is visible",
  "what's visible",
  "what's on the sign",
  "what is on the sign",
  "what does that say",
  "who is there",
  "is anyone there",
  "how many people",
  "what objects",
  "what do you notice",
  "what can you make out",
  "look at",
];
const actionPolicyReasonText = {
  operator_approval_required: "Blink paused because this request would perform operator-sensitive work.",
  implicit_operator_approval: "This action counts as operator-launched work, so Blink does not need a second approval.",
  local_write_allowed: "This is a low-risk local write.",
  read_only_allowed: "This is read-only.",
  proactive_local_write_preview_only: "Blink only previewed this proactive write; it will not execute it by default.",
  risk_class_rejected: "Blink blocked this request because the action class is high-risk or irreversible.",
  connector_missing: "Blink could not run this request because the connector is missing.",
  connector_unconfigured: "Blink could not run this request because the connector is not configured.",
  connector_unsupported: "Blink could not run this request because the connector does not support it.",
  policy_default_reject: "Blink blocked this request because the policy layer did not find a safe allow path.",
};

function actionPolicyReason(item) {
  if (!item) {
    return "Approval is required before this action can execute.";
  }
  const detail = item.detail || "";
  const decision = item.policy_decision || "-";
  const risk = item.request?.risk_class || "-";
  if (detail && actionPolicyReasonText[detail]) {
    return `${actionPolicyReasonText[detail]} (decision=${decision}, risk=${risk})`;
  }
  if (detail) {
    return String(detail).replaceAll("_", " ");
  }
  return `Blink paused this request for policy review. (decision=${decision}, risk=${risk})`;
}

function approvalAttentionSummary(overview, actionId) {
  return (overview?.attention_items || []).find((item) => item.kind === "approval" && item.action_id === actionId) || null;
}

async function requestJson(url, options = {}) {
  const { timeoutMs = 0, headers = {}, ...fetchOptions } = options;
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const timeoutId = controller
    ? window.setTimeout(() => controller.abort(new DOMException("request_timeout", "AbortError")), timeoutMs)
    : null;

  let response;
  try {
    response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...headers },
      signal: controller?.signal,
      ...fetchOptions,
    });
  } catch (error) {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
    if (error?.name === "AbortError" && timeoutMs > 0) {
      throw new Error(`request_timeout_after_${timeoutMs}ms`);
    }
    throw error;
  }
  if (timeoutId !== null) {
    window.clearTimeout(timeoutId);
  }

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
      if (typeof body.detail === "string" && body.detail) {
        detail = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        detail = body.detail.message || body.detail.code || JSON.stringify(body.detail);
        if (body.detail.artifact_path) {
          detail = `${detail} (${body.detail.artifact_path})`;
        }
      }
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

function liveTurnTimeoutMs({ source, voiceMode, text, hasCameraPayload }) {
  const browserLiveSource =
    source === "browser_speech_recognition" ||
    source === "browser_audio_capture" ||
    isBrowserLiveMode(voiceMode);
  if (!browserLiveSource) {
    return 25000;
  }
  if (hasCameraPayload && looksLikeVisualQuery(text)) {
    return 45000;
  }
  return 25000;
}

function banner(message, tone = "neutral") {
  const el = document.getElementById("action-banner");
  el.textContent = message;
  el.className = `banner ${tone}`;
}

function currentSessionId() {
  return document.getElementById("session-id-input").value.trim() || state.selectedSessionId || defaultConsoleSessionId;
}

function presenceShellUrl(sessionId = currentSessionId()) {
  const encoded = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return `/presence${encoded}`;
}

function performanceUrl(sessionId = currentSessionId()) {
  const encoded = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return `/performance${encoded}`;
}

function currentResponseMode() {
  return document.getElementById("response-mode-input").value;
}

function currentVoiceMode() {
  return document.getElementById("voice-mode-input").value;
}

function currentPerceptionMode() {
  return document.getElementById("perception-mode-input").value;
}

function looksLikeVisualQuery(text) {
  const lowered = String(text || "").toLowerCase().trim();
  if (!lowered) {
    return false;
  }
  if (visualQueryPhrases.some((phrase) => lowered.includes(phrase))) {
    return true;
  }
  const cameraTerms = ["camera", "cameras", "scene", "view", "visible", "sign", "screen"];
  const queryTerms = ["see", "show", "look", "notice", "there", "around", "front"];
  return cameraTerms.some((term) => lowered.includes(term)) && queryTerms.some((term) => lowered.includes(term));
}

function runtimePreferredPerceptionMode() {
  const runtime = state.latestSnapshot?.runtime || {};
  const preferred = runtime.vision_backend || runtime.perception_provider_mode || "";
  if (preferred === "ollama_vision" || preferred === "multimodal_llm") {
    return preferred;
  }
  return "";
}

function syncPerceptionModeControl(snapshot) {
  const select = document.getElementById("perception-mode-input");
  const preferred = snapshot?.runtime?.vision_backend || snapshot?.runtime?.perception_provider_mode || "";
  if (!preferred || !Array.from(select.options).some((option) => option.value === preferred)) {
    return;
  }
  if (!select.value || select.value === "stub" || select.value === "browser_snapshot") {
    select.value = preferred;
  }
}

function preferredLiveCameraPerceptionMode() {
  const selected = currentPerceptionMode();
  if (selected === "ollama_vision" || selected === "multimodal_llm") {
    return selected;
  }
  return runtimePreferredPerceptionMode() || selected;
}

function shouldPreferBrowserSpeechRecognition() {
  return state.browserSpeechSupported;
}

function currentIncidentId() {
  return document.getElementById("incident-ticket-id-input").value.trim() || state.selectedIncidentId || "";
}

function currentBodyPort() {
  return document.getElementById("body-port-input").value.trim();
}

function currentBodyBaud() {
  const raw = document.getElementById("body-baud-input").value.trim();
  return raw ? Number(raw) : null;
}

function currentBodyArmTtl() {
  const raw = document.getElementById("body-arm-ttl-input").value.trim();
  return raw ? Number(raw) : 60;
}

function currentBodySemanticSmoke() {
  return document.getElementById("body-semantic-smoke-input").value;
}

function currentBodySemanticIntensity() {
  const raw = document.getElementById("body-semantic-intensity-input").value.trim();
  return raw ? Number(raw) : 1.0;
}

function currentBodySemanticRepeatCount() {
  const raw = document.getElementById("body-semantic-repeat-input").value.trim();
  return raw ? Number(raw) : 1;
}

function currentBodyTeacherReview() {
  return document.getElementById("body-teacher-review-input").value;
}

function currentBodyTeacherNote() {
  return document.getElementById("body-teacher-note-input").value.trim() || null;
}

function currentBodyTeacherDelta() {
  const raw = document.getElementById("body-teacher-delta-input").value.trim();
  return raw ? JSON.parse(raw) : {};
}

function currentBodyApplyTuning() {
  return document.getElementById("body-apply-tuning-input").checked;
}

function currentServoLabJoint() {
  const select = document.getElementById("servo-lab-joint-select");
  return (select?.value || state.selectedServoLabJoint || "").trim();
}

function currentServoLabReferenceMode() {
  return document.getElementById("servo-lab-reference-mode-input").value;
}

function currentServoLabTargetRaw() {
  const raw = document.getElementById("servo-lab-target-raw-input").value.trim();
  return raw ? Number(raw) : null;
}

function currentServoLabStepSize() {
  const raw = document.getElementById("servo-lab-step-size-input").value.trim();
  return raw ? Number(raw) : 20;
}

function currentServoLabLabMin() {
  const raw = document.getElementById("servo-lab-lab-min-input").value.trim();
  return raw ? Number(raw) : null;
}

function currentServoLabLabMax() {
  const raw = document.getElementById("servo-lab-lab-max-input").value.trim();
  return raw ? Number(raw) : null;
}

function currentServoLabDurationMs() {
  const raw = document.getElementById("servo-lab-duration-input").value.trim();
  return raw ? Number(raw) : 600;
}

function currentServoLabSpeedOverride() {
  const raw = document.getElementById("servo-lab-speed-override-input").value.trim();
  return raw ? Number(raw) : null;
}

function currentServoLabAccelerationOverride() {
  const raw = document.getElementById("servo-lab-acceleration-override-input").value.trim();
  return raw ? Number(raw) : null;
}

function speakReplyEnabled() {
  return document.getElementById("speak-reply-input").checked;
}

function isBrowserLiveMode(mode = currentVoiceMode()) {
  return mode === "browser_live" || mode === "browser_live_macos_say";
}

function usesMacSay(mode = currentVoiceMode()) {
  return mode === "macos_say" || mode === "browser_live_macos_say";
}

function speechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function loadBrowserDeviceSelection(kind) {
  try {
    return window.localStorage.getItem(browserStorageKeys[kind]) || "";
  } catch (_) {
    return "";
  }
}

function persistBrowserDeviceSelection(kind, value) {
  try {
    if (!value) {
      window.localStorage.removeItem(browserStorageKeys[kind]);
      return;
    }
    window.localStorage.setItem(browserStorageKeys[kind], value);
  } catch (_) {
    // storage can fail in private browsing; keep in-memory fallback
  }
}

function deviceLabel(device) {
  return device?.label || `${device?.kind || "device"} ${device?.deviceId?.slice(0, 6) || ""}`.trim();
}

function choosePreferredDevice(devices, selectedId) {
  if (selectedId && devices.some((item) => item.deviceId === selectedId)) {
    return selectedId;
  }
  const lgMatch = devices.find((item) => preferredLgPatterns.some((pattern) => pattern.test(item.label || "")));
  if (lgMatch) {
    return lgMatch.deviceId;
  }
  return devices[0]?.deviceId || "";
}

function populateDeviceSelect(selectId, devices, selectedId, emptyLabel) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";
  if (!devices.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = emptyLabel;
    select.appendChild(option);
    select.disabled = true;
    return "";
  }
  for (const item of devices) {
    const option = document.createElement("option");
    option.value = item.deviceId;
    option.textContent = deviceLabel(item);
    select.appendChild(option);
  }
  select.disabled = false;
  const resolved = choosePreferredDevice(devices, selectedId);
  select.value = resolved;
  return resolved;
}

async function refreshBrowserDevices() {
  if (!state.browserDevicesSupported) {
    document.getElementById("browser-device-note").textContent =
      "Browser media device enumeration is unavailable here. Typed input remains the fallback.";
    document.getElementById("browser-camera-device-note").textContent =
      "Browser camera enumeration is unavailable here.";
    updateLiveControlAvailability();
    return;
  }

  const devices = await navigator.mediaDevices.enumerateDevices();
  state.browserDevices = {
    audioInputs: devices.filter((item) => item.kind === "audioinput"),
    audioOutputs: devices.filter((item) => item.kind === "audiooutput"),
    videoInputs: devices.filter((item) => item.kind === "videoinput"),
  };
  state.selectedBrowserMicrophoneId = populateDeviceSelect(
    "browser-microphone-input",
    state.browserDevices.audioInputs,
    state.selectedBrowserMicrophoneId,
    "No browser microphone found",
  );
  state.selectedBrowserCameraId = populateDeviceSelect(
    "browser-camera-input",
    state.browserDevices.videoInputs,
    state.selectedBrowserCameraId,
    "No browser camera found",
  );

  const speakerLabel = document.getElementById("browser-speaker-label");
  if (!state.browserSinkSelectionSupported) {
    speakerLabel.classList.add("hidden");
    state.selectedBrowserSpeakerId = "";
  } else {
    speakerLabel.classList.remove("hidden");
    state.selectedBrowserSpeakerId = populateDeviceSelect(
      "browser-speaker-input",
      state.browserDevices.audioOutputs,
      state.selectedBrowserSpeakerId,
      "System default output",
    );
  }

  persistBrowserDeviceSelection("microphone", state.selectedBrowserMicrophoneId);
  persistBrowserDeviceSelection("camera", state.selectedBrowserCameraId);
  persistBrowserDeviceSelection("speaker", state.selectedBrowserSpeakerId);

  document.getElementById("browser-device-note").textContent = [
    `mic=${state.selectedBrowserMicrophoneId ? deviceLabel(state.browserDevices.audioInputs.find((item) => item.deviceId === state.selectedBrowserMicrophoneId)) : "-"}`,
    state.browserSinkSelectionSupported
      ? `speaker=${state.selectedBrowserSpeakerId ? deviceLabel(state.browserDevices.audioOutputs.find((item) => item.deviceId === state.selectedBrowserSpeakerId)) : "system_default"}`
      : "speaker=system_default_only",
    usesMacSay() ? "reply_audio=system_default_output" : "reply_audio=browser_or_stub",
  ].join(" | ");
  document.getElementById("browser-camera-device-note").textContent = [
    `camera=${state.selectedBrowserCameraId ? deviceLabel(state.browserDevices.videoInputs.find((item) => item.deviceId === state.selectedBrowserCameraId)) : "-"}`,
    "browser_camera_capture=getUserMedia",
  ].join(" | ");
  updateLiveControlAvailability();
}

function selectedBrowserMicrophoneLabel() {
  return deviceLabel(state.browserDevices.audioInputs.find((item) => item.deviceId === state.selectedBrowserMicrophoneId));
}

function selectedBrowserCameraLabel() {
  return deviceLabel(state.browserDevices.videoInputs.find((item) => item.deviceId === state.selectedBrowserCameraId));
}

async function loadScenarios() {
  const data = await requestJson("/api/scenarios");
  state.scenarios = data.items;
  const container = document.getElementById("scenario-buttons");
  container.innerHTML = "";
  for (const item of data.items) {
    const button = document.createElement("button");
    button.textContent = `Run ${item.name}`;
    button.addEventListener("click", () => runScenario(item.name));
    container.appendChild(button);
  }
}

async function loadScenes() {
  const data = await requestJson("/api/operator/investor-scenes");
  state.scenes = data.items;
  const container = document.getElementById("scene-buttons");
  container.innerHTML = "";
  for (const item of data.items) {
    const button = document.createElement("button");
    button.textContent = item.title;
    button.addEventListener("click", () => runScene(item.scene_name, item.session_id));
    container.appendChild(button);
  }
}

async function loadPerceptionFixtures() {
  const data = await requestJson("/api/operator/perception/fixtures");
  state.perceptionFixtures = data.items;
  const select = document.getElementById("perception-fixture-input");
  select.innerHTML = "";
  if (!data.items.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No built-in fixtures found";
    select.appendChild(option);
    return;
  }
  for (const item of data.items) {
    const option = document.createElement("option");
    option.value = item.fixture_path;
    option.textContent = item.title;
    select.appendChild(option);
  }
}

async function loadEpisodes(selectedEpisodeId = state.selectedEpisodeId) {
  const data = await requestJson("/api/operator/episodes");
  state.episodes = data.items || [];
  renderEpisodes(state.episodes);
  if (selectedEpisodeId) {
    const match = state.episodes.find((item) => item.episode_id === selectedEpisodeId);
    if (match) {
      await inspectEpisode(selectedEpisodeId);
      return;
    }
  }
  if (!state.episodes.length) {
    renderJson("episode-json", null);
  }
}

async function loadBenchmarks() {
  const data = await requestJson("/api/operator/benchmarks");
  state.benchmarkRuns = data.runs || [];
  renderBenchmarkRuns(state.benchmarkRuns);
}

function actionCenterSelectionKey(item) {
  if (!item) {
    return null;
  }
  const detailRef = typeof item.detail_ref === "object" && item.detail_ref !== null
    ? JSON.stringify(item.detail_ref)
    : (item.detail_ref || "-");
  return [
    item.kind || "item",
    item.action_id || "-",
    item.workflow_run_id || "-",
    item.bundle_id || "-",
    item.session_id || "-",
    detailRef,
  ].join(":");
}

function currentActionCenterKey() {
  return actionCenterSelectionKey(state.actionCenterSelection);
}

function setActionCenterSelection(item) {
  state.actionCenterSelection = item
    ? {
        kind: item.kind || null,
        severity: item.severity || null,
        title: item.title || null,
        summary: item.summary || null,
        action_id: item.action_id || null,
        workflow_run_id: item.workflow_run_id || null,
        bundle_id: item.bundle_id || null,
        session_id: item.session_id || null,
        next_step_hint: item.next_step_hint || null,
        detail_ref: item.detail_ref || null,
      }
    : null;
}

function findActionCenterSelection(overview) {
  if (!overview) {
    return null;
  }
  const candidates = [
    ...(overview.attention_items || []),
    ...(overview.recent_failures || []).map((item) => ({
      kind: "failure",
      severity: "high",
      title: `${item.action_name || item.tool_name || "action"} failed`,
      summary: item.operator_summary || item.detail || item.error_detail || item.status,
      action_id: item.action_id,
      workflow_run_id: item.workflow_run_id,
      bundle_id: item.bundle_id || null,
      session_id: item.session_id,
      next_step_hint: item.next_step_hint,
      detail_ref: item.action_id,
      source_record: item,
    })),
    ...(overview.active_workflows || []).map((item) => ({
      kind: "workflow",
      severity: item.pause_reason ? "medium" : "low",
      title: item.workflow_id,
      summary: item.summary || item.detail || item.current_step_label || item.status,
      action_id: item.blocking_action_id || null,
      workflow_run_id: item.workflow_run_id,
      bundle_id: null,
      session_id: item.session_id,
      next_step_hint: item.pause_reason ? `Resume or retry ${item.workflow_run_id} after reviewing the blocking state.` : null,
      detail_ref: item.workflow_run_id,
      source_record: item,
    })),
    ...(overview.recent_bundles || []).map((item) => ({
      kind: "bundle",
      severity: item.final_status && item.final_status !== "completed" ? "medium" : "low",
      title: item.bundle_id,
      summary: item.outcome_summary || item.failure_classification || item.requested_workflow_id || item.requested_tool_name || "Action bundle",
      action_id: null,
      workflow_run_id: item.workflow_run_id || null,
      bundle_id: item.bundle_id,
      session_id: item.session_id || null,
      next_step_hint: "Inspect the bundle detail and replay or review it if the outcome looks wrong.",
      detail_ref: item.bundle_id,
      source_record: item,
    })),
    ...(overview.recent_history || []).map((item) => ({
      kind: "history",
      severity: item.status === "failed" || item.status === "uncertain_review_required" ? "high" : "low",
      title: item.action_name || item.tool_name || item.action_id,
      summary: item.operator_summary || item.detail || item.error_detail || item.status,
      action_id: item.action_id,
      workflow_run_id: item.workflow_run_id,
      bundle_id: null,
      session_id: item.session_id,
      next_step_hint: item.next_step_hint,
      detail_ref: item.action_id,
      source_record: item,
    })),
  ];
  if (!candidates.length) {
    return null;
  }
  const currentKey = currentActionCenterKey();
  if (currentKey) {
    const matched = candidates.find((item) => actionCenterSelectionKey(item) === currentKey);
    if (matched) {
      return matched;
    }
  }
  return candidates[0];
}

function firstActionCenterAttention(overview) {
  return overview?.attention_items?.[0] || null;
}

function notifyActionCenterIfNeeded(prefix = "Action Center") {
  const focus = firstActionCenterAttention(state.actionPlaneOverview);
  if (!focus) {
    return false;
  }
  banner(
    `${prefix}: ${focus.title}. ${focus.next_step_hint || focus.summary || "Review the selected item in the Action Center."}`,
    focus.severity === "high" ? "warning" : "neutral",
  );
  return true;
}

async function refreshBodySemanticLibrary(smokeSafeOnly = true) {
  const params = new URLSearchParams();
  if (smokeSafeOnly) params.set("smoke_safe_only", "true");
  const data = await requestJson(`/api/operator/body/semantic-library?${params.toString()}`);
  state.bodySemanticLibrary = data.payload?.semantic_actions || [];
  renderBodySemanticLibrary(state.bodySemanticLibrary);
}

function currentServoLabJointRecord() {
  const joints = state.bodyServoLabCatalog?.joints || [];
  return joints.find((item) => item.joint_name === currentServoLabJoint()) || null;
}

async function refreshServoLabCatalog() {
  const data = await requestJson("/api/operator/body/servo-lab/catalog");
  state.bodyServoLabCatalog = data.payload || null;
  renderServoLabCatalog(state.bodyServoLabCatalog);
}

async function refreshActionPlanePanel() {
  const [overview, workflows] = await Promise.all([
    requestJson(`/api/operator/action-plane/overview?session_id=${encodeURIComponent(currentSessionId())}`),
    requestJson("/api/operator/action-plane/workflows"),
  ]);
  state.actionPlaneOverview = overview;
  state.actionPlaneConnectors = overview.connectors || [];
  state.actionPlaneApprovals = overview.approvals || [];
  state.actionPlaneHistory = overview.recent_history || [];
  state.actionPlaneBundles = overview.recent_bundles || [];
  state.actionPlaneBrowserStatus = overview.browser_status || null;
  state.actionPlaneWorkflows = workflows.items || [];
  state.actionPlaneWorkflowRuns = overview.active_workflows || [];
  renderActionPlane(overview, state.actionPlaneWorkflows);
}

async function refreshSnapshot() {
  try {
    const params = new URLSearchParams();
    if (state.selectedSessionId) params.set("session_id", state.selectedSessionId);
    params.set("voice_mode", currentVoiceMode());
    const [snapshot, applianceStatus] = await Promise.all([
      requestJson(`/api/operator/snapshot?${params.toString()}`),
      requestJson("/api/appliance/status"),
    ]);
    state.applianceStatus = applianceStatus;
    renderSnapshot(snapshot);
    await refreshBodySemanticLibrary(true);
    await refreshActionPlanePanel();
  } catch (error) {
    banner(`Snapshot refresh failed: ${error.message}`, "danger");
  }
}

function renderBodySemanticLibrary(items) {
  const select = document.getElementById("body-semantic-smoke-input");
  if (!select) {
    return;
  }
  const previous = select.value;
  select.innerHTML = "";
  if (!items.length) {
    const option = document.createElement("option");
    option.value = "look_left";
    option.textContent = "look_left";
    select.appendChild(option);
    return;
  }
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.canonical_name;
    option.textContent = `${item.canonical_name} (${item.family}${item.tuning_override_active ? ", tuned" : ""})`;
    select.appendChild(option);
  }
  const fallback = items.some((item) => item.canonical_name === previous) ? previous : items[0].canonical_name;
  select.value = fallback;
}

function renderServoLabCatalog(catalog) {
  const select = document.getElementById("servo-lab-joint-select");
  const statusEl = document.getElementById("servo-lab-status");
  if (!select) {
    return;
  }
  const previous = currentServoLabJoint();
  const joints = catalog?.joints || [];
  select.innerHTML = "";
  if (!joints.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "no_joints";
    select.appendChild(option);
    state.selectedServoLabJoint = "";
    document.getElementById("servo-lab-coupling-hint-input").value = "";
    document.getElementById("servo-lab-selection-summary").textContent = "No Servo Lab joint catalog is available.";
    statusEl.textContent = catalog
      ? `joint_count=0 | acceleration=${catalog.capabilities?.acceleration_status || "unknown"}`
      : "Mac Servo Lab not loaded yet.";
    renderJson("servo-lab-json", catalog);
    return;
  }
  for (const joint of joints) {
    const option = document.createElement("option");
    option.value = joint.joint_name;
    option.textContent = joint.joint_name;
    select.appendChild(option);
  }
  const selected = joints.some((item) => item.joint_name === previous) ? previous : joints[0].joint_name;
  select.value = selected;
  state.selectedServoLabJoint = selected;
  statusEl.textContent = [
    `joint_count=${catalog.joint_count || joints.length}`,
    `calibration=${catalog.calibration_kind || "-"}`,
    `acceleration=${catalog.capabilities?.acceleration_status || "unknown"}`,
  ].join(" | ");
  renderServoLabSelection(false);
  renderJson("servo-lab-json", catalog);
}

function renderServoLabSelection(resetInputs = false) {
  const joint = currentServoLabJointRecord();
  const summaryEl = document.getElementById("servo-lab-selection-summary");
  if (!joint) {
    summaryEl.textContent = "Choose a Servo Lab joint to inspect its raw bounds and current position.";
    document.getElementById("servo-lab-coupling-hint-input").value = "";
    return;
  }
  state.selectedServoLabJoint = joint.joint_name;
  document.getElementById("servo-lab-coupling-hint-input").value = joint.coupling_hint || "";
  summaryEl.textContent = [
    `joint=${joint.joint_name}`,
    `servo_ids=${(joint.servo_ids || []).join(",") || "-"}`,
    `current=${joint.current_position ?? "?"}`,
    `neutral=${joint.neutral}`,
    `min=${joint.raw_min}`,
    `max=${joint.raw_max}`,
    `direction=${joint.positive_direction || "-"}`,
    `coupling=${joint.coupling_group || "-"}`,
    `readback=${joint.readback_error || "ok"}`,
  ].join(" | ");
  if (resetInputs || !document.getElementById("servo-lab-target-raw-input").value.trim()) {
    document.getElementById("servo-lab-target-raw-input").value = String(joint.neutral);
  }
  if (resetInputs || !document.getElementById("servo-lab-lab-min-input").value.trim()) {
    document.getElementById("servo-lab-lab-min-input").value = String(joint.raw_min);
  }
  if (resetInputs || !document.getElementById("servo-lab-lab-max-input").value.trim()) {
    document.getElementById("servo-lab-lab-max-input").value = String(joint.raw_max);
  }
}

function renderWorkflowCatalog(items) {
  const select = document.getElementById("workflow-start-id-input");
  if (!select) {
    return;
  }
  const previous = select.value;
  select.innerHTML = "";
  if (!items?.length) {
    const option = document.createElement("option");
    option.value = "capture_note_and_reminder";
    option.textContent = "capture_note_and_reminder";
    select.appendChild(option);
    return;
  }
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.workflow_id;
    option.textContent = `${item.workflow_id} (${item.version})`;
    select.appendChild(option);
  }
  const fallback = items.some((item) => item.workflow_id === previous) ? previous : items[0].workflow_id;
  select.value = fallback;
}

function renderWorkflowRuns(runs) {
  const container = document.getElementById("workflow-runs");
  const statusEl = document.getElementById("workflow-status");
  container.innerHTML = "";
  if (!runs?.length) {
    container.innerHTML = '<div class="log-card">No workflow runs yet.</div>';
    statusEl.textContent = "No workflow activity yet.";
    return;
  }
  const latest = runs[0];
  statusEl.textContent = [
    `last=${latest.workflow_id}`,
    `status=${latest.status}`,
    latest.current_step_label ? `step=${latest.current_step_label}` : null,
    latest.blocking_action_id ? `blocking_action=${latest.blocking_action_id}` : null,
    latest.pause_reason ? `pause=${latest.pause_reason}` : null,
  ].filter(Boolean).join(" | ");
  for (const item of runs) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.workflow_run_id}</strong><span>${item.status}</span></div>
      <div class="subtle">workflow=${item.workflow_id} | trigger=${item.trigger?.trigger_kind || "-"} | step=${item.current_step_label || "-"}</div>
      <div>${item.summary || item.detail || "-"}</div>
    `;
    const row = document.createElement("div");
    row.className = "button-row";
    const resumeButton = document.createElement("button");
    resumeButton.className = "secondary";
    resumeButton.textContent = "Resume";
    resumeButton.addEventListener("click", () => resumeWorkflow(item.workflow_run_id).catch(handleError));
    const retryButton = document.createElement("button");
    retryButton.className = "secondary";
    retryButton.textContent = "Retry";
    retryButton.addEventListener("click", () => retryWorkflow(item.workflow_run_id).catch(handleError));
    const pauseButton = document.createElement("button");
    pauseButton.className = "secondary";
    pauseButton.textContent = "Pause";
    pauseButton.addEventListener("click", () => pauseWorkflow(item.workflow_run_id).catch(handleError));
    row.appendChild(resumeButton);
    row.appendChild(retryButton);
    row.appendChild(pauseButton);
    card.appendChild(row);
    container.appendChild(card);
  }
}

function createActionCenterChip(label, value, tone = "neutral") {
  const card = document.createElement("div");
  card.className = `action-center-chip ${tone === "neutral" ? "" : tone}`.trim();
  card.innerHTML = `<div class="subtle">${label}</div><strong>${value}</strong>`;
  return card;
}

function actionCenterBrowserPayload(overview, selectedItem) {
  if (selectedItem?.bundle_id && state.selectedActionBundle?.manifest?.bundle_id === selectedItem.bundle_id) {
    const detail = state.selectedActionBundle;
    const result = detail?.result || {};
    const calls = detail?.connector_calls || [];
    const browserCall = calls.find((item) => item.connector_id === "browser_runtime") || null;
    return {
      summary: result.outcome_summary || result.summary || browserCall?.summary || "Bundle includes browser evidence.",
      screenshotDataUrl:
        result.screenshot_data_url ||
        result.browser_preview?.screenshot_data_url ||
        result.browser_result?.screenshot_data_url ||
        null,
      screenshotPath:
        result.screenshot_path ||
        result.browser_preview?.screenshot_path ||
        result.browser_result?.screenshot_path ||
        null,
      targets:
        result.candidate_targets ||
        result.browser_preview?.candidate_targets ||
        result.browser_result?.candidate_targets ||
        [],
      json: detail,
    };
  }
  const browserStatus = overview?.browser_status || null;
  if (!browserStatus) {
    return null;
  }
  const snapshot = browserStatus.latest_snapshot || null;
  const pendingPreview = browserStatus.pending_preview || null;
  const lastResult = browserStatus.last_result || null;
  return {
    summary:
      pendingPreview?.detail ||
      pendingPreview?.summary ||
      lastResult?.summary ||
      snapshot?.summary ||
      "No browser evidence attached to the selected item.",
    screenshotDataUrl:
      pendingPreview?.screenshot_data_url ||
      lastResult?.screenshot_data_url ||
      snapshot?.screenshot_data_url ||
      null,
    screenshotPath:
      pendingPreview?.screenshot_path ||
      lastResult?.screenshot_path ||
      snapshot?.screenshot_path ||
      null,
    targets: pendingPreview?.candidate_targets || lastResult?.candidate_targets || [],
    json: browserStatus,
  };
}

function renderActionCenter(overview) {
  const panel = document.getElementById("action-center-panel");
  const chipsEl = document.getElementById("action-center-chips");
  const attentionEl = document.getElementById("action-center-attention");
  const historyEl = document.getElementById("action-center-history");
  const bundlesEl = document.getElementById("action-center-bundles");
  const replaysEl = document.getElementById("action-center-replays");
  const inspectorSummaryEl = document.getElementById("action-center-inspector-summary");
  const inspectorLinksEl = document.getElementById("action-center-inspector-links");
  const inspectorBrowserEl = document.getElementById("action-center-browser-preview");
  const inspectorBrowserTargetsEl = document.getElementById("action-center-browser-targets");
  const inspectorScreenshotEl = document.getElementById("action-center-browser-screenshot");
  const inspectorJsonEl = document.getElementById("action-center-inspector-json");
  const attentionItems = overview?.attention_items || [];
  const latestReplay = overview?.latest_replays?.[0] || state.lastActionBundleReplay || null;

  chipsEl.innerHTML = "";
  chipsEl.appendChild(
    createActionCenterChip(
      "Pending Approvals",
      String(overview?.status?.pending_approval_count ?? 0),
      (overview?.status?.pending_approval_count ?? 0) > 0 ? "warning" : "neutral",
    ),
  );
  chipsEl.appendChild(
    createActionCenterChip(
      "Waiting Workflows",
      String(overview?.status?.waiting_workflow_count ?? 0),
      (overview?.status?.waiting_workflow_count ?? 0) > 0 ? "warning" : "neutral",
    ),
  );
  chipsEl.appendChild(
    createActionCenterChip(
      "Review Required",
      String(overview?.status?.review_required_count ?? 0),
      (overview?.status?.review_required_count ?? 0) > 0 ? "danger" : "neutral",
    ),
  );
  chipsEl.appendChild(
    createActionCenterChip(
      "Degraded Connectors",
      String(overview?.status?.degraded_connector_count ?? 0),
      (overview?.status?.degraded_connector_count ?? 0) > 0 ? "warning" : "neutral",
    ),
  );
  chipsEl.appendChild(
    createActionCenterChip(
      "Browser Runtime",
      overview?.browser_status?.backend_mode || state.applianceStatus?.browser_runtime_state || "unknown",
      overview?.browser_status?.supported === false ? "warning" : "neutral",
    ),
  );
  chipsEl.appendChild(
    createActionCenterChip(
      "Latest Replay",
      latestReplay ? `${latestReplay.status}` : "none",
      latestReplay && latestReplay.status !== "completed" ? "warning" : "neutral",
    ),
  );

  const selectedItem = findActionCenterSelection(overview);
  setActionCenterSelection(selectedItem);
  const selectedKey = currentActionCenterKey();

  panel.classList.toggle("action-center-attention", attentionItems.length > 0);
  const firstAttention = firstActionCenterAttention(overview);
  const attentionKey = actionCenterSelectionKey(firstAttention);
  if (firstAttention && attentionKey !== state.actionCenterAnnouncedKey) {
    state.actionCenterAnnouncedKey = attentionKey;
  }

  attentionEl.innerHTML = "";
  if (!attentionItems.length) {
    attentionEl.innerHTML = '<div class="log-card">No pending approvals, blocked workflows, restart-review items, or recent failures.</div>';
  } else {
    for (const item of attentionItems) {
      const card = document.createElement("div");
      card.className = `log-card attention-card ${actionCenterSelectionKey(item) === selectedKey ? "active" : ""}`;
      card.innerHTML = `
        <div class="meta-row"><strong>${item.title}</strong><span>${item.severity}</span></div>
        <div>${item.summary}</div>
        <div class="subtle">kind=${item.kind} | action=${item.action_id || "-"} | workflow=${item.workflow_run_id || "-"} | bundle=${item.bundle_id || "-"}</div>
        <div class="subtle">${item.next_step_hint || "Inspect this item in the shared Action Center inspector."}</div>
      `;
      card.addEventListener("click", () => {
        setActionCenterSelection(item);
        if (item.bundle_id) {
          loadActionBundle(item.bundle_id, { quiet: true }).catch(handleError);
        } else {
          renderActionCenter(state.actionPlaneOverview);
        }
      });
      attentionEl.appendChild(card);
    }
  }

  historyEl.innerHTML = "";
  for (const item of overview?.recent_history || []) {
    const card = document.createElement("div");
    card.className = `log-card attention-card ${actionCenterSelectionKey({
      kind: "history",
      action_id: item.action_id,
      workflow_run_id: item.workflow_run_id,
      bundle_id: null,
      session_id: item.session_id,
      detail_ref: item.action_id,
    }) === selectedKey ? "active" : ""}`;
    card.innerHTML = `
      <div class="meta-row"><strong>${item.action_id}</strong><span>${item.status}</span></div>
      <div class="subtle">tool=${item.tool_name} | action=${item.action_name} | connector=${item.connector_id}</div>
      <div>${item.operator_summary || item.detail || item.error_detail || "-"}</div>
    `;
    card.addEventListener("click", () => {
      setActionCenterSelection({
        kind: "history",
        severity: item.status === "failed" ? "high" : "low",
        title: item.action_name || item.tool_name || item.action_id,
        summary: item.operator_summary || item.detail || item.error_detail || item.status,
        action_id: item.action_id,
        workflow_run_id: item.workflow_run_id,
        bundle_id: null,
        session_id: item.session_id,
        next_step_hint: item.next_step_hint,
        detail_ref: item.action_id,
      });
      renderActionCenter(state.actionPlaneOverview);
    });
    historyEl.appendChild(card);
  }
  if (!(overview?.recent_history || []).length) {
    historyEl.innerHTML = '<div class="log-card">No recent actions for the selected session.</div>';
  }

  bundlesEl.innerHTML = "";
  for (const item of overview?.recent_bundles || []) {
    const card = document.createElement("div");
    card.className = `log-card attention-card ${actionCenterSelectionKey({
      kind: "bundle",
      action_id: null,
      workflow_run_id: item.workflow_run_id || null,
      bundle_id: item.bundle_id,
      session_id: item.session_id || null,
      detail_ref: item.bundle_id,
    }) === selectedKey ? "active" : ""}`;
    card.innerHTML = `
      <div class="meta-row"><strong>${item.bundle_id}</strong><span>${item.final_status || "-"}</span></div>
      <div class="subtle">root=${item.root_kind} | tool=${item.requested_tool_name || "-"} | workflow=${item.requested_workflow_id || "-"}</div>
      <div>${item.outcome_summary || item.failure_classification || "-"}</div>
    `;
    const row = document.createElement("div");
    row.className = "button-row";
    const inspectButton = document.createElement("button");
    inspectButton.className = "secondary";
    inspectButton.textContent = "Inspect";
    inspectButton.addEventListener("click", (event) => {
      event.stopPropagation();
      loadActionBundle(item.bundle_id, { quiet: true }).catch(handleError);
    });
    const replayButton = document.createElement("button");
    replayButton.className = "secondary";
    replayButton.textContent = "Replay";
    replayButton.addEventListener("click", (event) => {
      event.stopPropagation();
      replayActionBundle(item.bundle_id).catch(handleError);
    });
    row.appendChild(inspectButton);
    row.appendChild(replayButton);
    card.appendChild(row);
    card.addEventListener("click", () => loadActionBundle(item.bundle_id, { quiet: true }).catch(handleError));
    bundlesEl.appendChild(card);
  }
  if (!(overview?.recent_bundles || []).length) {
    bundlesEl.innerHTML = '<div class="log-card">No recent action bundles for the selected session.</div>';
  }

  replaysEl.innerHTML = "";
  for (const item of overview?.latest_replays || []) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.replay_id}</strong><span>${item.status}</span></div>
      <div class="subtle">bundle=${item.bundle_id} | replayed=${item.replayed_action_count} | blocked=${(item.blocked_action_ids || []).length}</div>
      <div>${(item.notes || []).join(" | ") || "Deterministic replay recorded."}</div>
    `;
    replaysEl.appendChild(card);
  }
  if (!(overview?.latest_replays || []).length) {
    replaysEl.innerHTML = '<div class="log-card">No recent deterministic action replays.</div>';
  }

  if (!selectedItem) {
    inspectorSummaryEl.textContent = "Select an approval, workflow, failure, or bundle to inspect it here.";
    inspectorLinksEl.innerHTML = '<div class="log-card">No current Action Center selection.</div>';
    inspectorBrowserEl.textContent = "Browser preview and artifacts will appear here when the selected item includes browser evidence.";
    inspectorBrowserTargetsEl.innerHTML = '<div class="log-card">No browser targets for the current selection.</div>';
    inspectorScreenshotEl.classList.add("hidden");
    inspectorScreenshotEl.removeAttribute("src");
    inspectorJsonEl.textContent = "";
    return;
  }

  inspectorSummaryEl.textContent = [
    selectedItem.title || selectedItem.kind || "Action Center item",
    selectedItem.summary || null,
    selectedItem.next_step_hint ? `Next: ${selectedItem.next_step_hint}` : null,
  ].filter(Boolean).join(" | ");
  inspectorLinksEl.innerHTML = "";
  for (const entry of [
    selectedItem.kind ? `kind=${selectedItem.kind}` : null,
    selectedItem.severity ? `severity=${selectedItem.severity}` : null,
    selectedItem.action_id ? `action=${selectedItem.action_id}` : null,
    selectedItem.workflow_run_id ? `workflow=${selectedItem.workflow_run_id}` : null,
    selectedItem.bundle_id ? `bundle=${selectedItem.bundle_id}` : null,
    selectedItem.session_id ? `session=${selectedItem.session_id}` : null,
  ].filter(Boolean)) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.textContent = entry;
    inspectorLinksEl.appendChild(card);
  }

  const browserPayload = actionCenterBrowserPayload(overview, selectedItem);
  inspectorBrowserEl.textContent = browserPayload?.summary || "No browser evidence attached to the selected item.";
  if (browserPayload?.screenshotDataUrl) {
    inspectorScreenshotEl.src = browserPayload.screenshotDataUrl;
    inspectorScreenshotEl.classList.remove("hidden");
  } else {
    inspectorScreenshotEl.classList.add("hidden");
    inspectorScreenshotEl.removeAttribute("src");
  }
  inspectorBrowserTargetsEl.innerHTML = "";
  for (const item of browserPayload?.targets || []) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.label || item.text || item.placeholder || item.field_name || item.target_id}</strong><span>${item.role || "-"}</span></div>
      <div class="subtle">selector=${item.selector || "-"} | field=${item.field_name || "-"} | placeholder=${item.placeholder || "-"}</div>
    `;
    inspectorBrowserTargetsEl.appendChild(card);
  }
  if (!(browserPayload?.targets || []).length) {
    inspectorBrowserTargetsEl.innerHTML = '<div class="log-card">No browser targets for the current selection.</div>';
  }
  inspectorJsonEl.textContent = JSON.stringify(
    selectedItem.bundle_id && state.selectedActionBundle?.manifest?.bundle_id === selectedItem.bundle_id
      ? state.selectedActionBundle
      : selectedItem,
    null,
    2,
  );
}

function renderActionPlane(overview, workflows) {
  const status = overview?.status || {};
  document.getElementById("action-plane-pill").textContent = `action-center: ${status?.enabled ? "enabled" : "disabled"}`;
  document.getElementById("action-plane-summary").textContent = [
    `pending=${status?.pending_approval_count ?? 0}`,
    `waiting_workflows=${status?.waiting_workflow_count ?? 0}`,
    `review_required=${status?.review_required_count ?? 0}`,
    `degraded_connectors=${status?.degraded_connector_count ?? 0}`,
    status?.last_action_id ? `last_action=${status.last_action_id}` : null,
    status?.last_action_status ? `last_status=${status.last_action_status}` : null,
    firstActionCenterAttention(overview)?.next_step_hint ? `next=${firstActionCenterAttention(overview).next_step_hint}` : null,
  ].filter(Boolean).join(" | ");
  renderActionCenter(overview);
  renderWorkflowCatalog(workflows);
  renderWorkflowRuns(overview?.active_workflows || []);
  renderBrowserRuntime(overview?.browser_status || null);
  renderActionBundles(overview?.recent_bundles || []);
  renderActionBenchmarkSummary();

  const connectorsEl = document.getElementById("action-plane-connectors");
  connectorsEl.innerHTML = "";
  for (const item of overview?.connectors || []) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.connector_id}</strong><span>${item.supported ? "supported" : "unsupported"}</span></div>
      <div class="subtle">configured=${item.configured} | dry_run=${item.dry_run_supported} | actions=${(item.supported_actions || []).join(", ") || "-"}</div>
    `;
    connectorsEl.appendChild(card);
  }
  if (!(overview?.connectors || []).length) {
    connectorsEl.innerHTML = '<div class="log-card">No connectors registered.</div>';
  }

  const approvalsEl = document.getElementById("action-plane-approvals");
  approvalsEl.innerHTML = "";
  for (const item of overview?.approvals || []) {
    const attention = approvalAttentionSummary(overview, item.action_id);
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.action_id}</strong><span>${item.approval_state}</span></div>
      <div class="subtle">tool=${item.tool_name} | action=${item.action_name} | connector=${item.connector_id}</div>
      <div class="subtle">policy=${item.policy_decision || "-"} | risk=${item.request?.risk_class || "-"}</div>
      <div><strong>Why Blink asked:</strong> ${attention?.summary || actionPolicyReason(item)}</div>
      <div class="subtle">${attention?.next_step_hint || `Approve or reject ${item.action_id} from this Action Center.`}</div>
    `;
    const row = document.createElement("div");
    row.className = "button-row";
    const approveButton = document.createElement("button");
    approveButton.textContent = "Approve";
    approveButton.addEventListener("click", () => approveActionPlane(item.action_id).catch(handleError));
    const rejectButton = document.createElement("button");
    rejectButton.className = "secondary";
    rejectButton.textContent = "Reject";
    rejectButton.addEventListener("click", () => rejectActionPlane(item.action_id).catch(handleError));
    row.appendChild(approveButton);
    row.appendChild(rejectButton);
    card.appendChild(row);
    approvalsEl.appendChild(card);
  }
  if (!(overview?.approvals || []).length) {
    approvalsEl.innerHTML = '<div class="log-card">No pending approvals.</div>';
  }

  const historyRawEl = document.getElementById("action-plane-history");
  historyRawEl.innerHTML = "";
  for (const item of overview?.recent_history || []) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.action_id}</strong><span>${item.status}</span></div>
      <div class="subtle">tool=${item.tool_name} | action=${item.action_name} | connector=${item.connector_id}</div>
      <div>${item.operator_summary || item.detail || item.error_detail || "-"}</div>
    `;
    const row = document.createElement("div");
    row.className = "button-row";
    const replayButton = document.createElement("button");
    replayButton.className = "secondary";
    replayButton.textContent = "Replay";
    replayButton.addEventListener("click", () => replayActionPlane(item.action_id).catch(handleError));
    row.appendChild(replayButton);
    card.appendChild(row);
    historyRawEl.appendChild(card);
  }
  if (!(overview?.recent_history || []).length) {
    historyRawEl.innerHTML = '<div class="log-card">No recent Action Plane history.</div>';
  }
}

function renderActionBundles(bundles) {
  const container = document.getElementById("action-bundles");
  const summaryEl = document.getElementById("action-flywheel-summary");
  container.innerHTML = "";
  if (!bundles?.length) {
    summaryEl.textContent = "No action bundle data yet.";
    container.innerHTML = '<div class="log-card">No recent action bundles.</div>';
    return;
  }
  const latest = state.selectedActionBundle?.manifest || bundles[0];
  summaryEl.textContent = [
    `last_bundle=${latest.bundle_id}`,
    `root=${latest.root_kind}`,
    `status=${latest.final_status || "-"}`,
    `teacher=${latest.teacher_annotation_count ?? 0}`,
    state.lastActionBundleReplay ? `last_replay=${state.lastActionBundleReplay.status}` : null,
  ].filter(Boolean).join(" | ");
  for (const item of bundles) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.bundle_id}</strong><span>${item.final_status || "-"}</span></div>
      <div class="subtle">root=${item.root_kind} | tool=${item.requested_tool_name || "-"} | workflow=${item.requested_workflow_id || "-"}</div>
      <div>${item.outcome_summary || item.failure_classification || "-"}</div>
      <div class="subtle">approvals=${item.approval_event_count || 0} | calls=${item.connector_call_count || 0} | teacher=${item.teacher_annotation_count || 0}</div>
    `;
    const row = document.createElement("div");
    row.className = "button-row";
    const loadButton = document.createElement("button");
    loadButton.className = "secondary";
    loadButton.textContent = "Load";
    loadButton.addEventListener("click", () => loadActionBundle(item.bundle_id).catch(handleError));
    const replayButton = document.createElement("button");
    replayButton.className = "secondary";
    replayButton.textContent = "Replay";
    replayButton.addEventListener("click", () => replayActionBundle(item.bundle_id).catch(handleError));
    const reviewButton = document.createElement("button");
    reviewButton.className = "secondary";
    reviewButton.textContent = "Review";
    reviewButton.addEventListener("click", () => {
      document.getElementById("bundle-review-id-input").value = item.bundle_id;
      banner(`Bundle ${item.bundle_id} loaded into the review form.`, "neutral");
    });
    row.appendChild(loadButton);
    row.appendChild(replayButton);
    row.appendChild(reviewButton);
    card.appendChild(row);
    container.appendChild(card);
  }
}

function renderActionBenchmarkSummary() {
  const el = document.getElementById("action-benchmark-summary");
  const actionFamilies = new Set([
    "action_approval_correctness",
    "action_idempotency",
    "workflow_resume_correctness",
    "browser_artifact_completeness",
    "connector_safety_policy",
    "proactive_action_restraint",
    "action_trace_completeness",
  ]);
  const latest = (state.benchmarkRuns || []).find((run) => (run.families || []).some((family) => actionFamilies.has(family)));
  if (!latest) {
    el.textContent = "No action benchmark summaries yet.";
    return;
  }
  el.textContent = [
    `benchmark=${latest.run_id}`,
    `score=${latest.score}/${latest.max_score}`,
    `families=${(latest.families || []).filter((family) => actionFamilies.has(family)).join(", ") || "-"}`,
  ].join(" | ");
}

function renderBrowserRuntime(browserStatus) {
  const statusEl = document.getElementById("browser-task-status");
  const previewEl = document.getElementById("browser-task-preview-summary");
  const screenshotEl = document.getElementById("browser-task-screenshot");
  const candidatesEl = document.getElementById("browser-task-candidates");
  const jsonEl = document.getElementById("browser-task-json");
  if (!browserStatus) {
    statusEl.textContent = "No browser runtime data yet.";
    previewEl.textContent = "No pending browser preview.";
    screenshotEl.classList.add("hidden");
    screenshotEl.removeAttribute("src");
    candidatesEl.innerHTML = '<div class="log-card">No browser targets yet.</div>';
    jsonEl.textContent = "";
    return;
  }
  const activeSession = browserStatus.active_session || null;
  const snapshot = browserStatus.latest_snapshot || null;
  const pendingPreview = browserStatus.pending_preview || null;
  const lastResult = browserStatus.last_result || null;
  const candidateTargets = pendingPreview?.candidate_targets || lastResult?.candidate_targets || [];
  statusEl.textContent = [
    `backend=${browserStatus.backend_mode}`,
    `supported=${browserStatus.supported}`,
    `configured=${browserStatus.configured}`,
    activeSession?.current_url ? `url=${activeSession.current_url}` : null,
    activeSession?.page_title ? `title=${activeSession.page_title}` : null,
  ].filter(Boolean).join(" | ");
  previewEl.textContent = pendingPreview
    ? [
        `pending=${pendingPreview.requested_action}`,
        pendingPreview.detail || "approval_required",
        pendingPreview.resolved_target?.label ? `target=${pendingPreview.resolved_target.label}` : null,
        pendingPreview.text_input ? `text=${pendingPreview.text_input}` : null,
      ].filter(Boolean).join(" | ")
    : (lastResult
      ? [
          `last=${lastResult.requested_action}`,
          `status=${lastResult.status}`,
          lastResult.summary || null,
        ].filter(Boolean).join(" | ")
      : "No pending browser preview.");
  const screenshotData = pendingPreview?.screenshot_data_url || lastResult?.screenshot_data_url || snapshot?.screenshot_data_url || null;
  if (screenshotData) {
    screenshotEl.src = screenshotData;
    screenshotEl.classList.remove("hidden");
  } else {
    screenshotEl.classList.add("hidden");
    screenshotEl.removeAttribute("src");
  }
  candidatesEl.innerHTML = "";
  for (const item of candidateTargets) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.label || item.text || item.placeholder || item.field_name || item.target_id}</strong><span>${item.role || "-"}</span></div>
      <div class="subtle">placeholder=${item.placeholder || "-"} | field=${item.field_name || "-"} | selector=${item.selector || "-"}</div>
    `;
    candidatesEl.appendChild(card);
  }
  if (!candidateTargets.length) {
    candidatesEl.innerHTML = '<div class="log-card">No browser targets yet.</div>';
  }
  jsonEl.textContent = JSON.stringify(browserStatus, null, 2);
}

function renderSnapshot(snapshot) {
  state.latestSnapshot = snapshot;
  const sessionInput = document.getElementById("session-id-input");
  const explicitSessionId = sessionInput.value.trim();
  if (!state.selectedSessionId) {
    state.selectedSessionId = explicitSessionId || defaultConsoleSessionId;
  }
  state.latestDemoRuns = snapshot.recent_demo_runs?.items || [];
  state.selectedIncidentId = snapshot.selected_incident?.ticket_id || state.selectedIncidentId;

  document.getElementById("demo-profile-chip").textContent = snapshot.runtime.profile_summary || snapshot.runtime.runtime_profile;
  document.getElementById("dialogue-backend").textContent =
    snapshot.runtime.text_backend || snapshot.runtime.dialogue_backend;
  document.getElementById("voice-backend").textContent = [
    snapshot.runtime.stt_backend || "stt:-",
    snapshot.runtime.tts_backend || snapshot.runtime.voice_backend || "tts:-",
  ].join(" / ");
  document.getElementById("perception-mode").textContent =
    snapshot.runtime.vision_backend || snapshot.runtime.perception_provider_mode;
  document.getElementById("provider-status-chip").textContent = [
    snapshot.runtime.resolved_backend_profile || snapshot.runtime.backend_profile || "-",
    snapshot.runtime.provider_status || "-",
  ].join(" / ");
  document.getElementById("edge-link-state").textContent =
    snapshot.runtime.edge_transport_error
      ? `${snapshot.runtime.edge_transport_state} (${snapshot.runtime.edge_transport_error})`
      : snapshot.runtime.edge_transport_state;
  document.getElementById("body-status-chip").textContent = snapshot.runtime.body_status || snapshot.runtime.body_driver_mode;
  document.getElementById("world-mode").textContent = snapshot.runtime.world_mode;
  document.getElementById("shift-state-chip").textContent = snapshot.shift_supervisor?.state || "booting";
  document.getElementById("safe-idle-flag").textContent = snapshot.heartbeat.safe_idle_active
    ? `active (${snapshot.heartbeat.safe_idle_reason || "unknown"})`
    : "clear";
  document.getElementById("frontend-status-chip").textContent = [
    `terminal=${snapshot.runtime.terminal_frontend_state || "-"}`,
    `console=${snapshot.runtime.console_launch_state || "-"}`,
  ].join(" | ");
  document.getElementById("setup-status-chip").textContent = snapshot.runtime.setup_complete ? "complete" : "needs review";
  document.getElementById("auth-mode-chip").textContent = snapshot.runtime.auth_mode || "-";
  document.getElementById("native-devices-chip").textContent = [
    `preset=${snapshot.runtime.device_preset || "-"}`,
    `mic=${snapshot.runtime.selected_microphone_label || "-"}`,
    `camera=${snapshot.runtime.selected_camera_label || "-"}`,
    `speaker=${snapshot.runtime.selected_speaker_label || "system_default"}`,
  ].join(" | ");
  const presenceShell = snapshot.runtime.character_presence_shell || {};
  const presenceShellLink = document.getElementById("open-presence-shell-link");
  if (presenceShellLink) {
    presenceShellLink.href = presenceShellUrl(snapshot.active_session_id || state.selectedSessionId || defaultConsoleSessionId);
  }
  const performanceLink = document.getElementById("open-performance-link");
  if (performanceLink) {
    performanceLink.href = performanceUrl(snapshot.active_session_id || state.selectedSessionId || defaultConsoleSessionId);
  }
  document.getElementById("presence-shell-summary").textContent = [
    `state=${presenceShell.surface_state || "-"}`,
    `expression=${presenceShell.expression_name || "-"}`,
    `gaze=${presenceShell.gaze_target || "-"}`,
    presenceShell.gesture_name ? `gesture=${presenceShell.gesture_name}` : null,
    presenceShell.animation_name ? `animation=${presenceShell.animation_name}` : null,
    presenceShell.detail || presenceShell.message || null,
  ].filter(Boolean).join(" | ");
  document.getElementById("active-session-pill").textContent = snapshot.active_session_id || state.selectedSessionId || "No session selected";
  document.getElementById("voice-state-pill").textContent = `${snapshot.voice_state.mode}: ${snapshot.voice_state.status}`;
  updateBrainStatusSummary(snapshot);
  document.getElementById("voice-state-detail").textContent = [
    snapshot.voice_state.backend || "voice_runtime",
    `in:${snapshot.voice_state.input_backend || "-"}`,
    `stt:${snapshot.voice_state.transcription_backend || "-"}`,
    `out:${snapshot.voice_state.output_backend || "-"}`,
    snapshot.voice_state.message || "idle",
  ].join(" | ");
  document.getElementById("voice-transcript-preview").textContent =
    activeVoicePreviewText() ||
    snapshot.voice_state.transcript_text ||
    snapshot.voice_state.spoken_text ||
    "No live transcript yet.";
  document.getElementById("live-capability-note").textContent = snapshot.voice_state.can_listen
    ? "Selected mode supports browser microphone capture. Space starts push-to-talk outside text fields."
    : "Selected mode uses typed input fallback. Browser microphone controls stay disabled.";
  syncPerceptionModeControl(snapshot);

  renderCurrentSession(snapshot.selected_session);
  renderSessions(snapshot.sessions, snapshot.selected_session);
  renderTranscript(snapshot.selected_session);
  renderTraceSummaries(snapshot.trace_summaries.items);
  renderJson("world-state-json", snapshot.world_state);
  renderShiftSupervisor(snapshot.shift_supervisor);
  renderShiftMetrics(snapshot.shift_metrics);
  renderShiftTransitions(snapshot.shift_transitions.items);
  renderVenueOperations(snapshot.venue_operations);
  renderParticipantRouter(snapshot.participant_router);
  renderIncidents(snapshot);
  renderRecentShiftReports(snapshot.recent_shift_reports?.items || []);
  renderApplianceStatus(snapshot.runtime, state.applianceStatus);
  renderLocalCompanionReadiness(snapshot.runtime.local_companion_readiness, state.applianceStatus);
  renderDemoStatus(snapshot);
  renderWorldModel(snapshot.world_model);
  renderBodyPreview(snapshot.telemetry?.body_state, snapshot.telemetry?.body_capabilities);
  renderExecutiveDecisions(snapshot.executive_decisions.items);
  renderLatestPerception(snapshot.latest_perception, snapshot.runtime?.perception_freshness);
  renderPerceptionHistory(snapshot.perception_history.items);
  renderSceneObserverEvents(snapshot.scene_observer_events?.items || []);
  if (state.replayInspector) {
    renderReplayInspector(state.replayInspector);
  } else {
    renderReplayInspectorFromSnapshot(snapshot);
  }
  renderJson("telemetry-json", snapshot.telemetry);
  renderJson("heartbeat-json", snapshot.heartbeat);
  renderCommandLog(snapshot.command_history.items);
  renderTelemetryLog(snapshot.telemetry_log.items);
  updateLiveControlAvailability();

  if (!sessionInput.value.trim()) {
    sessionInput.value = state.selectedSessionId || defaultConsoleSessionId;
  }
}

function renderCurrentSession(session) {
  const container = document.getElementById("current-session-card");
  container.innerHTML = "";
  if (!session) {
    container.innerHTML = '<div class="log-card">No current session selected yet.</div>';
    return;
  }
  const card = document.createElement("div");
  card.className = "session-card active";
  card.innerHTML = `
    <div class="meta-row"><strong>${session.session_id}</strong><span>${session.status}</span></div>
    <div class="meta-row"><span>${session.response_mode}</span><span>${session.turn_count} turns</span></div>
    <div class="subtle">participant=${session.participant_id || "-"} | routing=${session.routing_status || "active"}</div>
    <div>${session.conversation_summary || "No session summary yet."}</div>
  `;
  container.appendChild(card);
}

function renderSessions(sessions, selectedSession) {
  const container = document.getElementById("sessions-list");
  container.innerHTML = "";
  const selectedId = selectedSession?.session_id || state.selectedSessionId;
  const visibleSessions = sessions.filter((session) => session.session_id !== selectedId && session.status !== "closed");
  const hiddenCount = sessions.length - visibleSessions.length - (selectedSession ? 1 : 0);

  for (const session of visibleSessions) {
    const card = document.createElement("div");
    card.className = "session-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${session.session_id}</strong><span>${session.status}</span></div>
      <div class="meta-row"><span>${session.response_mode}</span><span>${session.turn_count} turns</span></div>
      <div class="subtle">participant=${session.participant_id || "-"} | routing=${session.routing_status || "active"}</div>
      <div>${session.conversation_summary || "No summary yet."}</div>
    `;
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent = "Inspect Session";
    button.addEventListener("click", () => {
      state.selectedSessionId = session.session_id;
      document.getElementById("session-id-input").value = session.session_id;
      refreshSnapshot();
    });
    card.appendChild(button);
    container.appendChild(card);
  }
  if (hiddenCount > 0) {
    const hidden = document.createElement("div");
    hidden.className = "log-card";
    hidden.textContent = `${hiddenCount} closed or internal session${hiddenCount === 1 ? "" : "s"} hidden from the main view.`;
    container.appendChild(hidden);
  }
  if (!visibleSessions.length && hiddenCount === 0) {
    container.innerHTML = '<div class="log-card">No other live sessions right now.</div>';
  }
}

function renderTranscript(session) {
  const container = document.getElementById("transcript-list");
  const hiddenNote = document.getElementById("transcript-hidden-note");
  container.innerHTML = "";
  if (!session) {
    container.innerHTML = '<div class="log-card">Select or create a session to see the transcript.</div>';
    hiddenNote.textContent = "Low-signal internal events are hidden here by default.";
    return;
  }
  const visibleTurns = session.transcript.filter((turn) => {
    const userText = String(turn.user_text || "").trim();
    const replyText = String(turn.reply_text || "").trim();
    return Boolean(
      userText ||
      replyText ||
      (turn.command_types || []).length ||
      (turn.executive_reason_codes || []).length,
    );
  });
  const hiddenCount = Math.max(session.transcript.length - visibleTurns.length, 0);

  hiddenNote.textContent = hiddenCount
    ? `${hiddenCount} low-signal internal event${hiddenCount === 1 ? "" : "s"} hidden. Open advanced diagnostics if you need the raw event stream.`
    : "Showing the meaningful conversation and action-carrying turns for this session.";

  for (const turn of visibleTurns) {
    const card = document.createElement("div");
    card.className = "turn-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${turn.intent || turn.event_type || "turn"}</strong><span>${turn.source || "-"}</span></div>
      <div><strong>User:</strong> ${turn.user_text || "-"}</div>
      <div><strong>Reply:</strong> ${turn.reply_text || "-"}</div>
      <div class="subtle">Commands: ${(turn.command_types || []).join(", ") || "none"}</div>
      <div class="subtle">Executive: ${(turn.executive_reason_codes || []).join(", ") || "none"}</div>
    `;
    container.appendChild(card);
  }
  if (!visibleTurns.length) {
    container.innerHTML = '<div class="log-card">No meaningful conversation turns yet for this session.</div>';
  }
}

function renderTraceSummaries(items) {
  const container = document.getElementById("trace-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "trace-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.event_type}</strong><span>${item.outcome}</span></div>
      <div class="meta-row"><span>${item.engine}</span><span>${item.latency_ms || 0} ms</span></div>
      <div><strong>Intent:</strong> ${item.intent}</div>
      <div><strong>Reply:</strong> ${item.reply_text || "-"}</div>
      <div class="subtle">Executive: ${(item.executive_reason_codes || []).join(", ") || "none"}</div>
      <div class="subtle">Shift: ${item.shift_state || "none"} | ${(item.shift_reason_codes || []).join(", ") || "none"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No trace summaries for the selected session yet.</div>';
  }
}

function renderBodyPreview(bodyState, bodyCapabilities) {
  const summaryEl = document.getElementById("body-preview-summary");
  const pillEl = document.getElementById("body-driver-pill");
  if (!bodyState) {
    pillEl.textContent = "body: unavailable";
    summaryEl.textContent = "No body preview available yet.";
    document.getElementById("body-bench-status").textContent = "No body bench action yet.";
    renderJson("body-preview-json", null);
    return;
  }

  const preview = bodyState.virtual_preview || {};
  const mode = bodyState.driver_mode || "unknown";
  const connection = bodyState.connected ? "connected" : "disconnected";
  const transportState = bodyState.transport_healthy ? "healthy" : "degraded";
  pillEl.textContent = `${mode}:${connection}:${transportState}`;
  summaryEl.textContent = [
    preview.summary || "No preview summary.",
    `transport=${bodyState.transport_mode || "-"}`,
    `port=${bodyState.transport_port || "-"}`,
    `baud=${bodyState.transport_baud_rate || "-"}`,
    `confirmed_live=${bodyState.transport_confirmed_live ? "yes" : "no"}`,
    `expression=${bodyState.active_expression || "-"}`,
    `gesture=${bodyState.last_gesture || "-"}`,
    `animation=${preview.current_animation_name || bodyState.last_animation || "-"}`,
    `calibration=${bodyState.calibration_status || "-"}`,
    `armed=${bodyState.live_motion_armed ? "yes" : "no"}`,
    `live=${bodyState.live_motion_enabled ? "enabled" : "disabled"}`,
    `last=${bodyState.last_command_outcome?.outcome_status || "-"}`,
    `audit=${bodyState.latest_command_audit?.canonical_action_name || "-"}`,
  ].join(" | ");
  if (!currentBodyPort() && bodyState.transport_port) {
    document.getElementById("body-port-input").value = bodyState.transport_port;
  }
  if (!currentBodyBaud() && bodyState.transport_baud_rate) {
    document.getElementById("body-baud-input").value = String(bodyState.transport_baud_rate);
  }
  renderJson("body-preview-json", {
    head_profile: bodyState.head_profile_name,
    head_profile_version: bodyState.head_profile_version,
    transport_mode: bodyState.transport_mode,
    transport_port: bodyState.transport_port,
    transport_baud_rate: bodyState.transport_baud_rate,
    transport_healthy: bodyState.transport_healthy,
    transport_confirmed_live: bodyState.transport_confirmed_live,
    transport_error: bodyState.transport_error,
    calibration_path: bodyState.calibration_path,
    calibration_version: bodyState.calibration_version,
    calibration_status: bodyState.calibration_status,
    live_motion_armed: bodyState.live_motion_armed,
    arm_expires_at: bodyState.arm_expires_at,
    live_motion_enabled: bodyState.live_motion_enabled,
    latest_command_audit: bodyState.latest_command_audit,
    preview,
    pose: bodyState.pose,
    current_frame: bodyState.current_frame,
    servo_targets: bodyState.servo_targets,
    feedback_positions: bodyState.feedback_positions,
    clamp_notes: bodyState.clamp_notes,
    last_command_outcome: bodyState.last_command_outcome,
    servo_health: bodyState.servo_health,
    capabilities: bodyCapabilities,
  });
}

function renderDemoStatus(snapshot) {
  const summaryEl = document.getElementById("demo-status-summary");
  const pillEl = document.getElementById("demo-status-pill");
  const runtime = snapshot.runtime || {};
  const voiceState = snapshot.voice_state || {};
  const lastSkill = runtime.last_active_skill?.skill_name || "-";
  const lastTools = (runtime.last_tool_calls || []).map((item) => item.tool_name).join(", ") || "none";
  const lastValidations = (runtime.last_validation_outcomes || []).map((item) => item.status).join(", ") || "none";
  const backendSummary = (runtime.backend_status || [])
    .map((item) => `${item.kind}=${item.backend_id}:${item.status}`)
    .join(" | ");
  const liveTurn = runtime.latest_live_turn_diagnostics || null;
  pillEl.textContent = `profile: ${runtime.profile_summary || runtime.runtime_profile || "-"} | backend: ${
    runtime.resolved_backend_profile || runtime.backend_profile || "-"
  }`;
  summaryEl.textContent = [
    `setup=${runtime.setup_complete ? "complete" : "needs_review"}`,
    `config=${runtime.config_source || "-"}`,
    `runtime=${runtime.runtime_mode || "-"}`,
    `body=${runtime.body_status || runtime.body_driver_mode || "-"}`,
    `provider=${runtime.provider_status || "-"}${runtime.provider_detail ? ` (${runtime.provider_detail})` : ""}`,
    `perception=${runtime.perception_status || runtime.vision_backend || runtime.perception_provider_mode || "-"}`,
    `freshness=${runtime.perception_freshness?.status || "-"}:${runtime.perception_freshness?.age_seconds ?? "-"}s`,
    `social=${runtime.social_runtime_mode || "-"}`,
    `watcher_events=${runtime.watcher_buffer_count || 0}`,
    `semantic_refresh=${runtime.last_semantic_refresh_reason || "-"}`,
    `memory=${runtime.memory_status?.status || "-"}:${runtime.memory_status?.transcript_turn_count || 0}t`,
    `skill=${lastSkill}`,
    `tools=${lastTools}`,
    `validation=${lastValidations}`,
    `fallback=${runtime.fallback_state?.active ? "active" : "clear"}`,
    liveTurn
      ? `live_turn=${
          liveTurn.timeout_triggered
            ? `timeout:${liveTurn.stall_classification || "unknown"}`
            : `${liveTurn.total_ms ?? "-"}ms`
        }`
      : "live_turn=-",
    `exports=${runtime.export_available ? runtime.episode_export_dir || "enabled" : "unavailable"}`,
    backendSummary || "backends=unreported",
    `voice=${voiceState.status || "-"}`,
  ].join(" | ");

  const fallbackContainer = document.getElementById("fallback-event-list");
  fallbackContainer.innerHTML = "";
  const fallbackItems = (snapshot.trace_summaries?.items || []).filter((item) => {
    const outcome = item.outcome || "";
    return fallbackOutcomes.has(outcome) || outcome.startsWith("transport_error");
  });
  for (const item of fallbackItems.slice(0, 6)) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.event_type}</strong><span>${item.outcome}</span></div>
      <div>${item.reply_text || "No reply text."}</div>
      <div class="subtle">${item.engine || "-"} | ${(item.executive_reason_codes || []).join(", ") || "no reason codes"}</div>
    `;
    fallbackContainer.appendChild(card);
  }
  if (!fallbackItems.length) {
    fallbackContainer.innerHTML = '<div class="log-card">No fallback events for the selected session.</div>';
  }

  const embodiedContainer = document.getElementById("embodied-action-list");
  embodiedContainer.innerHTML = "";
  const embodiedItems = [...(snapshot.command_history?.items || [])]
    .reverse()
    .filter((item) => embodiedCommandTypes.has(item.command.command_type))
    .slice(0, 8);
  for (const item of embodiedItems) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.command.command_type}</strong><span>${item.ack.status || "-"}</span></div>
      <div>${formatPayloadSummary(item.command.payload)}</div>
      <div class="subtle">${item.ack.reason || "ok"}</div>
    `;
    embodiedContainer.appendChild(card);
  }
  if (!embodiedItems.length) {
    embodiedContainer.innerHTML = '<div class="log-card">No embodied actions emitted yet.</div>';
  }
}

function renderLocalCompanionReadiness(readiness, applianceStatus = null) {
  const pillEl = document.getElementById("local-companion-readiness-pill");
  const summaryEl = document.getElementById("local-companion-readiness-summary");
  const issuesEl = document.getElementById("local-companion-readiness-issues");
  const payload = readiness || applianceStatus?.local_companion_readiness || null;

  if (!payload) {
    pillEl.textContent = "readiness: unknown";
    summaryEl.textContent = "No certification summary is available yet.";
    issuesEl.innerHTML = '<div class="log-card">Run local-companion-certify to populate this readiness card.</div>';
    return;
  }

  pillEl.textContent = `readiness: ${payload.verdict || "unknown"}`;
  summaryEl.textContent = [
    payload.summary || "No readiness summary.",
    `machine_ready=${payload.machine_ready ? "yes" : "no"}`,
    `product_ready=${payload.product_ready ? "yes" : "no"}`,
    `last_certified=${payload.last_certified_at || "-"}`,
    `artifact_dir=${payload.artifact_dir || "-"}`,
    `doctor_report=${payload.doctor_report_path || "-"}`,
    `next=${(payload.next_actions || []).join(" / ") || "none"}`,
  ].join(" | ");

  issuesEl.innerHTML = "";
  const issueGroups = [
    ["machine_blocker", payload.machine_blockers || []],
    ["repo_or_runtime_bug", payload.repo_or_runtime_issues || []],
    ["degraded_but_acceptable", payload.degraded_warnings || []],
  ];
  let rendered = 0;
  for (const [kind, items] of issueGroups) {
    for (const message of items) {
      const card = document.createElement("div");
      const tone = kind === "machine_blocker" ? "danger" : kind === "repo_or_runtime_bug" ? "warning" : "neutral";
      card.className = `log-card ${tone}`;
      card.innerHTML = `
        <div class="meta-row"><strong>${kind}</strong><span>${tone}</span></div>
        <div>${message}</div>
      `;
      issuesEl.appendChild(card);
      rendered += 1;
    }
  }
  if (!rendered) {
    issuesEl.innerHTML = '<div class="log-card">No machine blockers or degraded warnings recorded.</div>';
  }
}

function renderApplianceStatus(runtime, applianceStatus = null) {
  const summaryEl = document.getElementById("appliance-status-summary");
  const pillEl = document.getElementById("appliance-config-pill");
  const issueList = document.getElementById("setup-issue-list");
  const deviceList = document.getElementById("device-health-list");
  const appliance = applianceStatus || {};
  pillEl.textContent = `config: ${appliance.config_source || runtime.config_source || "-"} | preset: ${appliance.device_preset || runtime.device_preset || "-"}`;
  summaryEl.textContent = [
    `setup=${(appliance.setup_complete ?? runtime.setup_complete) ? "complete" : "needs_review"}`,
    `auth=${appliance.auth_mode || runtime.auth_mode || "-"}`,
    `action_plane=${appliance.action_plane_ready === false ? "needs_review" : "ready"}`,
    `browser=${appliance.browser_runtime_state || "unknown"}`,
    `pending=${appliance.pending_action_count ?? 0}`,
    `waiting=${appliance.waiting_workflow_count ?? 0}`,
    `review=${appliance.review_required_count ?? 0}`,
    `next=${appliance.next_operator_step || "none"}`,
    `speaker_route=${appliance.selected_speaker_label || runtime.selected_speaker_label || "system_default"}:${(appliance.speaker_selection_supported ?? runtime.speaker_selection_supported) ? "selectable" : "system_default_only"}`,
    `exports=${(appliance.export_available ?? runtime.export_available) ? appliance.export_dir || runtime.episode_export_dir || "enabled" : "unavailable"}`,
  ].join(" | ");

  issueList.innerHTML = "";
  const issues = [...(runtime.setup_issues || []), ...((appliance.action_plane_issues || []).map((item) => ({
    category: "action_plane",
    severity: "warning",
    message: item,
    blocking: false,
  })))];
  if (!issues.length) {
    issueList.innerHTML = '<div class="log-card">No unresolved setup issues.</div>';
  } else {
    for (const issue of issues) {
      const card = document.createElement("div");
      card.className = "log-card";
      card.innerHTML = `
        <div class="meta-row"><strong>${issue.category}</strong><span>${issue.severity}</span></div>
        <div>${issue.message}</div>
        <div class="subtle">blocking=${issue.blocking ? "true" : "false"}</div>
      `;
      issueList.appendChild(card);
    }
  }

  deviceList.innerHTML = "";
  const items = runtime.device_health || [];
  if (!items.length) {
    deviceList.innerHTML = '<div class="log-card">No native device health reported.</div>';
    return;
  }
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.kind}</strong><span>${item.state}</span></div>
      <div>${item.detail || item.backend || "-"}</div>
      <div class="subtle">backend=${item.backend} | required=${item.required ? "true" : "false"} | available=${item.available ? "true" : "false"}</div>
    `;
    deviceList.appendChild(card);
  }
}

function renderShiftSupervisor(shiftSupervisor) {
  const summaryEl = document.getElementById("shift-supervisor-summary");
  if (!shiftSupervisor) {
    summaryEl.textContent = "No shift supervisor state yet.";
    renderJson("shift-supervisor-json", null);
    return;
  }
  const timers = (shiftSupervisor.timers || [])
    .filter((item) => item.active)
    .map((item) => `${item.timer_name}=${item.remaining_seconds}s`)
    .join(" | ") || "no active timers";
  summaryEl.textContent = [
    `state=${shiftSupervisor.state}`,
    `reasons=${(shiftSupervisor.reason_codes || []).join(", ") || "none"}`,
    `session=${shiftSupervisor.active_session_id || "-"}`,
    `people=${shiftSupervisor.people_count ?? 0}`,
    timers,
  ].join(" | ");
  renderJson("shift-supervisor-json", shiftSupervisor);
}

function renderShiftTransitions(items) {
  const container = document.getElementById("shift-transition-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.from_state} -> ${item.to_state}</strong><span>${item.trigger}</span></div>
      <div>${item.note || item.proactive_action || "No note."}</div>
      <div class="subtle">${(item.reason_codes || []).join(", ") || "none"} | ${item.created_at || "-"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No shift transitions recorded yet.</div>';
  }
}

function renderShiftMetrics(metrics) {
  const summaryEl = document.getElementById("shift-metrics-summary");
  if (!metrics) {
    summaryEl.textContent = "No shift metrics yet.";
    renderJson("shift-metrics-json", null);
    return;
  }
  summaryEl.textContent = [
    `greeted=${metrics.visitors_greeted || 0}`,
    `started=${metrics.conversations_started || 0}`,
    `completed=${metrics.conversations_completed || 0}`,
    `escalations=${metrics.escalations_created || 0}/${metrics.escalations_resolved || 0}`,
    `latency=${metrics.average_response_latency_ms || 0} ms`,
    `degraded=${metrics.time_spent_degraded_seconds || 0}s`,
    `fallback_rate=${metrics.fallback_frequency_rate || 0}`,
    `limited_awareness=${metrics.perception_limited_awareness_rate || 0}`,
  ].join(" | ");
  renderJson("shift-metrics-json", metrics);
}

function renderRecentShiftReports(items) {
  const container = document.getElementById("shift-report-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.simulation_name}</strong><span>${item.status}</span></div>
      <div>${item.score_summary?.summary_text || "No score summary."}</div>
      <div class="subtle">rating=${item.score_summary?.rating || "-"} | score=${item.score_summary?.score || 0}/${item.score_summary?.max_score || 0}</div>
      <div class="subtle">greeted=${item.metrics?.visitors_greeted || 0} | started=${item.metrics?.conversations_started || 0} | resolved=${item.metrics?.escalations_resolved || 0}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No pilot shift reports saved yet.</div>';
  }
}

function renderVenueOperations(venueOperations) {
  const summaryEl = document.getElementById("venue-ops-summary");
  if (!venueOperations) {
    summaryEl.textContent = "No venue operations pack loaded yet.";
    renderJson("venue-ops-json", null);
    return;
  }
  const quietHours = (venueOperations.quiet_hours || []).length;
  const nextPrompt = venueOperations.next_scheduled_prompt_type
    ? `${venueOperations.next_scheduled_prompt_type} @ ${venueOperations.next_scheduled_prompt_at || "-"}`
    : "none scheduled";
  summaryEl.textContent = [
    `site=${venueOperations.site_name || "-"}`,
    `timezone=${venueOperations.timezone || "-"}`,
    `auto_greet=${venueOperations.proactive_greeting_policy?.enabled ? "on" : "off"}`,
    `quiet_windows=${quietHours}`,
    `next=${nextPrompt}`,
  ].join(" | ");
  renderJson("venue-ops-json", venueOperations);
}

function renderParticipantRouter(router) {
  const pill = document.getElementById("participant-router-pill");
  const summaryEl = document.getElementById("participant-router-summary");
  if (!router) {
    pill.textContent = "one_on_one";
    summaryEl.textContent = "No participant routing state yet.";
    renderJson("participant-router-json", null);
    return;
  }
  pill.textContent = router.crowd_mode ? "crowd_mode" : "one_on_one";
  const queued = (router.queued_participants || [])
    .map((item) => `${item.queue_position}:${item.participant_id}`)
    .join(", ") || "none";
  const bindings = (router.participant_sessions || [])
    .map((item) => `${item.participant_id}->${item.session_id}(${item.routing_status})`)
    .join(" | ") || "none";
  summaryEl.textContent = [
    `active_participant=${router.active_participant_id || "-"}`,
    `active_session=${router.active_session_id || "-"}`,
    `queue=${queued}`,
    `bindings=${bindings}`,
    `reason=${router.last_routing_reason || "-"}`,
  ].join(" | ");
  renderJson("participant-router-json", router);
}

function renderIncidents(snapshot) {
  const selectedIncident = snapshot.selected_incident;
  const summaryEl = document.getElementById("incident-summary");
  const pill = document.getElementById("incident-status-pill");

  if (!selectedIncident) {
    pill.textContent = "no_ticket";
    summaryEl.textContent = "No incident ticket selected.";
    renderIncidentList("open-incident-list", snapshot.open_incidents?.items || []);
    renderIncidentList("closed-incident-list", snapshot.closed_incidents?.items || []);
    renderIncidentTimeline([]);
    return;
  }

  state.selectedIncidentId = selectedIncident.ticket_id;
  document.getElementById("incident-ticket-id-input").value = selectedIncident.ticket_id;
  if (!document.getElementById("incident-operator-input").value.trim()) {
    document.getElementById("incident-operator-input").value = selectedIncident.assigned_to || "";
  }
  pill.textContent = selectedIncident.current_status;
  summaryEl.textContent = [
    `ticket=${selectedIncident.ticket_id}`,
    `session=${selectedIncident.session_id}`,
    `category=${selectedIncident.reason_category}`,
    `urgency=${selectedIncident.urgency}`,
    `assigned=${selectedIncident.assigned_to || "-"}`,
    `contact=${selectedIncident.suggested_staff_contact?.name || selectedIncident.suggested_staff_contact?.desk_location_label || "-"}`,
  ].join(" | ");
  renderIncidentList("open-incident-list", snapshot.open_incidents?.items || []);
  renderIncidentList("closed-incident-list", snapshot.closed_incidents?.items || []);
  renderIncidentTimeline(snapshot.selected_incident_timeline?.items || []);
}

function renderIncidentList(elementId, items) {
  const container = document.getElementById(elementId);
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.ticket_id}</strong><span>${item.current_status}</span></div>
      <div>${item.participant_summary || "No participant summary."}</div>
      <div class="subtle">category=${item.reason_category} | urgency=${item.urgency} | assigned=${item.assigned_to || "-"}</div>
      <div class="subtle">contact=${item.suggested_staff_contact?.name || "-"} | location=${item.suggested_staff_contact?.desk_location_label || "-"}</div>
    `;
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent = item.ticket_id === state.selectedIncidentId ? "Viewing" : "Inspect Ticket";
    button.disabled = item.ticket_id === state.selectedIncidentId;
    button.addEventListener("click", () => {
      state.selectedIncidentId = item.ticket_id;
      document.getElementById("incident-ticket-id-input").value = item.ticket_id;
      refreshSnapshot().catch(handleError);
    });
    card.appendChild(button);
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No tickets in this view.</div>';
  }
}

function renderIncidentTimeline(items) {
  const container = document.getElementById("incident-timeline-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.event_type}</strong><span>${item.to_status}</span></div>
      <div>${item.note || "No note."}</div>
      <div class="subtle">actor=${item.actor || "-"} | from=${item.from_status || "-"} | ${item.created_at || "-"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No incident timeline yet.</div>';
  }
}

function renderWorldModel(worldModel) {
  document.getElementById("engagement-state-pill").textContent = worldModel?.engagement_state || "unknown";
  document.getElementById("attention-target-pill").textContent = `attention: ${
    worldModel?.attention_target?.target_label || "none"
  }`;
  const router = worldModel?.participant_router || {};
  const summary = [
    `participants=${(worldModel?.active_participants_in_view || []).length}`,
    `active_participant=${router.active_participant_id || "unknown"}`,
    `queued=${(router.queued_participants || []).length}`,
    `speaker=${worldModel?.current_speaker_participant_id || "unknown"}`,
    `engagement=${worldModel?.engagement_state || "unknown"}`,
    `social=${worldModel?.social_runtime_mode || "idle"}`,
    `scene_freshness=${worldModel?.scene_freshness || "unknown"}`,
    `environment=${worldModel?.environment_state || "unknown"}`,
    `turn=${worldModel?.turn_state || "idle"}`,
    `executive=${worldModel?.executive_state || "idle"}`,
    `anchors=${(worldModel?.visual_anchors || []).map((item) => item.label).join(", ") || "none"}`,
    `visible_text=${(worldModel?.recent_visible_text || []).map((item) => item.label).join(", ") || "none"}`,
    `objects=${(worldModel?.recent_named_objects || []).map((item) => item.label).join(", ") || "none"}`,
    `limited_awareness=${Boolean(worldModel?.perception_limited_awareness)}`,
    `uncertainty=${(worldModel?.uncertainty_markers || []).join(", ") || "none"}`,
  ].join(" | ");
  document.getElementById("world-model-summary").textContent = summary;
  renderJson("world-model-json", worldModel);
}

function renderExecutiveDecisions(items) {
  const container = document.getElementById("executive-decision-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.decision_type}</strong><span>${item.executive_state}</span></div>
      <div>${item.note || "No note."}</div>
      <div class="subtle">reasons=${(item.reason_codes || []).join(", ") || "none"} | event=${item.trigger_event_type} | applied=${item.applied}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No executive decisions recorded yet.</div>';
  }
}

function renderCommandLog(items) {
  const container = document.getElementById("command-log");
  container.innerHTML = "";
  const reversed = [...items].reverse().slice(0, 12);
  for (const item of reversed) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.command.command_type}</strong><span>${item.ack.status || (item.ack.accepted ? "accepted" : "rejected")}</span></div>
      <div class="subtle">${item.ack.reason}</div>
    `;
    container.appendChild(card);
  }
  if (!reversed.length) {
    container.innerHTML = '<div class="log-card">No commands applied yet.</div>';
  }
}

function renderTelemetryLog(items) {
  const container = document.getElementById("telemetry-log");
  container.innerHTML = "";
  const reversed = [...items].reverse().slice(0, 12);
  for (const item of reversed) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.source}</strong><span>${item.note || "-"}</span></div>
      <div class="subtle">${item.telemetry.mode} | battery ${item.telemetry.battery_pct}% | led ${item.telemetry.led_color}</div>
    `;
    container.appendChild(card);
  }
  if (!reversed.length) {
    container.innerHTML = '<div class="log-card">No telemetry log entries yet.</div>';
  }
}

function renderEpisodes(items) {
  const container = document.getElementById("episode-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.source_type}</strong><span>${item.schema_version}</span></div>
      <div>${item.source_id}</div>
      <div class="subtle">sessions=${(item.session_ids || []).join(", ") || "-"} | traces=${item.trace_count} | perception=${item.perception_snapshot_count} | annotations=${item.annotation_count} | memory_actions=${item.memory_action_count || 0} | teacher=${item.teacher_annotation_count || 0}</div>
    `;
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent = item.episode_id === state.selectedEpisodeId ? "Viewing" : "Inspect Episode";
    button.disabled = item.episode_id === state.selectedEpisodeId;
    button.addEventListener("click", () => inspectEpisode(item.episode_id).catch(handleError));
    card.appendChild(button);
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No exported episodes yet.</div>';
  }
}

function renderTeacherAnnotations(items) {
  const container = document.getElementById("teacher-annotation-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.scope}</strong><span>${item.review_value}</span></div>
      <div>${item.label || "unlabeled"} | ${item.scope_id}</div>
      <div>${item.note || item.better_reply_text || item.corrected_scene_summary || "No note."}</div>
      <div class="subtle">author=${item.author || "-"} | tags=${(item.benchmark_tags || []).join(", ") || "none"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No teacher annotations saved for the current selection.</div>';
  }
}

function renderBenchmarkRuns(items) {
  const container = document.getElementById("benchmark-run-list");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.episode_id}</strong><span>${item.passed ? "passed" : "review"}</span></div>
      <div>score=${item.score}/${item.max_score} | fallback=${item.fallback_count}</div>
      <div class="subtle">${(item.families || []).join(", ") || "all_families"} | ${item.completed_at || item.started_at || "-"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No benchmark runs saved yet.</div>';
  }
}

function renderJson(id, value) {
  document.getElementById(id).textContent = JSON.stringify(value, null, 2);
}

function renderLatestPerception(snapshot, freshness) {
  const statusPill = document.getElementById("perception-status-pill");
  const summaryEl = document.getElementById("latest-perception-summary");
  if (!snapshot) {
    statusPill.textContent = "Perception idle";
    summaryEl.textContent = "No perception snapshot yet.";
    renderJson("latest-perception-json", null);
    return;
  }

  statusPill.textContent = `${snapshot.provider_mode}: ${snapshot.status}`;
  summaryEl.textContent = [
    snapshot.scene_summary || "No scene summary.",
    `freshness=${freshness?.status || "-"}:${freshness?.age_seconds ?? "-"}s`,
    `tier=${snapshot.tier || freshness?.tier || "-"}`,
    `trigger=${snapshot.trigger_reason || freshness?.trigger_reason || "-"}`,
    `confidence=${perceptionConfidenceText(snapshot)}`,
    `source=${snapshot.source_frame.source_kind}`,
    `uncertainty=${(snapshot.uncertainty_markers || []).join(", ") || "none"}`,
    `time=${snapshot.created_at || "-"}`,
  ].join(" | ");
  renderJson("latest-perception-json", snapshot);
}

function renderPerceptionHistory(items) {
  const container = document.getElementById("perception-history");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.provider_mode}</strong><span>${item.status}</span></div>
      <div>${item.scene_summary || item.message || "No summary."}</div>
      <div class="subtle">${item.tier || "-"} | ${item.trigger_reason || "-"} | ${item.source_frame.source_kind} | ${perceptionConfidenceText(item)} | ${item.created_at}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No perception history yet.</div>';
  }
}

function renderSceneObserverEvents(items) {
  const container = document.getElementById("scene-observer-events");
  container.innerHTML = "";
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${item.refresh_reason || "observe"}</strong><span>${item.environment_state || "-"}</span></div>
      <div>people=${item.people_count_estimate ?? "-"} | attention=${item.attention_state || "-"} | change=${item.scene_change_score ?? "-"}</div>
      <div class="subtle">refresh=${item.refresh_recommended ? "true" : "false"} | limits=${(item.capability_limits || []).join(", ") || "none"} | ${item.observed_at || "-"}</div>
    `;
    container.appendChild(card);
  }
  if (!items.length) {
    container.innerHTML = '<div class="log-card">No watcher events recorded yet.</div>';
  }
}

function renderReplayInspectorFromSnapshot(snapshot) {
  const facts = snapshot.latest_perception?.observations || [];
  renderReplayInspector({
    sourceSummary: snapshot.latest_perception
      ? [
          snapshot.latest_perception.source_frame.source_kind,
          snapshot.latest_perception.source_frame.fixture_path || snapshot.latest_perception.source_frame.file_name || "-",
          snapshot.latest_perception.created_at,
        ].join(" | ")
      : "No replay or snapshot selected yet.",
    facts,
    engagementTimeline: snapshot.engagement_timeline || [],
    finalAction: snapshot.executive_decisions?.items?.[0]
      ? {
          executive_state: snapshot.executive_decisions.items[0].executive_state,
          reason_codes: snapshot.executive_decisions.items[0].reason_codes,
          note: snapshot.executive_decisions.items[0].note,
        }
      : null,
    scorecard: null,
  });
}

function renderReplayInspector(model) {
  document.getElementById("replay-source-summary").textContent =
    model?.sourceSummary || "No replay or snapshot selected yet.";

  const factsContainer = document.getElementById("replay-facts-list");
  factsContainer.innerHTML = "";
  const facts = model?.facts || [];
  for (const fact of facts) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${fact.observation_type || fact.label || "fact"}</strong><span>${fact.confidence?.score?.toFixed ? fact.confidence.score.toFixed(2) : "-"}</span></div>
      <div>${fact.text_value || fact.number_value || fact.bool_value || fact.detail || "No extracted value."}</div>
    `;
    factsContainer.appendChild(card);
  }
  if (!facts.length) {
    factsContainer.innerHTML = '<div class="log-card">No extracted scene facts yet.</div>';
  }

  const timelineContainer = document.getElementById("replay-engagement-timeline");
  timelineContainer.innerHTML = "";
  const timeline = model?.engagementTimeline || [];
  for (const point of timeline) {
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${point.engagement_state || "-"}</strong><span>${point.timestamp || "-"}</span></div>
      <div class="subtle">attention=${point.attention_target || "none"} | confidence=${point.confidence?.score ?? "-"}</div>
    `;
    timelineContainer.appendChild(card);
  }
  if (!timeline.length) {
    timelineContainer.innerHTML = '<div class="log-card">No engagement timeline yet.</div>';
  }

  const actionContainer = document.getElementById("replay-final-action");
  actionContainer.innerHTML = "";
  if (model?.finalAction) {
    const action = model.finalAction;
    const card = document.createElement("div");
    card.className = "log-card";
    card.innerHTML = `
      <div class="meta-row"><strong>${action.intent || action.executive_state || "final_action"}</strong><span>${(action.command_types || []).join(", ") || "no commands"}</span></div>
      <div>${action.reply_text || action.note || "No reply text."}</div>
      <div class="subtle">${(action.reason_codes || []).join(", ") || "no explicit reason codes"}</div>
    `;
    actionContainer.appendChild(card);
  } else {
    actionContainer.innerHTML = '<div class="log-card">No final action captured yet.</div>';
  }

  const scorecardContainer = document.getElementById("replay-scorecard-list");
  scorecardContainer.innerHTML = "";
  if (model?.scorecard) {
    const header = document.createElement("div");
    header.className = "log-card";
    header.innerHTML = `
      <div class="meta-row"><strong>${model.scorecard.title || model.scorecard.scene_name}</strong><span>${model.scorecard.score}/${model.scorecard.max_score}</span></div>
      <div>${model.scorecard.passed ? "passed" : "degraded or failed"}</div>
    `;
    scorecardContainer.appendChild(header);
    for (const criterion of model.scorecard.criteria || []) {
      const card = document.createElement("div");
      card.className = "log-card";
      card.innerHTML = `
        <div class="meta-row"><strong>${criterion.criterion}</strong><span>${criterion.passed ? "pass" : "fail"}</span></div>
        <div class="subtle">${criterion.observed || criterion.note || "-"}</div>
      `;
      scorecardContainer.appendChild(card);
    }
  } else {
    scorecardContainer.innerHTML = '<div class="log-card">No scene scorecard yet.</div>';
  }
}

function replayInspectorFromSubmission(result) {
  return {
    sourceSummary: [
      result.snapshot?.source_frame?.source_kind || result.snapshot?.provider_mode || "snapshot",
      result.snapshot?.source_frame?.fixture_path || result.snapshot?.source_frame?.file_name || result.snapshot?.source || "-",
      result.snapshot?.created_at || "-",
    ].join(" | "),
    facts: result.snapshot?.observations || [],
    engagementTimeline: [],
    finalAction: result.published_results?.length
      ? {
          reply_text: result.published_results[result.published_results.length - 1].response?.reply_text,
          command_types: (result.published_results[result.published_results.length - 1].response?.commands || []).map((item) => item.command_type),
        }
      : null,
    scorecard: null,
  };
}

function replayInspectorFromReplay(result) {
  const snapshots = result.snapshots || [];
  return {
    sourceSummary: [
      "fixture_replay",
      result.fixture_path || "-",
      `${snapshots.length} frame(s)`,
    ].join(" | "),
    facts: snapshots.flatMap((item) => item.snapshot?.observations || []),
    engagementTimeline: [],
    finalAction: snapshots.length && snapshots[snapshots.length - 1].published_results?.length
      ? {
          reply_text: snapshots[snapshots.length - 1].published_results[snapshots[snapshots.length - 1].published_results.length - 1].response?.reply_text,
          command_types: (snapshots[snapshots.length - 1].published_results[snapshots[snapshots.length - 1].published_results.length - 1].response?.commands || []).map((item) => item.command_type),
        }
      : null,
    scorecard: null,
  };
}

function replayInspectorFromScene(result) {
  return {
    sourceSummary: [
      result.title || result.scene_name,
      result.perception_snapshots?.length ? `${result.perception_snapshots.length} perception snapshot(s)` : "no perception snapshots",
      `${result.latency_breakdown?.total_ms || 0} ms`,
    ].join(" | "),
    facts: (result.perception_snapshots || []).flatMap((item) => item.observations || []),
    engagementTimeline: result.engagement_timeline || [],
    finalAction: result.final_action || null,
    scorecard: result.scorecard || null,
  };
}

function perceptionConfidenceText(snapshot) {
  const scored = (snapshot.observations || [])
    .map((item) => item.confidence?.score)
    .filter((value) => typeof value === "number");
  if (!scored.length) {
    return snapshot.limited_awareness ? "limited" : "-";
  }
  const average = scored.reduce((sum, value) => sum + value, 0) / scored.length;
  return average.toFixed(2);
}

async function createSession() {
  const payload = {
    session_id: currentSessionId(),
    user_id: document.getElementById("user-id-input").value.trim() || null,
    response_mode: currentResponseMode(),
  };
  await requestJson("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
  state.selectedSessionId = payload.session_id;
  banner(`Session ${payload.session_id} created.`, "success");
  refreshSnapshot();
}

async function resetRuntime() {
  const clearDemoRuns = true;
  await requestJson("/api/reset", {
    method: "POST",
    body: JSON.stringify({ reset_edge: true, clear_user_memory: true, clear_demo_runs: clearDemoRuns }),
  });
  state.selectedSessionId = null;
  state.replayInspector = null;
  document.getElementById("session-id-input").value = "";
  banner(`Runtime reset completed${clearDemoRuns ? " and demo history cleared" : ""}.`, "warning");
  await refreshSnapshot();
}

async function sendTextTurn(options = {}) {
  const text = (options.inputText ?? document.getElementById("user-text-input").value).trim();
  if (!text) {
    banner("Type or capture a visitor utterance before sending input.", "warning");
    return null;
  }
  state.turnInFlight = true;
  try {
    const { payload: cameraPayload, cameraCaptureMs } = await maybeBuildCameraTurnPayload(text);
    const inputMetadata = {
      ...(options.inputMetadata || {}),
      client_submit_wall_time_ms: Date.now(),
    };
    if (cameraCaptureMs !== null && cameraCaptureMs !== undefined) {
      inputMetadata.browser_camera_capture_ms = cameraCaptureMs;
    }
    const payload = {
      session_id: currentSessionId(),
      user_id: document.getElementById("user-id-input").value.trim() || null,
      input_text: text,
      response_mode: currentResponseMode(),
      voice_mode: options.voiceMode || currentVoiceMode(),
      speak_reply: options.speakReply ?? speakReplyEnabled(),
      source: options.source || "operator_console",
      input_metadata: inputMetadata,
      ...cameraPayload,
    };
    const result = await requestJson("/api/operator/text-turn", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: liveTurnTimeoutMs({
        source: payload.source,
        voiceMode: payload.voice_mode,
        text,
        hasCameraPayload: Boolean(cameraPayload.camera_image_data_url),
      }),
    });
    state.selectedSessionId = result.session_id;
    document.getElementById("session-id-input").value = result.session_id;
    if (options.clearInput !== false) {
      document.getElementById("user-text-input").value = "";
    }
    banner(
      options.bannerText || `Reply: ${result.response.reply_text || "no spoken reply"}`,
      toneForOutcome(result.outcome),
    );
    await refreshSnapshot();
    notifyActionCenterIfNeeded("Continue in Action Center");
    return result;
  } finally {
    state.turnInFlight = false;
  }
}

async function submitPerceptionSnapshot(payload, { bannerText } = {}) {
  const result = await requestJson("/api/operator/perception/snapshots", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.selectedSessionId = result.session_id || state.selectedSessionId;
  if (result.session_id) {
    document.getElementById("session-id-input").value = result.session_id;
  }
  banner(
    bannerText || result.snapshot.scene_summary || result.snapshot.message || "Perception snapshot processed.",
    toneForPerception(result),
  );
  state.replayInspector = replayInspectorFromSubmission(result);
  renderReplayInspector(state.replayInspector);
  await refreshSnapshot();
  return result;
}

async function maybeBuildCameraTurnPayload(text) {
  if (!state.cameraStream || !looksLikeVisualQuery(text)) {
    return { payload: {}, cameraCaptureMs: null };
  }
  const providerMode = preferredLiveCameraPerceptionMode();
  if (!providerMode || providerMode === "stub" || providerMode === "browser_snapshot") {
    return { payload: {}, cameraCaptureMs: null };
  }
  try {
    const started = performance.now();
    const frame = await captureCameraFrame();
    return {
      payload: {
        camera_image_data_url: frame.dataUrl,
        camera_source_frame: {
          source_kind: "browser_camera_snapshot",
          source_label: "operator_console_camera",
          frame_id: `camera-turn-${Date.now()}`,
          mime_type: frame.mimeType,
          width_px: frame.width,
          height_px: frame.height,
          captured_at: frame.capturedAt,
        },
        camera_provider_mode: providerMode,
      },
      cameraCaptureMs: Math.round((performance.now() - started) * 100) / 100,
    };
  } catch (error) {
    banner(`Camera capture failed before visual query: ${error.message}`, "warning");
    return { payload: {}, cameraCaptureMs: null };
  }
}

async function replayPerceptionFixture() {
  const fixturePath = document.getElementById("perception-fixture-input").value;
  if (!fixturePath) {
    banner("Select a perception fixture first.", "warning");
    return null;
  }
  const result = await requestJson("/api/operator/perception/replay", {
    method: "POST",
    body: JSON.stringify({
      session_id: currentSessionId(),
      fixture_path: fixturePath,
      source: "operator_console_fixture",
      publish_events: true,
    }),
  });
  banner(
    `Perception fixture replay ${result.success ? "completed" : "degraded"}: ${result.snapshots.length} frame(s).`,
    result.success ? "success" : "warning",
  );
  state.replayInspector = replayInspectorFromReplay(result);
  renderReplayInspector(state.replayInspector);
  await refreshSnapshot();
  return result;
}

function buildManualAnnotations() {
  const annotations = [];
  const peopleCount = document.getElementById("people-count-input").value;
  const engagement = document.getElementById("engagement-input").value;
  const visibleText = splitList(document.getElementById("visible-text-input").value);
  const namedObjects = splitList(document.getElementById("named-objects-input").value);
  const anchors = splitList(document.getElementById("location-anchors-input").value);
  const sceneSummary = document.getElementById("scene-summary-input").value.trim();

  if (peopleCount !== "") {
    annotations.push({
      observation_type: "people_count",
      number_value: Number(peopleCount),
      confidence: 0.94,
    });
  }
  if (engagement) {
    annotations.push({
      observation_type: "engagement_estimate",
      text_value: engagement,
      confidence: 0.78,
    });
  }
  for (const text of visibleText) {
    annotations.push({
      observation_type: "visible_text",
      text_value: text,
      confidence: 0.82,
    });
  }
  for (const objectName of namedObjects) {
    annotations.push({
      observation_type: "named_object",
      text_value: objectName,
      confidence: 0.76,
    });
  }
  for (const anchorName of anchors) {
    annotations.push({
      observation_type: "location_anchor",
      text_value: anchorName,
      confidence: 0.84,
    });
  }
  if (sceneSummary) {
    annotations.push({
      observation_type: "scene_summary",
      text_value: sceneSummary,
      confidence: 0.72,
    });
  }
  return annotations;
}

async function submitManualAnnotations() {
  const annotations = buildManualAnnotations();
  if (!annotations.length) {
    banner("Add at least one manual annotation before submitting perception.", "warning");
    return null;
  }
  return submitPerceptionSnapshot(
    {
      session_id: currentSessionId(),
      provider_mode: "manual_annotations",
      source: "operator_console_manual_annotations",
      annotations,
      source_frame: uploadedImageSourceFrame("manual_annotation_frame"),
      publish_events: true,
    },
    { bannerText: "Manual perception annotations submitted." },
  );
}

async function postVoiceState(status, extra = {}) {
  const payload = {
    session_id: currentSessionId(),
    voice_mode: currentVoiceMode(),
    status,
    message: extra.message || null,
    transcript_text: extra.transcriptText || null,
    source: extra.source || "browser_live_console",
    input_backend: extra.inputBackend || (isBrowserLiveMode() ? "browser_microphone" : "typed_input"),
    transcription_backend:
      extra.transcriptionBackend || (isBrowserLiveMode() ? (state.browserAudioSupported ? "browser_audio_capture" : "browser_speech_recognition") : "pass_through"),
    output_backend: extra.outputBackend || (usesMacSay() ? "macos_say" : "stub_tts"),
    confidence: extra.confidence ?? null,
    metadata: extra.metadata || {},
  };
  return requestJson("/api/operator/voice/state", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

function splitList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function uploadedImageSourceFrame(frameId = "uploaded-image") {
  if (!state.uploadedImage) {
    return null;
  }
  return {
    source_kind: "local_image_upload",
    source_label: state.uploadedImage.fileName || "uploaded_image",
    frame_id: frameId,
    mime_type: state.uploadedImage.mimeType,
    width_px: state.uploadedImage.width,
    height_px: state.uploadedImage.height,
    file_name: state.uploadedImage.fileName,
    captured_at: new Date().toISOString(),
  };
}

async function injectEvent(kind, overrides = {}) {
  const payload = {
    session_id: currentSessionId(),
    source: overrides.source || "operator_console",
    event_type: kind,
    payload: overrides.payload || {},
  };
  if (!overrides.payload) {
    if (kind === "person_detected") payload.payload = { confidence: 0.96 };
    if (kind === "touch") payload.payload = { zone: "head" };
    if (kind === "low_battery") payload.payload = { battery_pct: 11.0 };
    if (kind === "heartbeat") payload.payload = { network_ok: false, latency_ms: 850.0 };
  }

  const result = await requestJson("/api/operator/inject-event", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.selectedSessionId = result.session_id;
  document.getElementById("session-id-input").value = result.session_id;
  banner(`Injected ${kind}; outcome=${result.outcome}.`, toneForOutcome(result.outcome));
  refreshSnapshot();
}

async function forceSafeIdle() {
  const params = new URLSearchParams({
    session_id: currentSessionId(),
    reason: "operator_override",
  });
  const result = await requestJson(`/api/operator/safe-idle?${params.toString()}`, { method: "POST" });
  banner(`Safe idle forced; outcome=${result.outcome}.`, "danger");
  refreshSnapshot();
}

async function bodyAction(path, payload = null) {
  const result = await requestJson(path, {
    method: "POST",
    ...(payload ? { body: JSON.stringify(payload) } : {}),
  });
  const statusEl = document.getElementById("body-bench-status");
  statusEl.textContent = [
    `status=${result.status}`,
    result.detail ? `detail=${result.detail}` : null,
    result.report_path ? `report=${result.report_path}` : null,
    result.motion_report_path ? `motion=${result.motion_report_path}` : null,
  ].filter(Boolean).join(" | ");
  banner(
    `Body action ${path.split("/").pop()} -> ${result.status}${result.detail ? ` (${result.detail})` : ""}.`,
    result.ok ? "success" : "warning",
  );
  await refreshSnapshot();
  await refreshServoLabCatalog().catch(() => {});
  return result;
}

function renderServoLabResult(result, fallbackLabel = "Servo Lab action") {
  const resultEl = document.getElementById("servo-lab-result");
  const payload = result?.payload || result || {};
  const move = payload.servo_lab_move || null;
  const sweep = payload.servo_lab_sweep || null;
  const motion = payload.motion_control_summary || null;
  resultEl.textContent = [
    `${fallbackLabel}: status=${result.status || payload.status || "-"}`,
    result.detail ? `detail=${result.detail}` : null,
    move ? `effective_target=${move.effective_target}` : null,
    move?.clamp_notes?.length ? `clamps=${move.clamp_notes.join(",")}` : null,
    sweep ? `steps=${(sweep.steps || []).length}` : null,
    motion?.effective_speed != null ? `speed=${motion.effective_speed}` : null,
    motion?.effective_acceleration != null ? `accel=${motion.effective_acceleration}` : null,
    motion?.acceleration_status ? `acceleration=${motion.acceleration_status}` : null,
    result.motion_report_path ? `motion=${result.motion_report_path}` : null,
  ].filter(Boolean).join(" | ");
  renderJson("servo-lab-json", payload);
}

async function servoLabAction(path, payload, fallbackLabel) {
  const result = await requestJson(path, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  document.getElementById("servo-lab-status").textContent = [
    `status=${result.status}`,
    result.detail ? `detail=${result.detail}` : null,
    result.motion_report_path ? `motion=${result.motion_report_path}` : null,
    result.report_path ? `report=${result.report_path}` : null,
  ].filter(Boolean).join(" | ");
  renderServoLabResult(result, fallbackLabel);
  banner(
    `${fallbackLabel} -> ${result.status}${result.detail ? ` (${result.detail})` : ""}.`,
    result.ok ? "success" : "warning",
  );
  await refreshSnapshot();
  await refreshServoLabCatalog().catch(() => {});
  return result;
}

async function approveActionPlane(actionId) {
  const result = await requestJson(`/api/operator/action-plane/approvals/${actionId}/approve`, {
    method: "POST",
    body: JSON.stringify({ action_id: actionId }),
  });
  banner(`Action ${actionId} approved -> ${result.execution?.status || result.approval_state}.`, "success");
  await refreshSnapshot();
  return result;
}

function currentWorkflowId() {
  return document.getElementById("workflow-start-id-input").value;
}

function currentWorkflowInputs() {
  const raw = document.getElementById("workflow-inputs-input").value.trim();
  return raw ? JSON.parse(raw) : {};
}

function currentWorkflowNote() {
  return document.getElementById("workflow-note-input").value.trim() || null;
}

async function startWorkflow() {
  const result = await requestJson("/api/operator/action-plane/workflows/start", {
    method: "POST",
    body: JSON.stringify({
      workflow_id: currentWorkflowId(),
      session_id: currentSessionId(),
      inputs: currentWorkflowInputs(),
      note: currentWorkflowNote(),
    }),
  });
  banner(`Workflow ${result.workflow_id} -> ${result.status}.`, result.status === "completed" ? "success" : "neutral");
  await refreshSnapshot();
  notifyActionCenterIfNeeded("Workflow follow-up");
  return result;
}

async function resumeWorkflow(workflowRunId) {
  const result = await requestJson(`/api/operator/action-plane/workflows/runs/${workflowRunId}/resume`, {
    method: "POST",
    body: JSON.stringify({ note: currentWorkflowNote() }),
  });
  banner(`Workflow ${workflowRunId} resume -> ${result.status}.`, result.status === "completed" ? "success" : "neutral");
  await refreshSnapshot();
  return result;
}

async function retryWorkflow(workflowRunId) {
  const result = await requestJson(`/api/operator/action-plane/workflows/runs/${workflowRunId}/retry`, {
    method: "POST",
    body: JSON.stringify({ note: currentWorkflowNote() }),
  });
  banner(`Workflow ${workflowRunId} retry -> ${result.status}.`, result.status === "completed" ? "success" : "warning");
  await refreshSnapshot();
  return result;
}

async function pauseWorkflow(workflowRunId) {
  const result = await requestJson(`/api/operator/action-plane/workflows/runs/${workflowRunId}/pause`, {
    method: "POST",
    body: JSON.stringify({ note: currentWorkflowNote() }),
  });
  banner(`Workflow ${workflowRunId} paused.`, "warning");
  await refreshSnapshot();
  return result;
}

async function rejectActionPlane(actionId) {
  const result = await requestJson(`/api/operator/action-plane/approvals/${actionId}/reject`, {
    method: "POST",
    body: JSON.stringify({ action_id: actionId }),
  });
  banner(`Action ${actionId} rejected.`, "warning");
  await refreshSnapshot();
  return result;
}

async function loadActionBundle(bundleId, { quiet = false } = {}) {
  const detail = await requestJson(`/api/operator/action-plane/bundles/${bundleId}`);
  state.selectedActionBundle = detail;
  setActionCenterSelection({
    kind: "bundle",
    severity: detail.manifest.final_status && detail.manifest.final_status !== "completed" ? "medium" : "low",
    title: detail.manifest.bundle_id,
    summary: detail.manifest.outcome_summary || detail.result?.summary || detail.manifest.requested_workflow_id || detail.manifest.requested_tool_name || "Action bundle",
    action_id: null,
    workflow_run_id: detail.manifest.workflow_run_id || null,
    bundle_id,
    session_id: detail.manifest.session_id || null,
    next_step_hint: "Inspect the bundle evidence, then replay or attach teacher feedback if needed.",
    detail_ref: bundleId,
  });
  document.getElementById("bundle-review-id-input").value = bundleId;
  document.getElementById("action-flywheel-summary").textContent = [
    `bundle=${detail.manifest.bundle_id}`,
    `status=${detail.manifest.final_status || "-"}`,
    `approvals=${(detail.approval_events || []).length}`,
    `connector_calls=${(detail.connector_calls || []).length}`,
    `replays=${(detail.replays || []).length}`,
    `teacher=${(detail.teacher_annotations || []).length}`,
  ].join(" | ");
  if (state.actionPlaneOverview) {
    renderActionCenter(state.actionPlaneOverview);
  }
  if (!quiet) {
    banner(`Loaded action bundle ${bundleId}.`, "neutral");
  }
  return detail;
}

async function replayActionPlane(actionId) {
  const result = await requestJson("/api/operator/action-plane/replay", {
    method: "POST",
    body: JSON.stringify({ action_id: actionId }),
  });
  banner(`Action ${actionId} replayed -> ${result.status}.`, result.status === "executed" ? "success" : "warning");
  await refreshSnapshot();
  return result;
}

function currentBundleReviewPayload() {
  return {
    review_value: document.getElementById("bundle-review-value-input").value,
    note: document.getElementById("bundle-review-note-input").value.trim() || null,
    author: document.getElementById("teacher-author-input").value.trim() || "operator_console",
    action_feedback_labels: splitCsv(document.getElementById("bundle-action-feedback-input").value),
  };
}

async function replayActionBundle(bundleId) {
  const result = await requestJson("/api/operator/action-plane/replays", {
    method: "POST",
    body: JSON.stringify({ bundle_id: bundleId }),
  });
  state.lastActionBundleReplay = result;
  banner(`Bundle ${bundleId} replay -> ${result.status}.`, result.status === "completed" ? "success" : "warning");
  await refreshSnapshot();
  return result;
}

async function submitActionBundleTeacherReview() {
  const bundleId = document.getElementById("bundle-review-id-input").value.trim();
  if (!bundleId) {
    banner("Enter or load a bundle id first.", "warning");
    return;
  }
  await requestJson(`/api/operator/action-plane/bundles/${bundleId}/teacher-review`, {
    method: "POST",
    body: JSON.stringify(currentBundleReviewPayload()),
  });
  banner(`Bundle teacher review saved for ${bundleId}.`, "success");
  await loadActionBundle(bundleId);
  await refreshSnapshot();
}

function currentBrowserTargetHint() {
  const raw = document.getElementById("browser-task-target-hint-input").value.trim();
  if (!raw) {
    return null;
  }
  return {
    label: raw,
    text: raw,
    placeholder: raw,
    field_name: raw,
  };
}

async function runBrowserTask(requestedActionOverride = null) {
  const requestedAction = requestedActionOverride || document.getElementById("browser-task-action-input").value;
  const payload = {
    session_id: currentSessionId(),
    query: document.getElementById("browser-task-url-input").value.trim() || requestedAction,
    target_url: document.getElementById("browser-task-url-input").value.trim() || null,
    requested_action: requestedAction,
    target_hint: currentBrowserTargetHint(),
    text_input: document.getElementById("browser-task-text-input").value.trim() || null,
  };
  if (requestedAction === "type_text" && !payload.text_input) {
    banner("Text input is required for type_text.", "warning");
    return null;
  }
  const result = await requestJson("/api/operator/action-plane/browser/task", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await refreshSnapshot();
  if (!notifyActionCenterIfNeeded("Browser task ready")) {
    banner(
      `Browser task ${requestedAction} -> ${result.status}${result.detail ? ` (${result.detail})` : ""}.`,
      result.status === "ok" ? "success" : "warning",
    );
  }
  return result;
}

async function connectBody() {
  await bodyAction("/api/operator/body/connect", {
    port: currentBodyPort() || null,
    baud: currentBodyBaud(),
  });
}

async function disconnectBody() {
  await bodyAction("/api/operator/body/disconnect");
}

async function scanBody() {
  await bodyAction("/api/operator/body/scan", {});
}

async function pingBody() {
  await bodyAction("/api/operator/body/ping", {});
}

async function readBodyHealth() {
  await bodyAction("/api/operator/body/read-health", {});
}

async function armBodyMotion() {
  await bodyAction("/api/operator/body/arm", {
    ttl_seconds: currentBodyArmTtl(),
  });
}

async function disarmBodyMotion() {
  await bodyAction("/api/operator/body/disarm");
}

async function writeBodyNeutral() {
  await bodyAction("/api/operator/body/write-neutral");
}

async function readServoLabCurrent() {
  const result = await requestJson("/api/operator/body/servo-lab/readback", {
    method: "POST",
    body: JSON.stringify({
      joint_name: currentServoLabJoint() || null,
      include_health: true,
    }),
  });
  document.getElementById("servo-lab-status").textContent = [
    `status=${result.status}`,
    result.detail ? `detail=${result.detail}` : null,
  ].filter(Boolean).join(" | ");
  const payload = result.payload || {};
  const catalog = payload.catalog || null;
  if (catalog) {
    state.bodyServoLabCatalog = catalog;
    renderServoLabCatalog(catalog);
  }
  renderServoLabResult(result, "Servo Lab readback");
  banner(
    `Servo Lab readback -> ${result.status}${result.detail ? ` (${result.detail})` : ""}.`,
    result.ok ? "success" : "warning",
  );
  await refreshSnapshot();
  return result;
}

async function moveServoLabJoint(overrides = {}) {
  return servoLabAction("/api/operator/body/servo-lab/move", {
    joint_name: currentServoLabJoint(),
    reference_mode: overrides.reference_mode || currentServoLabReferenceMode(),
    target_raw: overrides.target_raw ?? currentServoLabTargetRaw(),
    delta_counts: overrides.delta_counts ?? null,
    lab_min: overrides.lab_min ?? currentServoLabLabMin(),
    lab_max: overrides.lab_max ?? currentServoLabLabMax(),
    duration_ms: overrides.duration_ms ?? currentServoLabDurationMs(),
    speed_override: overrides.speed_override ?? currentServoLabSpeedOverride(),
    acceleration_override: overrides.acceleration_override ?? currentServoLabAccelerationOverride(),
    note: overrides.note ?? "operator_console_servo_lab_move",
  }, "Servo Lab move");
}

async function stepServoLabJoint(direction) {
  const step = Math.abs(currentServoLabStepSize()) * (direction < 0 ? -1 : 1);
  return moveServoLabJoint({
    reference_mode: "current_delta",
    target_raw: null,
    delta_counts: step,
    note: `operator_console_servo_lab_step:${direction < 0 ? "minus" : "plus"}`,
  });
}

async function moveServoLabToBound(kind) {
  const joint = currentServoLabJointRecord();
  if (!joint) {
    banner("Select a Servo Lab joint first.", "warning");
    return null;
  }
  const target =
    kind === "min"
      ? (currentServoLabLabMin() ?? joint.raw_min)
      : kind === "max"
        ? (currentServoLabLabMax() ?? joint.raw_max)
        : joint.neutral;
  return moveServoLabJoint({
    reference_mode: "absolute_raw",
    target_raw: target,
    delta_counts: null,
    note: `operator_console_servo_lab_go_${kind}`,
  });
}

async function sweepServoLabJoint() {
  return servoLabAction("/api/operator/body/servo-lab/sweep", {
    joint_name: currentServoLabJoint(),
    lab_min: currentServoLabLabMin(),
    lab_max: currentServoLabLabMax(),
    cycles: 1,
    duration_ms: currentServoLabDurationMs(),
    dwell_ms: 250,
    speed_override: currentServoLabSpeedOverride(),
    acceleration_override: currentServoLabAccelerationOverride(),
    return_to_neutral: true,
    note: "operator_console_servo_lab_sweep",
  }, "Servo Lab sweep");
}

async function saveServoLabCurrentAsNeutral() {
  return servoLabAction("/api/operator/body/servo-lab/save-calibration", {
    joint_name: currentServoLabJoint(),
    save_current_as_neutral: true,
    raw_min: null,
    raw_max: null,
    confirm_mirrored: null,
    note: "operator_console_save_current_neutral",
  }, "Servo Lab save neutral");
}

async function saveServoLabRangeToCalibration() {
  return servoLabAction("/api/operator/body/servo-lab/save-calibration", {
    joint_name: currentServoLabJoint(),
    save_current_as_neutral: false,
    raw_min: currentServoLabLabMin(),
    raw_max: currentServoLabLabMax(),
    confirm_mirrored: null,
    note: "operator_console_save_lab_range",
  }, "Servo Lab save range");
}

async function runBodySemanticSmoke() {
  await bodyAction("/api/operator/body/semantic-smoke", {
    action: currentBodySemanticSmoke(),
    intensity: currentBodySemanticIntensity(),
    repeat_count: currentBodySemanticRepeatCount(),
    note: currentBodyTeacherNote(),
  });
}

async function submitBodyTeacherReview() {
  await bodyAction("/api/operator/body/teacher-review", {
    action: currentBodySemanticSmoke(),
    review: currentBodyTeacherReview(),
    note: currentBodyTeacherNote(),
    proposed_tuning_delta: currentBodyTeacherDelta(),
    apply_tuning: currentBodyApplyTuning(),
  });
}

async function runShiftTick() {
  const result = await requestJson("/api/operator/shift/tick", {
    method: "POST",
    body: JSON.stringify({
      session_id: currentSessionId(),
      source: "operator_console",
    }),
  });
  banner(
    result.response.reply_text || `Shift tick complete; state=${result.shift_supervisor?.state || "-"}.`,
    toneForOutcome(result.outcome),
  );
  await refreshSnapshot();
}

async function acknowledgeIncident() {
  const ticketId = currentIncidentId();
  if (!ticketId) {
    banner("Select an incident ticket first.", "warning");
    return;
  }
  const operatorName = document.getElementById("incident-operator-input").value.trim() || "operator";
  const note = document.getElementById("incident-note-input").value.trim() || null;
  await requestJson(`/api/operator/incidents/${ticketId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ operator_name: operatorName, note }),
  });
  banner(`Incident ${ticketId} acknowledged by ${operatorName}.`, "success");
  document.getElementById("incident-note-input").value = "";
  await refreshSnapshot();
}

async function assignIncident() {
  const ticketId = currentIncidentId();
  if (!ticketId) {
    banner("Select an incident ticket first.", "warning");
    return;
  }
  const assigneeName = document.getElementById("incident-operator-input").value.trim();
  if (!assigneeName) {
    banner("Enter the operator or staff name before assigning the ticket.", "warning");
    return;
  }
  const note = document.getElementById("incident-note-input").value.trim() || null;
  await requestJson(`/api/operator/incidents/${ticketId}/assign`, {
    method: "POST",
    body: JSON.stringify({ assignee_name: assigneeName, author: "operator_console", note }),
  });
  banner(`Incident ${ticketId} assigned to ${assigneeName}.`, "success");
  document.getElementById("incident-note-input").value = "";
  await refreshSnapshot();
}

async function addIncidentNote() {
  const ticketId = currentIncidentId();
  if (!ticketId) {
    banner("Select an incident ticket first.", "warning");
    return;
  }
  const text = document.getElementById("incident-note-input").value.trim();
  if (!text) {
    banner("Enter an incident note before submitting it.", "warning");
    return;
  }
  const author = document.getElementById("incident-operator-input").value.trim() || "operator_console";
  await requestJson(`/api/operator/incidents/${ticketId}/notes`, {
    method: "POST",
    body: JSON.stringify({ text, author }),
  });
  banner(`Incident note added to ${ticketId}.`, "success");
  document.getElementById("incident-note-input").value = "";
  await refreshSnapshot();
}

async function resolveIncident() {
  const ticketId = currentIncidentId();
  if (!ticketId) {
    banner("Select an incident ticket first.", "warning");
    return;
  }
  const author = document.getElementById("incident-operator-input").value.trim() || "operator_console";
  const note = document.getElementById("incident-note-input").value.trim() || null;
  const outcome = document.getElementById("incident-resolution-input").value;
  await requestJson(`/api/operator/incidents/${ticketId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ outcome, author, note }),
  });
  banner(`Incident ${ticketId} closed with outcome ${outcome}.`, outcome === "no_operator_available" ? "warning" : "success");
  document.getElementById("incident-note-input").value = "";
  await refreshSnapshot();
}

async function cancelVoice() {
  if (state.browserRecognition && state.browserListening) {
    state.browserManualStop = true;
    state.browserRecognition.stop();
    await postVoiceState("interrupted", {
      message: "browser_listening_cancelled",
      source: "browser_speech_recognition",
    }).catch(() => {});
  }

  const params = new URLSearchParams({
    session_id: currentSessionId(),
    voice_mode: currentVoiceMode(),
  });
  const result = await requestJson(`/api/operator/voice/cancel?${params.toString()}`, { method: "POST" });
  banner(`Voice status: ${result.state.status}.`, "warning");
  refreshSnapshot();
}

async function runScenario(name) {
  const payload = {
    scenario_names: [name],
    response_mode: currentResponseMode(),
    reset_brain_first: false,
    reset_edge_first: false,
    stop_on_failure: false,
  };
  const result = await requestJson("/api/demo-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  banner(`Scenario ${name} finished with status ${result.status}.`, result.status === "completed" ? "success" : "danger");
  await refreshSnapshot();
}

async function runScene(sceneName, suggestedSessionId) {
  const payload = {
    session_id: state.selectedSessionId || suggestedSessionId,
    response_mode: currentResponseMode(),
    voice_mode: currentVoiceMode(),
    speak_reply: speakReplyEnabled(),
  };
  const result = await requestJson(`/api/operator/investor-scenes/${sceneName}/run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.selectedSessionId = result.session_id;
  document.getElementById("session-id-input").value = result.session_id;
  banner(`${result.title}: ${result.note}`, result.success ? "success" : "danger");
  state.replayInspector = replayInspectorFromScene(result);
  renderReplayInspector(state.replayInspector);
  await refreshSnapshot();
}

async function runDesktopStory() {
  banner("Resetting runtime and running the desktop investor story...", "neutral");
  await resetRuntime();
  const failures = [];
  for (const sceneName of desktopStoryScenes) {
    const scene = state.scenes.find((item) => item.scene_name === sceneName);
    try {
      await runScene(sceneName, scene?.session_id);
    } catch (error) {
      failures.push(`${sceneName}:${error.message}`);
      break;
    }
  }
  if (failures.length) {
    banner(`Desktop story degraded at ${failures[0]}.`, "warning");
    return;
  }
  banner("Desktop story completed.", "success");
}

async function runLocalCompanionStory() {
  banner("Resetting runtime and running the maintained local companion story...", "neutral");
  await resetRuntime();
  const failures = [];
  for (const sceneName of localCompanionStoryScenes) {
    const scene = state.scenes.find((item) => item.scene_name === sceneName);
    try {
      await runScene(sceneName, scene?.session_id);
    } catch (error) {
      failures.push(`${sceneName}:${error.message}`);
      break;
    }
  }
  if (failures.length) {
    banner(`Local companion story degraded at ${failures[0]}.`, "warning");
    return;
  }
  banner("Local companion story completed.", "success");
}

function formatPayloadSummary(payload) {
  const entries = Object.entries(payload || {});
  if (!entries.length) {
    return "No payload details.";
  }
  return entries
    .slice(0, 4)
    .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`)
    .join(" | ");
}

function splitCsv(value) {
  return (value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseMemoryUpdates() {
  const raw = document.getElementById("memory-updates-input").value.trim();
  if (!raw) {
    return {};
  }
  return JSON.parse(raw);
}

function teacherReviewPayload() {
  return {
    review_value: document.getElementById("teacher-review-value-input").value,
    label: document.getElementById("teacher-label-input").value.trim() || null,
    note: document.getElementById("teacher-note-input").value.trim() || null,
    author: document.getElementById("teacher-author-input").value.trim() || "operator_console",
    better_reply_text: document.getElementById("teacher-better-reply-input").value.trim() || null,
    corrected_scene_summary: document.getElementById("teacher-scene-correction-input").value.trim() || null,
    preferred_body_expression: document.getElementById("teacher-body-expression-input").value.trim() || null,
    outcome_label: document.getElementById("teacher-outcome-label-input").value.trim() || null,
    benchmark_tags: splitCsv(document.getElementById("teacher-benchmark-tags-input").value),
  };
}

function memoryReviewPayload() {
  return {
    memory_id: document.getElementById("memory-teacher-target-input").value.trim(),
    layer: document.getElementById("memory-layer-input").value,
    note: document.getElementById("teacher-note-input").value.trim() || null,
    author: document.getElementById("teacher-author-input").value.trim() || "operator_console",
    updated_fields: parseMemoryUpdates(),
  };
}

async function inspectEpisode(episodeId) {
  const episode = await requestJson(`/api/operator/episodes/${episodeId}`);
  state.selectedEpisodeId = episode.episode_id;
  document.getElementById("episode-teacher-target-input").value = episode.episode_id;
  document.getElementById("benchmark-episode-id-input").value = episode.episode_id;
  document.getElementById("trace-teacher-target-input").value =
    episode.traces?.[episode.traces.length - 1]?.trace_id || "";
  const firstMemoryAction = episode.memory_actions?.[0];
  if (firstMemoryAction) {
    document.getElementById("memory-teacher-target-input").value = firstMemoryAction.memory_id || "";
    document.getElementById("memory-layer-input").value = firstMemoryAction.layer || "semantic";
  }
  renderTeacherAnnotations(episode.teacher_annotations || []);
  renderJson("episode-json", episode);
  renderEpisodes(state.episodes);
  banner(`Episode ${episode.episode_id} loaded.`, "neutral");
}

async function exportCurrentSessionEpisode() {
  const sessionId = currentSessionId();
  const episode = await requestJson("/api/operator/episodes/export-session", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      redact_operator_notes: false,
      redact_session_memory: false,
      include_asset_refs: true,
    }),
  });
  state.selectedEpisodeId = episode.episode_id;
  banner(`Session ${sessionId} exported as episode ${episode.episode_id}.`, "success");
  await loadEpisodes(episode.episode_id);
  await inspectEpisode(episode.episode_id);
}

async function exportLatestRunEpisode() {
  const latestRun = state.latestDemoRuns?.[0];
  if (!latestRun) {
    banner("Run a demo scenario before exporting a demo-run episode.", "warning");
    return;
  }
  const episode = await requestJson("/api/operator/episodes/export-demo-run", {
    method: "POST",
    body: JSON.stringify({
      run_id: latestRun.run_id,
      redact_operator_notes: false,
      redact_session_memory: false,
      include_asset_refs: true,
    }),
  });
  state.selectedEpisodeId = episode.episode_id;
  banner(`Demo run ${latestRun.run_id} exported as episode ${episode.episode_id}.`, "success");
  await loadEpisodes(episode.episode_id);
  await inspectEpisode(episode.episode_id);
}

async function submitEpisodeTeacherReview() {
  const episodeId = document.getElementById("episode-teacher-target-input").value.trim() || state.selectedEpisodeId;
  if (!episodeId) {
    banner("Load or enter an episode id first.", "warning");
    return;
  }
  await requestJson(`/api/operator/episodes/${episodeId}/teacher`, {
    method: "POST",
    body: JSON.stringify(teacherReviewPayload()),
  });
  banner(`Episode teacher review saved for ${episodeId}.`, "success");
  await loadEpisodes(episodeId);
  await inspectEpisode(episodeId);
}

async function submitTraceTeacherReview() {
  const traceId = document.getElementById("trace-teacher-target-input").value.trim();
  if (!traceId) {
    banner("Enter a trace id first.", "warning");
    return;
  }
  await requestJson(`/api/operator/traces/${traceId}/teacher/review`, {
    method: "POST",
    body: JSON.stringify(teacherReviewPayload()),
  });
  banner(`Trace teacher review saved for ${traceId}.`, "success");
  if (state.selectedEpisodeId) {
    await inspectEpisode(state.selectedEpisodeId);
  }
}

async function submitMemoryReview(action) {
  const payload = memoryReviewPayload();
  if (!payload.memory_id) {
    banner("Enter a memory id first.", "warning");
    return;
  }
  await requestJson(`/api/operator/memory/${action}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  banner(`Memory ${action} saved for ${payload.memory_id}.`, action === "delete" ? "warning" : "success");
  if (state.selectedEpisodeId) {
    await inspectEpisode(state.selectedEpisodeId);
  }
  await refreshSnapshot();
}

async function runBenchmarks() {
  const episodeId = document.getElementById("benchmark-episode-id-input").value.trim() || state.selectedEpisodeId;
  if (!episodeId) {
    banner("Load or enter an episode id before running benchmarks.", "warning");
    return;
  }
  const families = splitCsv(document.getElementById("benchmark-families-input").value);
  const result = await requestJson("/api/operator/benchmarks/run", {
    method: "POST",
    body: JSON.stringify({
      episode_id: episodeId,
      families,
    }),
  });
  banner(`Benchmark run recorded for ${episodeId}: ${result.score}/${result.max_score}.`, result.passed ? "success" : "warning");
  await loadBenchmarks();
}

function toneForOutcome(outcome) {
  if (outcome === "ok") return "success";
  if (outcome === "safe_fallback" || outcome === "fallback_reply") return "warning";
  return "danger";
}

function toneForPerception(result) {
  if (!result.success || result.snapshot?.status === "failed") return "danger";
  if (result.snapshot?.limited_awareness || result.snapshot?.status === "degraded") return "warning";
  return "success";
}

function updateLiveControlAvailability() {
  const browserMode = isBrowserLiveMode();
  const browserMicAvailable = state.browserAudioSupported || state.browserSpeechSupported;
  const startBtn = document.getElementById("start-listening-btn");
  const stopBtn = document.getElementById("stop-listening-btn");
  const enableCameraBtn = document.getElementById("enable-camera-btn");
  const disableCameraBtn = document.getElementById("disable-camera-btn");
  const captureSnapshotBtn = document.getElementById("capture-snapshot-btn");
  const sendCameraCueBtn = document.getElementById("send-camera-cue-btn");
  const submitImageBtn = document.getElementById("submit-image-btn");
  const note = document.getElementById("camera-status-note");
  const voiceHowToEl = document.getElementById("voice-howto-note");

  startBtn.disabled = !browserMode || !browserMicAvailable || state.browserListening;
  stopBtn.disabled = !browserMode || !state.browserListening;
  stopBtn.textContent = state.browserListening ? "Stop Mic + Send" : "Stop Mic";
  enableCameraBtn.disabled = !state.cameraSupported;
  disableCameraBtn.disabled = !state.cameraSupported || !state.cameraStream;
  captureSnapshotBtn.disabled = !state.cameraSupported;
  sendCameraCueBtn.disabled = !state.cameraSupported;
  submitImageBtn.disabled = !state.uploadedImage;

  if (!browserMode) {
    voiceHowToEl.textContent =
      "To speak with the AI, switch Voice Mode to browser_live or browser_live_macos_say, then either hold Space to talk and release to send, or click Start Mic, speak, and click Stop Mic to submit.";
  } else if (currentVoiceMode() === "browser_live_macos_say") {
    voiceHowToEl.textContent =
      shouldPreferBrowserSpeechRecognition()
        ? "Live voice is ready. The console is using fast browser speech recognition first. Hold Space to talk and release to send, or click Start Mic and speak. The AI answers in text and through the speaker when available."
        : "Live voice is ready. Hold Space to talk and release to send, or click Start Mic, speak, and click Stop Mic to submit. The AI answers in text and through the speaker when available.";
  } else {
    voiceHowToEl.textContent =
      shouldPreferBrowserSpeechRecognition()
        ? "Live voice is ready. The console is using fast browser speech recognition first. Hold Space to talk and release to send, or click Start Mic and speak. The AI answers in text; enable Speak reply or switch to browser_live_macos_say for spoken playback."
        : "Live voice is ready. Hold Space to talk and release to send, or click Start Mic, speak, and click Stop Mic to submit. The AI answers in text; enable Speak reply or switch to browser_live_macos_say for spoken playback.";
  }

  if (!state.cameraSupported) {
    note.textContent = "Browser camera cue is unavailable in this browser.";
  } else if (state.cameraStream) {
    note.textContent =
      "Camera is active. Visual questions now auto-submit a fresh frame to the live vision backend when available. Capture Snapshot still sends a manual frame into the perception layer, and Disable Camera turns it off immediately.";
  } else if (state.uploadedImage) {
    note.textContent = `Selected image: ${state.uploadedImage.fileName || "uploaded image"} (${state.uploadedImage.width || "-"}x${state.uploadedImage.height || "-"})`;
  } else {
    note.textContent = "Camera cue inactive.";
  }
}

function updateBrainStatusSummary(snapshot) {
  const summaryEl = document.getElementById("brain-status-summary");
  const runtime = snapshot?.runtime || {};
  const actionPlane = runtime.action_plane || {};
  const initiative = runtime.initiative_engine || {};
  const presence = runtime.presence_runtime || {};
  summaryEl.textContent = [
    runtime.profile_summary || runtime.runtime_profile || "profile:-",
    `context=${runtime.context_mode || "-"}`,
    `audio=${runtime.audio_mode || "-"}:${runtime.audio_loop?.state || "-"}`,
    `presence=${presence.state || "-"}`,
    `initiative=${initiative.suppression_reason ? "silenced" : initiative.last_decision || "-"}`,
    runtime.setup_complete ? "setup=ready" : "setup=review",
    `actions p${actionPlane.pending_approval_count ?? 0}/w${actionPlane.waiting_workflow_count ?? 0}/r${actionPlane.review_required_count ?? 0}`,
  ].join(" | ");
}

function activeVoicePreviewText() {
  if (!isBrowserLiveMode()) {
    return null;
  }
  if (state.browserSubmitting) {
    return "Transcribing recorded speech and sending it to the AI...";
  }
  if (state.browserListening) {
    return state.browserShortcutHeld
      ? "Listening now. Release Space to send your speech to the AI."
      : "Listening now. Click Stop Mic + Send when you finish speaking.";
  }
  return null;
}

function shouldPauseBackgroundPolling() {
  return state.turnInFlight || state.browserListening || state.browserSubmitting;
}

function handleVoiceModeChange() {
  state.voiceMode = currentVoiceMode();
  if (isBrowserLiveMode() && !(state.browserAudioSupported || state.browserSpeechSupported)) {
    banner("Browser speech recognition is unavailable here. Typed input remains the safe fallback.", "warning");
  }
  updateLiveControlAvailability();
  refreshSnapshot().catch(handleError);
}

function handlePerceptionModeChange() {
  const mode = currentPerceptionMode();
  if (mode === "multimodal_llm") {
    banner("multimodal_llm mode requires configured provider credentials. Stub, manual annotations, and fixture replay remain the safe fallback paths.", "warning");
  } else if (mode === "browser_snapshot") {
    banner("browser_snapshot only stores the frame. For semantic answers about the live camera, prefer ollama_vision when it is available.", "warning");
  }
  updateLiveControlAvailability();
}

function browserAudioMimeType() {
  if (!window.MediaRecorder) {
    return "";
  }
  for (const candidate of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"]) {
    if (window.MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return "";
}

function stopMediaStream(stream) {
  if (!stream) {
    return;
  }
  stream.getTracks().forEach((track) => track.stop());
}

async function ensureBrowserAudioStream({ forceRestart = false } = {}) {
  if (!state.browserAudioSupported) {
    return null;
  }
  const currentDeviceId = state.browserAudioStream?.getAudioTracks?.()[0]?.getSettings?.().deviceId || "";
  if (state.browserAudioStream && !forceRestart) {
    if (!state.selectedBrowserMicrophoneId || currentDeviceId === state.selectedBrowserMicrophoneId) {
      return state.browserAudioStream;
    }
  }
  stopMediaStream(state.browserAudioStream);
  state.browserAudioStream = await navigator.mediaDevices.getUserMedia({
    audio: state.selectedBrowserMicrophoneId ? { deviceId: { exact: state.selectedBrowserMicrophoneId } } : true,
    video: false,
  });
  return state.browserAudioStream;
}

async function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("browser_audio_read_failed"));
    reader.readAsDataURL(blob);
  });
}

async function submitBrowserAudioCapture(blob, mimeType) {
  const transcriptPreview = document.getElementById("voice-transcript-preview");
  let cameraFrame = null;
  let cameraCaptureMs = null;
  if (state.cameraStream) {
    try {
      const captureStarted = performance.now();
      cameraFrame = await captureCameraFrame();
      cameraCaptureMs = Math.round((performance.now() - captureStarted) * 100) / 100;
    } catch (_) {
      cameraFrame = null;
      cameraCaptureMs = null;
    }
  }
  state.turnInFlight = true;
  try {
    await postVoiceState("transcribing", {
      message: "browser_audio_uploading",
      source: "browser_audio_capture",
      inputBackend: "browser_microphone",
      transcriptionBackend: "browser_audio_capture",
      metadata: {
        browser_device_id: state.selectedBrowserMicrophoneId || null,
        browser_device_label: selectedBrowserMicrophoneLabel(),
      },
    }).catch(() => {});
    const result = await requestJson("/api/operator/browser-audio-turn", {
      method: "POST",
      body: JSON.stringify({
        session_id: currentSessionId(),
        user_id: document.getElementById("user-id-input").value.trim() || null,
        response_mode: currentResponseMode(),
        voice_mode: currentVoiceMode(),
        speak_reply: speakReplyEnabled(),
        source: "browser_audio_capture",
        audio_data_url: await blobToDataUrl(blob),
        mime_type: mimeType || blob.type || null,
        camera_image_data_url: cameraFrame?.dataUrl || null,
        camera_source_frame: cameraFrame
          ? {
              source_kind: "browser_camera_snapshot",
              source_label: "operator_console_camera",
              frame_id: `camera-voice-${Date.now()}`,
              mime_type: cameraFrame.mimeType,
              width_px: cameraFrame.width,
              height_px: cameraFrame.height,
              captured_at: cameraFrame.capturedAt,
            }
          : null,
        camera_provider_mode: preferredLiveCameraPerceptionMode(),
        input_metadata: {
          capture_mode: "browser_microphone",
          browser_device_id: state.selectedBrowserMicrophoneId || null,
          browser_device_label: selectedBrowserMicrophoneLabel(),
          browser_camera_capture_ms: cameraCaptureMs,
          client_submit_wall_time_ms: Date.now(),
        },
      }),
      timeoutMs: liveTurnTimeoutMs({
        source: "browser_audio_capture",
        voiceMode: currentVoiceMode(),
        text: transcriptPreview.textContent || "",
        hasCameraPayload: Boolean(cameraFrame?.dataUrl),
      }),
    });
    transcriptPreview.textContent = result.transcript_text || "No live transcript yet.";
    await postVoiceState("idle", {
      message: "browser_audio_complete",
      source: "browser_audio_capture",
      transcriptText: result.transcript_text || null,
      inputBackend: "browser_microphone",
      transcriptionBackend: result.transcription_backend || "local_stt",
      metadata: {
        browser_device_id: state.selectedBrowserMicrophoneId || null,
        browser_device_label: selectedBrowserMicrophoneLabel(),
      },
    }).catch(() => {});
    state.selectedSessionId = result.interaction.session_id;
    document.getElementById("session-id-input").value = result.interaction.session_id;
    banner(`Reply: ${result.interaction.response.reply_text || "no spoken reply"}`, toneForOutcome(result.interaction.outcome));
    await refreshSnapshot();
    return result;
  } finally {
    state.turnInFlight = false;
  }
}

function ensureBrowserRecognition() {
  if (state.browserRecognition) {
    return state.browserRecognition;
  }
  const Recognition = speechRecognitionCtor();
  state.browserSpeechSupported = Boolean(Recognition);
  if (!Recognition) {
    updateLiveControlAvailability();
    return null;
  }

  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.continuous = false;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;

  recognition.onstart = async () => {
    state.browserListening = true;
    state.browserManualStop = false;
    state.browserRecognitionStartedAt = performance.now();
    updateLiveControlAvailability();
    banner("Browser microphone listening...", "neutral");
    await postVoiceState("listening", {
      message: "browser_microphone_active",
      source: "browser_speech_recognition",
    }).catch(() => {});
    refreshSnapshot().catch(() => {});
  };

  recognition.onresult = async (event) => {
    let finalTranscript = "";
    let interimTranscript = "";
    let confidence = null;

    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const alternative = result[0];
      if (result.isFinal) {
        finalTranscript += alternative.transcript;
        confidence = alternative.confidence ?? confidence;
      } else {
        interimTranscript += alternative.transcript;
      }
    }

    if (interimTranscript) {
      document.getElementById("voice-transcript-preview").textContent = interimTranscript.trim();
      await postVoiceState("transcribing", {
        transcriptText: interimTranscript.trim(),
        message: "browser_transcribing",
        source: "browser_speech_recognition",
      }).catch(() => {});
    }

    if (finalTranscript.trim() && !state.browserSubmitting) {
      state.browserSubmitting = true;
      try {
        await postVoiceState("thinking", {
          transcriptText: finalTranscript.trim(),
          message: "browser_transcript_captured",
          source: "browser_speech_recognition",
          confidence,
          metadata: { confidence },
        }).catch(() => {});
        await sendTextTurn({
          inputText: finalTranscript.trim(),
          voiceMode: currentVoiceMode(),
          source: "browser_speech_recognition",
          inputMetadata: {
            capture_mode: "browser_microphone",
            transcription_backend: "browser_speech_recognition",
            confidence,
            browser_speech_recognition_ms:
              state.browserRecognitionStartedAt !== null
                ? Math.round((performance.now() - state.browserRecognitionStartedAt) * 100) / 100
                : null,
          },
          clearInput: false,
          bannerText: "Browser live turn submitted.",
        });
      } finally {
        state.browserSubmitting = false;
      }
    }
  };

  recognition.onerror = async (event) => {
    state.browserListening = false;
    state.browserSubmitting = false;
    updateLiveControlAvailability();
    const errorCode = event.error || "browser_recognition_error";
    banner(`Microphone recognition failed: ${errorCode}. Typed input remains available.`, "warning");
    await postVoiceState("failed", {
      message: errorCode,
      source: "browser_speech_recognition",
      metadata: { error_code: errorCode },
    }).catch(() => {});
    refreshSnapshot().catch(() => {});
  };

  recognition.onend = async () => {
    const manualStop = state.browserManualStop;
    state.browserListening = false;
    state.browserManualStop = false;
    state.browserRecognitionStartedAt = null;
    updateLiveControlAvailability();
    if (state.browserSubmitting) {
      return;
    }
    await postVoiceState(manualStop ? "interrupted" : "idle", {
      message: manualStop ? "browser_listening_stopped" : "browser_listening_complete",
      source: "browser_speech_recognition",
    }).catch(() => {});
    refreshSnapshot().catch(() => {});
  };

  state.browserRecognition = recognition;
  updateLiveControlAvailability();
  return recognition;
}

async function startBrowserListening() {
  if (!isBrowserLiveMode()) {
    banner("Select a browser_live mode to use the microphone.", "warning");
    return;
  }
  if (shouldPreferBrowserSpeechRecognition()) {
    const recognition = ensureBrowserRecognition();
    if (recognition) {
      if (state.browserListening) {
        return;
      }
      try {
        recognition.start();
        return;
      } catch (error) {
        if (!state.browserAudioSupported) {
          banner(`Microphone start failed: ${error.message}`, "warning");
          return;
        }
        banner("Browser speech recognition failed to start. Falling back to recorded audio submission.", "warning");
      }
    }
  }
  if (state.browserAudioSupported) {
    if (state.browserListening) {
      return;
    }
    try {
      const stream = await ensureBrowserAudioStream();
      const mimeType = browserAudioMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      state.browserAudioChunks = [];
      state.browserAudioRecorder = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          state.browserAudioChunks.push(event.data);
        }
      };
      recorder.onstart = async () => {
        state.browserListening = true;
        state.browserManualStop = false;
        updateLiveControlAvailability();
        document.getElementById("voice-transcript-preview").textContent =
          "Listening now. Click Stop Mic + Send when you finish speaking.";
        banner(
          `Browser microphone listening${state.selectedBrowserMicrophoneId ? ` on ${selectedBrowserMicrophoneLabel()}` : ""}. Click Stop Mic + Send when you finish speaking.`,
          "neutral",
        );
        await postVoiceState("listening", {
          message: "browser_microphone_active",
          source: "browser_audio_capture",
          inputBackend: "browser_microphone",
          transcriptionBackend: "browser_audio_capture",
        }).catch(() => {});
        refreshSnapshot().catch(() => {});
      };
      recorder.onerror = async (event) => {
        state.browserListening = false;
        state.browserSubmitting = false;
        state.browserAudioRecorder = null;
        updateLiveControlAvailability();
        const errorCode = event.error?.name || "browser_audio_capture_failed";
        banner(`Microphone capture failed: ${errorCode}. Typed input remains available.`, "warning");
        await postVoiceState("failed", {
          message: errorCode,
          source: "browser_audio_capture",
          inputBackend: "browser_microphone",
          transcriptionBackend: "browser_audio_capture",
          metadata: { error_code: errorCode },
        }).catch(() => {});
      };
      recorder.onstop = async () => {
        state.browserListening = false;
        state.browserAudioRecorder = null;
        updateLiveControlAvailability();
        const blob = new Blob(state.browserAudioChunks, { type: recorder.mimeType || mimeType || "audio/webm" });
        state.browserAudioChunks = [];
        if (blob.size === 0) {
          await postVoiceState(state.browserManualStop ? "interrupted" : "idle", {
            message: state.browserManualStop ? "browser_audio_cancelled" : "browser_audio_empty",
            source: "browser_audio_capture",
            inputBackend: "browser_microphone",
            transcriptionBackend: "browser_audio_capture",
          }).catch(() => {});
          return;
        }
        state.browserSubmitting = true;
        document.getElementById("voice-transcript-preview").textContent =
          "Transcribing recorded speech and sending it to the AI...";
        try {
          await submitBrowserAudioCapture(blob, recorder.mimeType || mimeType || blob.type || "audio/webm");
        } finally {
          state.browserSubmitting = false;
          state.browserManualStop = false;
        }
      };

      recorder.start();
      return;
    } catch (error) {
      banner(`Browser microphone start failed: ${error.message}`, "warning");
      return;
    }
  }

  const recognition = ensureBrowserRecognition();
  if (!recognition) {
    banner("Browser speech recognition is not available here. Use typed input instead.", "warning");
    await postVoiceState("failed", {
      message: "browser_speech_recognition_unavailable",
      source: "browser_speech_recognition",
      metadata: { error_code: "browser_speech_recognition_unavailable" },
    }).catch(() => {});
    refreshSnapshot().catch(() => {});
    return;
  }
  if (state.browserListening) {
    return;
  }
  try {
    recognition.start();
  } catch (error) {
    banner(`Microphone start failed: ${error.message}`, "warning");
  }
}

function stopBrowserListening() {
  if (state.browserAudioRecorder && state.browserListening) {
    state.browserManualStop = true;
    document.getElementById("voice-transcript-preview").textContent =
      "Submitting recorded speech to the AI...";
    state.browserAudioRecorder.stop();
    return;
  }
  if (state.browserRecognition && state.browserListening) {
    state.browserManualStop = true;
    state.browserRecognition.stop();
  }
}

function disableCameraCue({ quiet = false } = {}) {
  const video = document.getElementById("camera-preview");
  stopMediaStream(state.cameraStream);
  state.cameraStream = null;
  if (video) {
    video.pause?.();
    video.srcObject = null;
    video.classList.add("hidden");
  }
  updateLiveControlAvailability();
  if (!quiet) {
    banner("Camera disabled. You can still use typed input, uploaded images, or manual presence cues.", "neutral");
  }
}

async function enableCameraCue() {
  if (!state.cameraSupported) {
    banner("Camera cue is unavailable in this browser.", "warning");
    return;
  }
  if (state.cameraStream) {
    updateLiveControlAvailability();
    return;
  }
  try {
    stopMediaStream(state.cameraStream);
    state.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: state.selectedBrowserCameraId ? { deviceId: { exact: state.selectedBrowserCameraId } } : { facingMode: "user" },
      audio: false,
    });
    const video = document.getElementById("camera-preview");
    video.srcObject = state.cameraStream;
    video.classList.remove("hidden");
    banner(
      `Camera cue enabled${state.selectedBrowserCameraId ? ` on ${selectedBrowserCameraLabel()}` : ""}. This does not do autonomous detection; it only supports an operator-confirmed presence cue.`,
      "neutral",
    );
  } catch (error) {
    banner(`Camera enable failed: ${error.message}`, "warning");
  } finally {
    updateLiveControlAvailability();
  }
}

async function handleBrowserMicrophoneChange() {
  state.selectedBrowserMicrophoneId = document.getElementById("browser-microphone-input").value;
  persistBrowserDeviceSelection("microphone", state.selectedBrowserMicrophoneId);
  if (state.browserAudioStream) {
    await ensureBrowserAudioStream({ forceRestart: true });
  }
  await refreshBrowserDevices();
}

async function handleBrowserCameraChange() {
  state.selectedBrowserCameraId = document.getElementById("browser-camera-input").value;
  persistBrowserDeviceSelection("camera", state.selectedBrowserCameraId);
  if (state.cameraStream) {
    disableCameraCue({ quiet: true });
    await enableCameraCue();
  } else {
    await refreshBrowserDevices();
  }
}

async function handleBrowserSpeakerChange() {
  state.selectedBrowserSpeakerId = document.getElementById("browser-speaker-input").value;
  persistBrowserDeviceSelection("speaker", state.selectedBrowserSpeakerId);
  if (state.browserSinkSelectionSupported) {
    const outputPreview = document.getElementById("browser-output-preview");
    try {
      await outputPreview.setSinkId(state.selectedBrowserSpeakerId);
    } catch (_) {
      banner("Browser speaker selection is unsupported for this output path. System default output remains active.", "warning");
    }
  }
  await refreshBrowserDevices();
}

async function captureCameraFrame() {
  if (!state.cameraStream) {
    await enableCameraCue();
  }
  const video = document.getElementById("camera-preview");
  const sourceWidth = video.videoWidth || 640;
  const sourceHeight = video.videoHeight || 480;
  const maxDimension = 960;
  const scale = Math.min(1, maxDimension / Math.max(sourceWidth, sourceHeight));
  const width = Math.max(1, Math.round(sourceWidth * scale));
  const height = Math.max(1, Math.round(sourceHeight * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("camera_canvas_unavailable");
  }
  context.drawImage(video, 0, 0, width, height);
  return {
    dataUrl: canvas.toDataURL("image/jpeg", 0.72),
    mimeType: "image/jpeg",
    width,
    height,
    capturedAt: new Date().toISOString(),
  };
}

async function submitCameraSnapshot() {
  const frame = await captureCameraFrame();
  return submitPerceptionSnapshot(
    {
      session_id: currentSessionId(),
      provider_mode: currentPerceptionMode(),
      source: "browser_camera_snapshot",
      image_data_url: frame.dataUrl,
      source_frame: {
        source_kind: "browser_camera_snapshot",
        source_label: "operator_console_camera",
        frame_id: `camera-${Date.now()}`,
        mime_type: frame.mimeType,
        width_px: frame.width,
        height_px: frame.height,
        captured_at: frame.capturedAt,
      },
      publish_events: true,
    },
    { bannerText: "Camera snapshot submitted to perception." },
  );
}

async function readImageFile(file) {
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("image_read_failed"));
    reader.readAsDataURL(file);
  });
  const dimensions = await new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.width, height: image.height });
    image.onerror = () => reject(new Error("image_dimension_read_failed"));
    image.src = dataUrl;
  });
  return {
    dataUrl,
    mimeType: file.type || "image/*",
    fileName: file.name,
    width: dimensions.width,
    height: dimensions.height,
  };
}

async function handlePerceptionImageSelected(event) {
  const file = event.target.files?.[0];
  if (!file) {
    state.uploadedImage = null;
    updateLiveControlAvailability();
    return;
  }
  state.uploadedImage = await readImageFile(file);
  updateLiveControlAvailability();
}

async function submitSelectedImage() {
  if (!state.uploadedImage) {
    banner("Choose an image first.", "warning");
    return null;
  }
  return submitPerceptionSnapshot(
    {
      session_id: currentSessionId(),
      provider_mode: currentPerceptionMode(),
      source: "browser_local_image",
      image_data_url: state.uploadedImage.dataUrl,
      source_frame: uploadedImageSourceFrame(`upload-${Date.now()}`),
      publish_events: true,
    },
    { bannerText: "Selected image submitted to perception." },
  );
}

async function sendCameraPresenceCue() {
  if (!state.cameraStream) {
    await enableCameraCue();
  }
  await injectEvent("person_detected", {
    source: "browser_camera_presence",
    payload: {
      confidence: 0.62,
      operator_confirmed: true,
      camera_active: Boolean(state.cameraStream),
    },
  });
}

function handleGlobalKeyDown(event) {
  const target = event.target;
  const isEditable =
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLButtonElement ||
    target?.isContentEditable;
  if (isEditable || event.repeat) {
    return;
  }
  if (event.code === "Space" && isBrowserLiveMode()) {
    event.preventDefault();
    state.browserShortcutHeld = true;
    startBrowserListening().catch(handleError);
  }
}

function handleGlobalKeyUp(event) {
  if (event.code === "Space" && state.browserShortcutHeld) {
    event.preventDefault();
    state.browserShortcutHeld = false;
    stopBrowserListening();
  }
}

function bindEvents() {
  document.getElementById("create-session-btn").addEventListener("click", () => createSession().catch(handleError));
  document.getElementById("reset-runtime-btn").addEventListener("click", () => resetRuntime().catch(handleError));
  document.getElementById("run-local-companion-story-btn").addEventListener("click", () => runLocalCompanionStory().catch(handleError));
  document.getElementById("run-desktop-story-btn").addEventListener("click", () => runDesktopStory().catch(handleError));
  document.getElementById("export-session-episode-btn").addEventListener("click", () => exportCurrentSessionEpisode().catch(handleError));
  document.getElementById("export-latest-run-episode-btn").addEventListener("click", () => exportLatestRunEpisode().catch(handleError));
  document.getElementById("submit-episode-teacher-btn").addEventListener("click", () => submitEpisodeTeacherReview().catch(handleError));
  document.getElementById("submit-trace-teacher-btn").addEventListener("click", () => submitTraceTeacherReview().catch(handleError));
  document.getElementById("review-memory-btn").addEventListener("click", () => submitMemoryReview("review").catch(handleError));
  document.getElementById("correct-memory-btn").addEventListener("click", () => submitMemoryReview("correct").catch(handleError));
  document.getElementById("delete-memory-btn").addEventListener("click", () => submitMemoryReview("delete").catch(handleError));
  document.getElementById("run-benchmarks-btn").addEventListener("click", () => runBenchmarks().catch(handleError));
  document.getElementById("send-text-btn").addEventListener("click", () => sendTextTurn().catch(handleError));
  document.getElementById("cancel-voice-btn").addEventListener("click", () => cancelVoice().catch(handleError));
  document.getElementById("force-safe-idle-btn").addEventListener("click", () => forceSafeIdle().catch(handleError));
  document.getElementById("body-connect-btn").addEventListener("click", () => connectBody().catch(handleError));
  document.getElementById("body-disconnect-btn").addEventListener("click", () => disconnectBody().catch(handleError));
  document.getElementById("body-scan-btn").addEventListener("click", () => scanBody().catch(handleError));
  document.getElementById("body-ping-btn").addEventListener("click", () => pingBody().catch(handleError));
  document.getElementById("body-read-health-btn").addEventListener("click", () => readBodyHealth().catch(handleError));
  document.getElementById("body-arm-btn").addEventListener("click", () => armBodyMotion().catch(handleError));
  document.getElementById("body-disarm-btn").addEventListener("click", () => disarmBodyMotion().catch(handleError));
  document.getElementById("body-write-neutral-btn").addEventListener("click", () => writeBodyNeutral().catch(handleError));
  document.getElementById("body-semantic-smoke-btn").addEventListener("click", () => runBodySemanticSmoke().catch(handleError));
  document.getElementById("body-teacher-review-btn").addEventListener("click", () => submitBodyTeacherReview().catch(handleError));
  document.getElementById("body-safe-idle-btn").addEventListener("click", () => forceSafeIdle().catch(handleError));
  document.getElementById("servo-lab-joint-select").addEventListener("change", () => renderServoLabSelection(true));
  document.getElementById("servo-lab-read-current-btn").addEventListener("click", () => readServoLabCurrent().catch(handleError));
  document.getElementById("servo-lab-move-btn").addEventListener("click", () => moveServoLabJoint().catch(handleError));
  document.getElementById("servo-lab-step-minus-btn").addEventListener("click", () => stepServoLabJoint(-1).catch(handleError));
  document.getElementById("servo-lab-step-plus-btn").addEventListener("click", () => stepServoLabJoint(1).catch(handleError));
  document.getElementById("servo-lab-go-min-btn").addEventListener("click", () => moveServoLabToBound("min").catch(handleError));
  document.getElementById("servo-lab-go-max-btn").addEventListener("click", () => moveServoLabToBound("max").catch(handleError));
  document.getElementById("servo-lab-go-neutral-btn").addEventListener("click", () => moveServoLabToBound("neutral").catch(handleError));
  document.getElementById("servo-lab-sweep-btn").addEventListener("click", () => sweepServoLabJoint().catch(handleError));
  document.getElementById("servo-lab-save-neutral-btn").addEventListener("click", () => saveServoLabCurrentAsNeutral().catch(handleError));
  document.getElementById("servo-lab-save-range-btn").addEventListener("click", () => saveServoLabRangeToCalibration().catch(handleError));
  document.getElementById("workflow-start-btn").addEventListener("click", () => startWorkflow().catch(handleError));
  document.getElementById("bundle-teacher-review-btn").addEventListener("click", () => submitActionBundleTeacherReview().catch(handleError));
  document.getElementById("browser-task-open-btn").addEventListener("click", () => runBrowserTask("open_url").catch(handleError));
  document.getElementById("browser-task-snapshot-btn").addEventListener("click", () => runBrowserTask("capture_snapshot").catch(handleError));
  document.getElementById("browser-task-find-btn").addEventListener("click", () => runBrowserTask("find_click_targets").catch(handleError));
  document.getElementById("browser-task-run-btn").addEventListener("click", () => runBrowserTask().catch(handleError));
  document.getElementById("run-shift-tick-btn").addEventListener("click", () => runShiftTick().catch(handleError));
  document.getElementById("incident-ack-btn").addEventListener("click", () => acknowledgeIncident().catch(handleError));
  document.getElementById("incident-assign-btn").addEventListener("click", () => assignIncident().catch(handleError));
  document.getElementById("incident-note-btn").addEventListener("click", () => addIncidentNote().catch(handleError));
  document.getElementById("incident-resolve-btn").addEventListener("click", () => resolveIncident().catch(handleError));
  document.getElementById("start-listening-btn").addEventListener("click", () => startBrowserListening().catch(handleError));
  document.getElementById("stop-listening-btn").addEventListener("click", () => stopBrowserListening());
  document.getElementById("enable-camera-btn").addEventListener("click", () => enableCameraCue().catch(handleError));
  document.getElementById("disable-camera-btn").addEventListener("click", () => disableCameraCue());
  document.getElementById("capture-snapshot-btn").addEventListener("click", () => submitCameraSnapshot().catch(handleError));
  document.getElementById("send-camera-cue-btn").addEventListener("click", () => sendCameraPresenceCue().catch(handleError));
  document.getElementById("submit-image-btn").addEventListener("click", () => submitSelectedImage().catch(handleError));
  document.getElementById("submit-annotations-btn").addEventListener("click", () => submitManualAnnotations().catch(handleError));
  document.getElementById("replay-fixture-btn").addEventListener("click", () => replayPerceptionFixture().catch(handleError));
  document.getElementById("perception-image-input").addEventListener("change", (event) => handlePerceptionImageSelected(event).catch(handleError));
  document.getElementById("voice-mode-input").addEventListener("change", handleVoiceModeChange);
  document.getElementById("browser-microphone-input").addEventListener("change", () => handleBrowserMicrophoneChange().catch(handleError));
  document.getElementById("browser-speaker-input").addEventListener("change", () => handleBrowserSpeakerChange().catch(handleError));
  document.getElementById("browser-camera-input").addEventListener("change", () => handleBrowserCameraChange().catch(handleError));
  document.getElementById("perception-mode-input").addEventListener("change", handlePerceptionModeChange);
  document.querySelectorAll("[data-inject]").forEach((button) => {
    button.addEventListener("click", () => injectEvent(button.dataset.inject).catch(handleError));
  });
  window.addEventListener("keydown", handleGlobalKeyDown);
  window.addEventListener("keyup", handleGlobalKeyUp);
  window.addEventListener("beforeunload", () => {
    stopMediaStream(state.browserAudioStream);
    if (state.cameraStream) {
      state.cameraStream.getTracks().forEach((track) => track.stop());
    }
    if (state.browserRecognition && state.browserListening) {
      state.browserRecognition.stop();
    }
  });
}

function handleError(error) {
  banner(`Action failed: ${error.message}`, "danger");
}

async function init() {
  state.browserSpeechSupported = Boolean(speechRecognitionCtor());
  state.selectedBrowserMicrophoneId = loadBrowserDeviceSelection("microphone");
  state.selectedBrowserSpeakerId = loadBrowserDeviceSelection("speaker");
  state.selectedBrowserCameraId = loadBrowserDeviceSelection("camera");
  bindEvents();
  ensureBrowserRecognition();
  if (state.browserDevicesSupported) {
    await refreshBrowserDevices();
    navigator.mediaDevices.addEventListener?.("devicechange", () => {
      refreshBrowserDevices().catch(handleError);
    });
  }
  updateLiveControlAvailability();
  await Promise.all([
    loadScenarios(),
    loadScenes(),
    loadPerceptionFixtures(),
    refreshSnapshot(),
    refreshServoLabCatalog(),
    loadEpisodes(),
    loadBenchmarks(),
  ]);
  notifyActionCenterIfNeeded("Action Center");
  window.setInterval(() => {
    if (shouldPauseBackgroundPolling() || state.periodicRefreshInFlight) {
      return;
    }
    state.periodicRefreshInFlight = true;
    Promise.all([
      refreshSnapshot(),
      loadEpisodes(),
      loadBenchmarks(),
    ]).catch(handleError).finally(() => {
      state.periodicRefreshInFlight = false;
    });
  }, pollIntervalMs);
}

window.addEventListener("DOMContentLoaded", () => {
  init().catch(handleError);
});
