(function () {
  function requestJson(url, options = {}) {
    return fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    }).then(async (response) => {
      if (response.status === 401) {
        if (!window.location.pathname.startsWith("/login")) {
          window.location.assign("/login");
        }
        throw new Error("operator_auth_required");
      }
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `${response.status} ${response.statusText}`);
      }
      return response.json();
    });
  }

  function formatFraction(value) {
    if (typeof value !== "number") {
      return "-";
    }
    return `${Math.round(value * 100)}%`;
  }

  function formatJson(value) {
    return JSON.stringify(value, null, 2);
  }

  function renderSignals(container, items) {
    if (!container) {
      return;
    }
    container.innerHTML = "";
    for (const item of items || []) {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.textContent = item;
      container.appendChild(chip);
    }
    if (!container.children.length) {
      const chip = document.createElement("span");
      chip.className = "tag-chip";
      chip.textContent = "no_signals_reported";
      container.appendChild(chip);
    }
  }

  function buildStatusLine(data, shell) {
    return [
      shell.semantic_summary || "semantic_projection_unavailable",
      `presence=${data.presence_runtime?.state || "-"}`,
      `voice=${data.voice_loop?.state || "-"}`,
      `initiative=${data.initiative_engine?.current_stage || "-"}/${data.initiative_engine?.last_decision || "-"}`,
    ].join(" | ");
  }

  function applyPose(windowEl, shell) {
    if (!windowEl) {
      return;
    }
    const pose = shell.pose || {};
    windowEl.dataset.surfaceState = shell.surface_state || "idle";
    windowEl.dataset.motionHint = shell.motion_hint || "settled";
    windowEl.style.setProperty("--head-roll-deg", `${((pose.head_roll || 0) * 18).toFixed(1)}deg`);
    windowEl.style.setProperty("--head-raise-px", `${((pose.head_pitch || 0) * -16).toFixed(1)}px`);
    windowEl.style.setProperty("--pupil-offset-x", `${((pose.eye_yaw || 0) * 10).toFixed(1)}px`);
    windowEl.style.setProperty("--pupil-offset-y", `${((pose.eye_pitch || 0) * 8).toFixed(1)}px`);
    windowEl.style.setProperty(
      "--eye-open-left",
      `${Math.max(0.05, Math.min(1, pose.upper_lid_left_open ?? pose.upper_lids_open ?? 0.9))}`,
    );
    windowEl.style.setProperty(
      "--eye-open-right",
      `${Math.max(0.05, Math.min(1, pose.upper_lid_right_open ?? pose.upper_lids_open ?? 0.9))}`,
    );
    windowEl.style.setProperty("--brow-offset-left", `${-((pose.brow_raise_left || 0) * 16).toFixed(1)}px`);
    windowEl.style.setProperty("--brow-offset-right", `${-((pose.brow_raise_right || 0) * 16).toFixed(1)}px`);
  }

  window.BlinkPresenceShell = {
    applyPose,
    buildStatusLine,
    formatFraction,
    formatJson,
    renderSignals,
    requestJson,
  };
})();
