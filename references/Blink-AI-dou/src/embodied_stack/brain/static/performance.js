const performanceState = {
  refreshInFlight: false,
  timerId: null,
  currentRunId: "",
};

const presenceShell = window.BlinkPresenceShell;

function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function scheduleRefresh(delayMs = 1200) {
  if (performanceState.timerId !== null) {
    window.clearTimeout(performanceState.timerId);
  }
  performanceState.timerId = window.setTimeout(() => {
    refreshPerformance().catch(handleError);
  }, delayMs);
}

function formatClock(value) {
  const totalSeconds = Math.max(0, Number.isFinite(value) ? Math.floor(value) : 0);
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

async function requestMaybeJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
    throw new Error("operator_auth_required");
  }
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function flattenCueResults(run) {
  if (!run) {
    return [];
  }
  return (run.segment_results || []).flatMap((segment) =>
    (segment.cue_results || []).map((cue) => ({ segment, cue })),
  );
}

function currentSegment(run, definition) {
  if (!run && !definition) {
    return null;
  }
  const segment = (run?.segment_results || []).find((item) => item.segment_id === run?.current_segment_id);
  if (segment) {
    return segment;
  }
  return run?.segment_results?.[0] || definition?.segments?.[0] || null;
}

function currentCueResult(run, segment) {
  if (!run) {
    return null;
  }
  const cueId = run.current_cue_id;
  if (cueId && segment?.cue_results?.length) {
    const match = segment.cue_results.find((item) => item.cue_id === cueId);
    if (match) {
      return match;
    }
  }
  const flattened = flattenCueResults(run);
  return flattened.length ? flattened[flattened.length - 1]?.cue || null : null;
}

function latestCommandAudit(cueResult) {
  if (!cueResult) {
    return null;
  }
  const motionResults = cueResult?.payload?.motion_results || [];
  const latestMotionAudit = motionResults.length
    ? motionResults[motionResults.length - 1]?.raw_result?.latest_command_audit ||
      motionResults[motionResults.length - 1]?.raw_result?.body_state?.latest_command_audit
    : null;
  return (
    latestMotionAudit ||
    cueResult?.payload?.raw_result?.latest_command_audit ||
    cueResult?.payload?.raw_result?.body_state?.latest_command_audit ||
    null
  );
}

function motionExecutionSummary(cueResult) {
  const audit = latestCommandAudit(cueResult);
  if (!audit) {
    return "frames=awaiting_body_motion";
  }
  const frameNames = (audit.executed_frame_names || []).slice(0, 5);
  const peaks = audit.peak_normalized_pose || {};
  const peakSummary = ["head_pitch", "head_yaw", "head_roll"]
    .filter((key) => peaks[key] !== undefined && peaks[key] !== null)
    .map((key) => `${key}=${Number(peaks[key]).toFixed(3)}`)
    .join(" | ");
  return [
    `frames=${audit.executed_frame_count ?? "-"}`,
    frameNames.length ? `frame_names=${frameNames.join(",")}` : null,
    audit.final_frame_name ? `final_frame=${audit.final_frame_name}` : null,
    audit.elapsed_wall_clock_ms != null ? `wall_clock_ms=${Math.round(Number(audit.elapsed_wall_clock_ms))}` : null,
    motionControlSummary(audit.motion_control),
    peakSummary || null,
  ]
    .filter(Boolean)
    .join(" | ");
}

function motionControlSummary(motionControl) {
  if (!motionControl) {
    return null;
  }
  const speed = motionControl.speed || {};
  const acceleration = motionControl.acceleration || {};
  return [
    `speed=${speed.effective_value ?? "-"}`,
    `speed_verified=${speed.verified ?? false}`,
    `accel=${acceleration.effective_value ?? "-"}`,
    `accel_verified=${acceleration.verified ?? false}`,
  ].join(" | ");
}

function isProofLikeCue(cue) {
  return Boolean(
    (cue.proof_checks && cue.proof_checks.length) ||
      cue.fallback_used ||
      cue.payload?.reply_text ||
      cue.payload?.incident_present ||
      cue.payload?.safe_idle_active ||
      cue.payload?.session_export,
  );
}

function summarizeProofChecks(cue) {
  const checks = cue.proof_checks || [];
  if (!checks.length) {
    return cue.note || cue.payload?.reply_text || "Awaiting proof output.";
  }
  const failed = checks.filter((item) => !item.passed);
  if (failed.length) {
    return failed
      .slice(0, 2)
      .map((item) => `${item.criterion}: expected ${item.expected || "-"} / observed ${item.observed || "-"}`)
      .join(" | ");
  }
  return checks
    .slice(0, 2)
    .map((item) => `${item.criterion}: ${item.observed || item.expected || "passed"}`)
    .join(" | ");
}

function renderProofCards(run) {
  const grid = document.getElementById("performance-proof-grid");
  grid.innerHTML = "";

  const segment = currentSegment(run, null);
  const proofItems = ((segment?.cue_results || []).filter(isProofLikeCue)).slice(-2);
  const cards = proofItems.length
    ? proofItems
    : run?.current_cue_id
      ? [{ cue_id: run.current_cue_id, label: run.current_cue_id, status: "running", proof_checks: [], payload: {} }]
      : [];

  if (!cards.length) {
    const empty = document.createElement("div");
    empty.className = "status-chip";
    empty.textContent = "Waiting for the first proof cue.";
    grid.appendChild(empty);
    return;
  }

  for (const cue of cards) {
    const card = document.createElement("article");
    card.className = "status-chip performance-proof-card";
    card.dataset.state = cue.status || "pending";

    const title = document.createElement("strong");
    title.textContent = cue.label || cue.cue_id || "proof";
    card.appendChild(title);

    const state = document.createElement("span");
    state.className = "subtle";
    state.textContent = [
      `state=${cue.status || "-"}`,
      cue.fallback_used ? "fallback_used=yes" : null,
      cue.degraded ? "degraded=yes" : null,
    ]
      .filter(Boolean)
      .join(" | ");
    card.appendChild(state);

    const detail = document.createElement("div");
    detail.className = "performance-proof-detail";
    detail.textContent = summarizeProofChecks(cue);
    card.appendChild(detail);

    grid.appendChild(card);
  }
}

function projectionSummary(run) {
  if (!run) {
    return "projection=awaiting_run";
  }
  const motionOutcome = run.last_motion_outcome || "-";
  const reasonCode = run.last_motion_margin_record?.reason_code || "-";
  const minMargin = run.last_motion_margin_record?.min_remaining_margin_percent;
  const coverage = coverageSummary(run.actuator_coverage);
  const worstActuator = run.worst_actuator_group || "-";
  if (run.preview_only) {
    return `projection=preview-only | outcome=${run.last_body_projection_outcome || "-"} | motion=${motionOutcome} | coverage=${coverage} | worst_actuator=${worstActuator} | min_margin=${minMargin ?? "-"} | reason=${reasonCode}`;
  }
  return `projection=live_or_bodyless | outcome=${run.last_body_projection_outcome || "-"} | motion=${motionOutcome} | coverage=${coverage} | worst_actuator=${worstActuator} | min_margin=${minMargin ?? "-"} | reason=${reasonCode}`;
}

function coverageSummary(coverage) {
  if (!coverage) {
    return "-";
  }
  const active = [
    "head_yaw",
    "head_pitch_pair",
    "eye_yaw",
    "eye_pitch",
    "upper_lids",
    "lower_lids",
    "brows",
  ].filter((key) => Boolean(coverage[key]));
  return active.length ? active.join(",") : "-";
}

function timingBreakdownSummary(run) {
  const breakdown = run?.timing_breakdown_ms || {};
  const keys = ["narration", "proof", "motion_track", "idle", "body_motion", "proof_backend_latency"];
  return keys
    .filter((key) => key in breakdown)
    .map((key) => `${key}=${Math.round(Number(breakdown[key] || 0))}ms`)
    .join(" | ");
}

function renderPerformance(definition, run, presence, catalog) {
  const shell = presence?.character_presence_shell || {};
  const segment = currentSegment(run, definition);
  const cueResult = currentCueResult(run, segment);
  const showName = definition?.show_name || run?.show_name || "investor_expressive_motion_v8";
  performanceState.currentRunId = run?.run_id || "";

  document.getElementById("performance-title").textContent = definition?.title || "Blink-AI Investor Performance";
  document.getElementById("performance-show-pill").textContent = showName;
  document.getElementById("performance-run-pill").textContent = run?.status || "idle";
  document.getElementById("performance-segment-title").textContent = segment?.title || "Waiting for show state";
  document.getElementById("performance-segment-clock").textContent = formatClock(segment?.target_start_seconds || 0);
  document.getElementById("performance-investor-claim").textContent =
    segment?.investor_claim ||
    "The projector page follows the active or latest deterministic investor performance run.";
  const promptNode = document.getElementById("performance-prompt");
  if (run?.current_prompt) {
    promptNode.textContent = `Off-stage prompt: ${run.current_prompt}`;
    promptNode.classList.remove("hidden");
  } else {
    promptNode.textContent = "Off-stage prompt will appear here when the current chapter needs one.";
    promptNode.classList.add("hidden");
  }
  document.getElementById("performance-caption").textContent =
    run?.current_narration ||
    run?.current_caption ||
    "Start the show from the terminal with uv run local-companion performance-show investor_expressive_motion_v8.";
  document.getElementById("performance-status-line").textContent = presence
    ? presenceShell.buildStatusLine(presence, shell)
    : `show=${showName} | active_run=${catalog?.active_run_id || "-"} | latest_run=${catalog?.latest_run_id || "-"}`;
  document.getElementById("performance-config-summary").textContent = [
    `proof_backend=${run?.proof_backend_mode || definition?.defaults?.proof_backend_mode || "-"}`,
    `language=${run?.language || definition?.defaults?.language || "-"}`,
    `voice_preset=${run?.narration_voice_preset || definition?.defaults?.narration_voice_preset || "-"}`,
    `voice_name=${run?.narration_voice_name || definition?.defaults?.narration_voice_name || "-"}`,
    `voice_rate=${run?.narration_voice_rate || definition?.defaults?.narration_voice_rate || "-"}`,
    `tuning=${run?.selected_show_tuning_path || "-"}`,
  ].join(" | ");

  document.getElementById("performance-run-summary").textContent = [
    `session=${run?.session_id || definition?.session_id || queryParam("session_id") || "investor-expressive-motion-v8"}`,
    `current_segment=${run?.current_segment_id || "-"}`,
    `current_cue=${run?.current_cue_id || "-"}`,
    `preflight=${run?.preflight_passed === undefined || run?.preflight_passed === null ? "-" : run.preflight_passed}`,
    `power=${run?.power_health_classification || "-"}`,
    `degraded_cues=${(run?.degraded_cues || []).length}`,
    `proof_checks=${run?.proof_check_count ?? 0}`,
    `failed_checks=${run?.failed_proof_check_count ?? 0}`,
    `motion=${run?.last_motion_outcome || "-"}`,
    `coverage=${coverageSummary(run?.actuator_coverage)}`,
    `eye_pitch_live=${run?.eye_pitch_exercised_live ?? false}`,
  ].join(" | ");
  document.getElementById("performance-timing-summary").textContent = [
    `target=${formatClock(run?.target_total_duration_seconds || 0)}`,
    `elapsed=${formatClock(run?.elapsed_seconds || 0)}`,
    `drift_seconds=${run?.timing_drift_seconds ?? "-"}`,
    `completed_segments=${run?.completed_segment_count ?? 0}/${run?.segment_results?.length ?? 0}`,
    timingBreakdownSummary(run),
  ]
    .filter(Boolean)
    .join(" | ");
  document.getElementById("performance-projection-summary").textContent = projectionSummary(run);
  document.getElementById("performance-motion-summary").textContent = motionExecutionSummary(cueResult);

  document.getElementById("performance-artifact-summary").textContent = [
    run?.artifact_dir ? `artifact_dir=${run.artifact_dir}` : null,
    run?.episode_id ? `episode_id=${run.episode_id}` : null,
    run?.preflight_failure_reason ? `preflight_reason=${run.preflight_failure_reason}` : null,
    run?.artifact_files?.session_export ? `session_export=${run.artifact_files.session_export}` : null,
    run?.artifact_files?.rehearsal_log ? `rehearsal_log=${run.artifact_files.rehearsal_log}` : null,
    run?.live_motion_arm_author ? `arm_author=${run.live_motion_arm_author}` : null,
    run?.live_motion_arm_port ? `arm_port=${run.live_motion_arm_port}` : null,
    run?.degraded_due_to_margin_only_cues?.length
      ? `margin_only_degraded=${run.degraded_due_to_margin_only_cues.join(",")}`
      : null,
    run?.degraded_cues?.length ? `degraded=${run.degraded_cues.join(",")}` : null,
  ]
    .filter(Boolean)
    .join(" | ") || "Artifacts will appear here when a run completes or degrades.";

  const degradedBadge = document.getElementById("performance-degraded-badge");
  degradedBadge.classList.toggle("hidden", !run?.degraded);
  degradedBadge.textContent = run?.degraded ? "Degraded" : "";
  const stopButton = document.getElementById("performance-stop-btn");
  stopButton.classList.toggle("hidden", !(run?.status === "running" && run?.run_id));

  presenceShell.applyPose(document.getElementById("performance-shell-window"), shell);
  renderProofCards(run);
}

async function refreshPerformance() {
  if (performanceState.refreshInFlight) {
    return;
  }
  performanceState.refreshInFlight = true;
  try {
    const catalog = await presenceShell.requestJson("/api/operator/performance-shows");
    const requestedShowName = queryParam("show");
    const definition =
      catalog.items.find((item) => item.show_name === requestedShowName) ||
      catalog.items[0] ||
      null;
    const runId = queryParam("run_id") || catalog.active_run_id || catalog.latest_run_id || "";
    const run = runId
      ? await requestMaybeJson(`/api/operator/performance-shows/runs/${encodeURIComponent(runId)}`)
      : null;
    const sessionId = run?.session_id || queryParam("session_id") || definition?.session_id || "";
    const presence = sessionId
      ? await presenceShell.requestJson(`/api/operator/presence?session_id=${encodeURIComponent(sessionId)}`)
      : null;
    renderPerformance(definition, run, presence, catalog);
  } finally {
    performanceState.refreshInFlight = false;
    scheduleRefresh(document.hidden ? 2600 : 1200);
  }
}

function handleError(error) {
  document.getElementById("performance-status-line").textContent = `performance_refresh_error=${error.message}`;
  scheduleRefresh(2600);
}

async function cancelPerformanceRun() {
  if (!performanceState.currentRunId) {
    return;
  }
  await requestMaybeJson(`/api/operator/performance-shows/runs/${encodeURIComponent(performanceState.currentRunId)}/cancel`, {
    method: "POST",
  });
  scheduleRefresh(150);
}

function wireEvents() {
  document.getElementById("performance-refresh-btn").addEventListener("click", () => {
    refreshPerformance().catch(handleError);
  });
  document.getElementById("performance-stop-btn").addEventListener("click", () => {
    cancelPerformanceRun().catch(handleError);
  });
  document.addEventListener("visibilitychange", () => {
    scheduleRefresh(document.hidden ? 2600 : 1200);
  });
}

wireEvents();
refreshPerformance().catch(handleError);
