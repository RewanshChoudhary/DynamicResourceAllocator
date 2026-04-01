const state = {
  datasets: [],
  presets: [],
  mutations: [],
  mutationOptions: null,
  loadedPayloadText: "",
};

const elements = {
  datasetSelect: document.getElementById("dataset-select"),
  datasetLoad: document.getElementById("dataset-load"),
  idempotencyKey: document.getElementById("idempotency-key"),
  refreshIdempotency: document.getElementById("refresh-idempotency"),
  allocationPayload: document.getElementById("allocation-payload"),
  runAllocation: document.getElementById("run-allocation"),
  allocateStatus: document.getElementById("allocate-status"),
  allocationResults: document.getElementById("allocation-results"),
  auditOrderId: document.getElementById("audit-order-id"),
  findManifest: document.getElementById("find-manifest"),
  auditManifestStatus: document.getElementById("audit-manifest-status"),
  manifestCard: document.getElementById("manifest-card"),
  viewTrace: document.getElementById("view-trace"),
  traceContainer: document.getElementById("trace-container"),
  verifyManifestId: document.getElementById("verify-manifest-id"),
  verifyIntegrity: document.getElementById("verify-integrity"),
  verifyStatus: document.getElementById("verify-status"),
  verifyResult: document.getElementById("verify-result"),
  rejectionOrderId: document.getElementById("rejection-order-id"),
  viewRejections: document.getElementById("view-rejections"),
  rejectionStatus: document.getElementById("rejection-status"),
  rejectionTable: document.getElementById("rejection-table"),
  replayManifestId: document.getElementById("replay-manifest-id"),
  runReplay: document.getElementById("run-replay"),
  replayStatus: document.getElementById("replay-status"),
  replayResults: document.getElementById("replay-results"),
  simulateManifestId: document.getElementById("simulate-manifest-id"),
  presetSelect: document.getElementById("preset-select"),
  applyPreset: document.getElementById("apply-preset"),
  presetHelper: document.getElementById("preset-helper"),
  mutationType: document.getElementById("mutation-type"),
  mutationFields: document.getElementById("mutation-fields"),
  addMutation: document.getElementById("add-mutation"),
  clearMutations: document.getElementById("clear-mutations"),
  mutationList: document.getElementById("mutation-list"),
  runSimulation: document.getElementById("run-simulation"),
  simulateStatus: document.getElementById("simulate-status"),
  simulationResults: document.getElementById("simulation-results"),
  diagnosticsSidebar: document.getElementById("diagnostics-sidebar"),
  diagnosticsToggle: document.getElementById("diagnostics-toggle"),
  diagnosticsRefresh: document.getElementById("diagnostics-refresh"),
  diagnosticsStatus: document.getElementById("diagnostics-status"),
  diagnosticsHealth: document.getElementById("diagnostics-health"),
  diagnosticsSummary: document.getElementById("diagnostics-summary"),
  diagnosticsReservations: document.getElementById("diagnostics-reservations"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}

function formatTraceNumber(value, decimals = 3) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value ?? "—");
  }
  return Number(numeric.toFixed(decimals)).toString();
}

function scoreBarWidth(rawScore) {
  const numeric = Number(rawScore);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  const normalized = numeric <= 1 ? numeric : numeric / 10;
  return Math.max(0, Math.min(100, normalized * 100));
}

function normalizeVehicleTypes(vehicleTypes) {
  if (Array.isArray(vehicleTypes)) {
    return vehicleTypes.filter(Boolean);
  }
  return String(vehicleTypes || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function generateIdempotencyKey() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `manual-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function showLoading(container, message) {
  container.innerHTML = `<div class="loading-card"><span class="spinner"></span><span>${escapeHtml(message)}</span></div>`;
}

function showError(container, error) {
  const status = error && error.status ? `HTTP ${error.status}` : "Request failed";
  const message = error && error.message ? error.message : "Unknown error";
  container.innerHTML = `<div class="error-card"><strong>${escapeHtml(status)}</strong><div class="small">${escapeHtml(message)}</div></div>`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch (error) {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === "object" && payload.detail ? payload.detail : payload;
    throw {
      status: response.status,
      message: typeof detail === "string" ? detail : prettyJson(detail),
    };
  }

  return payload;
}

function setTab(tabName) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tabName}`);
  });
}

function summariseMutation(mutation) {
  if (mutation.mutation_type === "rule_parameter") {
    return `${mutation.rule_name}.${mutation.parameter_name} → ${mutation.new_value}`;
  }
  if (mutation.mutation_type === "rule_weight") {
    return `${mutation.rule_name} weight → ${mutation.new_weight}`;
  }
  if (mutation.mutation_type === "rule_toggle") {
    return `${mutation.rule_name} enabled → ${mutation.enabled}`;
  }
  const action = mutation.action || "remove";
  return `partner_pool ${action} ${mutation.partner_id}`;
}

function renderMutationList() {
  if (!state.mutations.length) {
    elements.mutationList.innerHTML = `<div class="hint">No mutations added yet.</div>`;
    return;
  }

  elements.mutationList.innerHTML = state.mutations
    .map(
      (mutation, index) => `
        <span class="mutation-chip mono">
          ${escapeHtml(summariseMutation(mutation))}
          <button data-remove-mutation="${index}" aria-label="Remove mutation">×</button>
        </span>
      `
    )
    .join("");

  elements.mutationList.querySelectorAll("[data-remove-mutation]").forEach((button) => {
    button.addEventListener("click", () => {
      const index = Number(button.dataset.removeMutation);
      state.mutations.splice(index, 1);
      renderMutationList();
    });
  });
}

function mutationToApi(mutation) {
  if (mutation.mutation_type === "rule_parameter") {
    return {
      mutation_type: "rule_parameter",
      rule_name: mutation.rule_name,
      parameter: mutation.parameter_name,
      new_value: Number(mutation.new_value),
    };
  }

  if (mutation.mutation_type === "rule_weight") {
    return {
      mutation_type: "rule_weight",
      rule_name: mutation.rule_name,
      new_weight: Number(mutation.new_weight),
    };
  }

  if (mutation.mutation_type === "rule_toggle") {
    return {
      mutation_type: "rule_toggle",
      rule_name: mutation.rule_name,
      enabled: Boolean(mutation.enabled),
    };
  }

  const payload = {
    mutation_type: "partner_pool",
    add: [],
    remove: [],
    modify: [],
  };

  if ((mutation.action || "remove") === "remove") {
    payload.remove = [mutation.partner_id];
    return payload;
  }

  const partnerPayload = {
    partner_id: mutation.partner_id,
    latitude: Number(mutation.latitude),
    longitude: Number(mutation.longitude),
    is_available: mutation.is_available !== false,
    rating: Number(mutation.rating),
    vehicle_types: normalizeVehicleTypes(mutation.vehicle_types),
    active: mutation.active !== false,
  };

  if (mutation.action === "modify") {
    payload.modify = [partnerPayload];
  } else {
    payload.add = [partnerPayload];
  }
  return payload;
}

function renderMutationFields() {
  const type = elements.mutationType.value;
  const mutationOptions = state.mutationOptions;
  if (!mutationOptions) {
    elements.mutationFields.innerHTML = `<div class="banner">Loading mutation choices from the current rule config...</div>`;
    return;
  }

  const previousRuleName = document.getElementById("field-rule-name")?.value || "";
  const previousParameterName = document.getElementById("field-parameter-name")?.value || "";
  const previousNewValue = document.getElementById("field-new-value")?.value || "";
  const previousNewWeight = document.getElementById("field-new-weight")?.value || "";
  const previousEnabled = document.getElementById("field-enabled")?.value || "";
  const previousAction = document.getElementById("field-action")?.value || "";
  const previousPartnerId = document.getElementById("field-partner-id")?.value || "";
  const previousLatitude = document.getElementById("field-latitude")?.value || "";
  const previousLongitude = document.getElementById("field-longitude")?.value || "";
  const previousRating = document.getElementById("field-rating")?.value || "";
  const previousAvailability = document.getElementById("field-is-available")?.value || "true";
  const previousActive = document.getElementById("field-active")?.value || "true";
  const previousVehicleTypes = Array.from(
    document.getElementById("field-vehicle-types")?.selectedOptions || []
  ).map((option) => option.value);
  let html = "";

  if (type === "rule_parameter") {
    const rules = mutationOptions.rule_parameter || [];
    const selectedRuleName =
      rules.find((rule) => rule.rule_name === previousRuleName)?.rule_name || rules[0]?.rule_name || "";
    const selectedRule = rules.find((rule) => rule.rule_name === selectedRuleName);
    const parameters = selectedRule?.parameters || [];
    const selectedParameterName =
      parameters.find((parameter) => parameter.name === previousParameterName)?.name
      || parameters[0]?.name
      || "";
    const selectedParameter = parameters.find((parameter) => parameter.name === selectedParameterName);

    html = `
      <div class="row">
        <div class="field">
          <label for="field-rule-name">Rule name</label>
          <select id="field-rule-name" class="mono">
            ${rules
              .map(
                (rule) => `
                  <option value="${escapeHtml(rule.rule_name)}" ${rule.rule_name === selectedRuleName ? "selected" : ""}>
                    ${escapeHtml(rule.rule_name)} (${escapeHtml(rule.rule_group)})
                  </option>
                `
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="field-parameter-name">Parameter name</label>
          <select id="field-parameter-name" class="mono">
            ${parameters
              .map(
                (parameter) => `
                  <option value="${escapeHtml(parameter.name)}" ${parameter.name === selectedParameterName ? "selected" : ""}>
                    ${escapeHtml(parameter.name)}
                  </option>
                `
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="field-new-value">New value</label>
          <input id="field-new-value" type="number" step="0.01" class="mono" value="${escapeHtml(previousNewValue)}" />
        </div>
      </div>
      <div class="hint">
        Choose from the live rule config. Current value for
        <span class="mono">${escapeHtml(selectedRuleName || "rule")}.${escapeHtml(selectedParameterName || "parameter")}</span>
        is <span class="mono">${escapeHtml(selectedParameter?.current_value ?? "N/A")}</span>.
      </div>
    `;
  } else if (type === "rule_weight") {
    const rules = mutationOptions.rule_weight || [];
    const selectedRuleName =
      rules.find((rule) => rule.rule_name === previousRuleName)?.rule_name || rules[0]?.rule_name || "";
    const selectedRule = rules.find((rule) => rule.rule_name === selectedRuleName);
    html = `
      <div class="row">
        <div class="field">
          <label for="field-rule-name">Rule name</label>
          <select id="field-rule-name" class="mono">
            ${rules
              .map(
                (rule) => `
                  <option value="${escapeHtml(rule.rule_name)}" ${rule.rule_name === selectedRuleName ? "selected" : ""}>
                    ${escapeHtml(rule.rule_name)}
                  </option>
                `
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="field-new-weight">New weight</label>
          <input
            id="field-new-weight"
            type="number"
            step="0.01"
            min="0"
            max="1"
            class="mono"
            value="${escapeHtml(previousNewWeight)}"
          />
        </div>
      </div>
      <div class="hint">
        Any scoring rule weight can be changed here, not just <span class="mono">fairness_score</span>.
        Current weight for <span class="mono">${escapeHtml(selectedRuleName || "rule")}</span> is
        <span class="mono">${escapeHtml(selectedRule?.current_weight ?? "N/A")}</span>.
      </div>
    `;
  } else if (type === "rule_toggle") {
    const rules = mutationOptions.rule_toggle || [];
    const selectedRuleName =
      rules.find((rule) => rule.rule_name === previousRuleName)?.rule_name || rules[0]?.rule_name || "";
    const selectedRule = rules.find((rule) => rule.rule_name === selectedRuleName);
    const selectedEnabled = previousEnabled || String(selectedRule?.enabled ?? true);
    html = `
      <div class="row">
        <div class="field">
          <label for="field-rule-name">Rule name</label>
          <select id="field-rule-name" class="mono">
            ${rules
              .map(
                (rule) => `
                  <option value="${escapeHtml(rule.rule_name)}" ${rule.rule_name === selectedRuleName ? "selected" : ""}>
                    ${escapeHtml(rule.rule_name)} (${escapeHtml(rule.rule_group)})
                  </option>
                `
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="field-enabled">Enabled</label>
          <select id="field-enabled">
            <option value="true" ${selectedEnabled === "true" ? "selected" : ""}>true</option>
            <option value="false" ${selectedEnabled === "false" ? "selected" : ""}>false</option>
          </select>
        </div>
      </div>
      <div class="hint">
        Toggle any current hard or scoring rule. The live config currently has
        <span class="mono">${escapeHtml(selectedRuleName || "rule")}</span> set to
        <span class="mono">${escapeHtml(selectedRule?.enabled ?? true)}</span>.
      </div>
    `;
  } else {
    const partnerPool = mutationOptions.partner_pool || { actions: ["remove"], vehicle_type_choices: ["bike"] };
    const selectedAction =
      partnerPool.actions.find((action) => action === previousAction) || partnerPool.actions[0] || "remove";
    const selectedVehicleTypes = previousVehicleTypes.length
      ? previousVehicleTypes
      : [partnerPool.vehicle_type_choices[0]].filter(Boolean);
    html = `
      <div class="row">
        <div class="field">
          <label for="field-action">Action</label>
          <select id="field-action">
            ${partnerPool.actions
              .map(
                (action) => `
                  <option value="${escapeHtml(action)}" ${action === selectedAction ? "selected" : ""}>
                    ${escapeHtml(action)}
                  </option>
                `
              )
              .join("")}
          </select>
        </div>
        <div class="field">
          <label for="field-partner-id">Partner ID</label>
          <input id="field-partner-id" class="mono" placeholder="PT-123" value="${escapeHtml(previousPartnerId)}" />
        </div>
      </div>
      <div class="hint">Use remove for an existing partner, or add or modify to provide a replacement partner payload with chosen vehicle types.</div>
      ${
        selectedAction === "remove"
          ? ""
          : `
            <div class="row">
              <div class="field">
                <label for="field-latitude">Latitude</label>
                <input id="field-latitude" type="number" step="0.000001" class="mono" value="${escapeHtml(previousLatitude)}" />
              </div>
              <div class="field">
                <label for="field-longitude">Longitude</label>
                <input id="field-longitude" type="number" step="0.000001" class="mono" value="${escapeHtml(previousLongitude)}" />
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="field-rating">Rating</label>
                <input id="field-rating" type="number" step="0.1" class="mono" value="${escapeHtml(previousRating || "4.5")}" />
              </div>
              <div class="field">
                <label for="field-vehicle-types">Vehicle types</label>
                <select id="field-vehicle-types" class="mono" multiple size="3">
                  ${partnerPool.vehicle_type_choices
                    .map(
                      (vehicleType) => `
                        <option value="${escapeHtml(vehicleType)}" ${selectedVehicleTypes.includes(vehicleType) ? "selected" : ""}>
                          ${escapeHtml(vehicleType)}
                        </option>
                      `
                    )
                    .join("")}
                </select>
              </div>
            </div>
            <div class="row">
              <div class="field">
                <label for="field-is-available">Available</label>
                <select id="field-is-available">
                  <option value="true" ${previousAvailability === "true" ? "selected" : ""}>true</option>
                  <option value="false" ${previousAvailability === "false" ? "selected" : ""}>false</option>
                </select>
              </div>
              <div class="field">
                <label for="field-active">Active</label>
                <select id="field-active">
                  <option value="true" ${previousActive === "true" ? "selected" : ""}>true</option>
                  <option value="false" ${previousActive === "false" ? "selected" : ""}>false</option>
                </select>
              </div>
            </div>
          `
      }
    `;
  }

  elements.mutationFields.innerHTML = html;
  document.getElementById("field-rule-name")?.addEventListener("change", renderMutationFields);
  document.getElementById("field-parameter-name")?.addEventListener("change", renderMutationFields);
  document.getElementById("field-action")?.addEventListener("change", renderMutationFields);
}

function collectMutationFromFields() {
  const type = elements.mutationType.value;
  if (type === "rule_parameter") {
    return {
      mutation_type: "rule_parameter",
      rule_name: document.getElementById("field-rule-name").value.trim(),
      parameter_name: document.getElementById("field-parameter-name").value.trim(),
      new_value: document.getElementById("field-new-value").value,
    };
  }
  if (type === "rule_weight") {
    return {
      mutation_type: "rule_weight",
      rule_name: document.getElementById("field-rule-name").value.trim(),
      new_weight: document.getElementById("field-new-weight").value,
    };
  }
  if (type === "rule_toggle") {
    return {
      mutation_type: "rule_toggle",
      rule_name: document.getElementById("field-rule-name").value.trim(),
      enabled: document.getElementById("field-enabled").value === "true",
    };
  }
  return {
    mutation_type: "partner_pool",
    action: document.getElementById("field-action").value,
    partner_id: document.getElementById("field-partner-id").value.trim(),
    latitude: document.getElementById("field-latitude")?.value ?? "",
    longitude: document.getElementById("field-longitude")?.value ?? "",
    rating: document.getElementById("field-rating")?.value ?? "",
    vehicle_types: Array.from(document.getElementById("field-vehicle-types")?.selectedOptions || []).map(
      (option) => option.value
    ),
    is_available: (document.getElementById("field-is-available")?.value ?? "true") === "true",
    active: (document.getElementById("field-active")?.value ?? "true") === "true",
  };
}

function validateMutation(mutation) {
  if (mutation.mutation_type === "rule_parameter") {
    return mutation.rule_name && mutation.parameter_name && mutation.new_value !== "";
  }
  if (mutation.mutation_type === "rule_weight") {
    return mutation.rule_name && mutation.new_weight !== "";
  }
  if (mutation.mutation_type === "rule_toggle") {
    return mutation.rule_name;
  }
  if (!mutation.partner_id) {
    return false;
  }
  if ((mutation.action || "remove") === "remove") {
    return true;
  }
  return (
    mutation.latitude !== ""
    && mutation.longitude !== ""
    && mutation.rating !== ""
    && normalizeVehicleTypes(mutation.vehicle_types).length > 0
  );
}

function renderAllocationResults(data) {
  const summary = data.summary || {};
  const diagnostics = data.aggregate_diagnostics || {};
  const activeRules = summary.active_hard_rules || [];
  const firstOrderId = data.allocations && data.allocations.length ? data.allocations[0].order_id : "";

  elements.auditOrderId.value = firstOrderId;
  elements.rejectionOrderId.value = firstOrderId;
  elements.verifyManifestId.value = data.manifest_id || "";
  elements.replayManifestId.value = data.manifest_id || "";
  elements.simulateManifestId.value = data.manifest_id || "";

  const rows = (data.allocations || [])
    .map(
      (allocation) => `
        <tr>
          <td class="mono">${escapeHtml(allocation.order_id)}</td>
          <td class="mono">${escapeHtml(allocation.partner_id ?? "UNALLOCATED")}</td>
          <td><span class="result-badge ${allocation.status === "assigned" ? "success" : "mismatch"}">${escapeHtml(allocation.status)}</span></td>
          <td class="mono">${escapeHtml(allocation.reason ?? "")}</td>
          <td class="score mono">${allocation.weighted_score ?? "—"}</td>
        </tr>
      `
    )
    .join("");

  const failureCombos = Object.entries(diagnostics.unallocated_orders_by_failure_combination || {})
    .map(([reason, count]) => `<div class="diagnostic-item mono">${escapeHtml(reason)}: ${escapeHtml(count)}</div>`)
    .join("") || `<div class="diagnostic-item">No rejection signatures were recorded in this run.</div>`;

  elements.allocationResults.innerHTML = `
    <div class="banner">
      Manifest <span class="hash mono">${escapeHtml(data.manifest_id)}</span> created for
      <strong>${escapeHtml(summary.total_orders ?? 0)}</strong> orders.
    </div>

    <div class="stats">
      <div class="stat-card">
        <span class="stat-label">Allocated</span>
        <span class="stat-value">${escapeHtml(summary.allocated_orders ?? 0)}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Unallocated</span>
        <span class="stat-value">${escapeHtml(summary.unallocated_orders ?? 0)}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Manifest ID</span>
        <span class="stat-value mono" style="font-size: 0.95rem">${escapeHtml(data.manifest_id)}</span>
      </div>
    </div>

    <div class="stack">
      <div>
        <h3>Active hard rules in this run</h3>
        <div class="rule-list">
          ${activeRules.map((rule) => `<span class="rule-chip mono">${escapeHtml(rule)}</span>`).join("") || `<span class="hint">No active hard rules reported.</span>`}
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Partner</th>
              <th>Status</th>
              <th>Reason</th>
              <th>Weighted Score</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>

      <div class="stats">
        <div class="stat-card">
          <span class="stat-label">Aggregate Allocated</span>
          <span class="stat-value">${escapeHtml(diagnostics.allocated ?? 0)}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Aggregate Unallocated</span>
          <span class="stat-value">${escapeHtml(diagnostics.unallocated ?? 0)}</span>
        </div>
        <div class="stat-card">
          <span class="stat-label">Rejection signatures</span>
          <span class="stat-value">${escapeHtml(Object.keys(diagnostics.unallocated_orders_by_failure_combination || {}).length)}</span>
        </div>
      </div>

      <div>
        <h3>Unallocated rejection signatures</h3>
        <div class="diagnostic-list">${failureCombos}</div>
      </div>

      <details>
        <summary>Raw allocation response</summary>
        <div class="details-body"><pre>${escapeHtml(prettyJson(data))}</pre></div>
      </details>
    </div>
  `;
}

function renderManifestCard(manifest) {
  elements.manifestCard.innerHTML = `
    <div class="info-card stack">
      <div class="meta-list">
        <div class="meta-item">
          <span class="meta-label">Manifest ID</span>
          <span class="mono">${escapeHtml(manifest.manifest_id)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Decision Timestamp</span>
          <span>${escapeHtml(manifest.decided_at)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Config Version Hash</span>
          <span class="mono">${escapeHtml(manifest.config_version_hash)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Manifest Signature</span>
          <span class="mono">${escapeHtml(manifest.manifest_signature)}</span>
        </div>
      </div>
    </div>
  `;
}

function renderTrace(tracePayload, orderId) {
  const orderTrace = (tracePayload.trace?.orders || []).find((entry) => entry.order_id === orderId);
  if (!orderTrace) {
    elements.traceContainer.innerHTML = `<div class="error-card"><strong>Trace missing</strong><div class="small">No stored trace found for order ${escapeHtml(orderId)}.</div></div>`;
    return;
  }

  const candidates = orderTrace.candidates || [];
  elements.traceContainer.innerHTML = `
    <div class="trace-card stack">
      <div class="candidate-head">
        <div>
          <strong>Order ${escapeHtml(orderId)}</strong>
          <div class="small">Recorded decision reason: <span class="mono">${escapeHtml(orderTrace.decision_reason)}</span></div>
        </div>
        <span class="result-badge ${orderTrace.selected_partner_id ? "success" : "mismatch"}">
          ${escapeHtml(orderTrace.selected_partner_id ? "ALLOCATED" : "UNALLOCATED")}
        </span>
      </div>
      ${candidates
        .map((candidate) => {
          const selected = candidate.partner_id === orderTrace.selected_partner_id;
          const hardRules = (candidate.hard_results || [])
            .map(
              (rule) => `
                <div class="rule-row">
                  <div>
                    <strong class="mono">${escapeHtml(rule.rule)}</strong>
                    <div class="small">${escapeHtml(rule.rationale || "")}</div>
                  </div>
                  <span class="result-badge ${rule.passed ? "success" : "mismatch"}">${rule.passed ? "PASSED" : "FAILED"}</span>
                </div>
              `
            )
            .join("");
          const scoringRules = (candidate.scoring_results || [])
            .map((rule) => {
              const weightedContribution = formatTraceNumber(rule.weighted_contribution, 4);
              const rawScore = formatTraceNumber(rule.raw_score, 3);
              const barWidth = scoreBarWidth(rule.raw_score);
              return `
                <div class="score-row">
                  <div class="score-copy">
                    <strong class="mono">${escapeHtml(rule.rule)}</strong>
                    <div class="small">Weighted contribution: <span class="mono">${escapeHtml(weightedContribution)}</span></div>
                  </div>
                  <div class="score-metric">
                    <div class="score-bar"><span style="width: ${barWidth}%"></span></div>
                    <span class="mono score-value">${escapeHtml(rawScore)}</span>
                  </div>
                </div>
              `
            })
            .join("");

          return `
            <details class="candidate-card" ${selected ? "open" : ""}>
              <summary>
                <span class="candidate-title">
                  <strong class="mono">${escapeHtml(candidate.partner_id)}</strong>
                  <span class="result-badge ${selected ? "success" : "warning"}">${selected ? "SELECTED" : "REJECTED"}</span>
                </span>
              </summary>
              <div class="details-body stack">
                <div class="small">Total weighted score: <span class="mono">${candidate.weighted_score ?? "—"}</span></div>
                <div class="stack">${hardRules || `<div class="small">No hard rule evaluations recorded.</div>`}</div>
                <div class="stack">${scoringRules || `<div class="small">No scoring rules ran for this candidate.</div>`}</div>
              </div>
            </details>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderVerifyResult(data) {
  const verified = data.status === "VERIFIED";
  elements.verifyResult.innerHTML = `
    <div class="info-card stack">
      <div class="candidate-head">
        <div>
          <strong>${verified ? "VERIFIED" : "TAMPERED"}</strong>
          <div class="small">${verified ? "Signature valid. Decision is reproducible." : escapeHtml(data.details || "Verification mismatch detected.")}</div>
        </div>
        <span class="result-badge ${verified ? "verified" : "tampered"}">${escapeHtml(data.status)}</span>
      </div>
      <div class="meta-list">
        <div class="meta-item">
          <span class="meta-label">Manifest ID</span>
          <span class="mono">${escapeHtml(data.manifest_id)}</span>
        </div>
        <div class="meta-item">
          <span class="meta-label">Verified At</span>
          <span>${escapeHtml(data.verified_at)}</span>
        </div>
      </div>
    </div>
  `;
}

function renderRejections(summary) {
  const rows = (summary.hard_rule_failures || [])
    .map(
      (failure) => `
        <tr>
          <td class="mono">${escapeHtml(failure.partner_id)}</td>
          <td>${escapeHtml(failure.reason)}</td>
          <td class="mono">${escapeHtml(failure.rule)}</td>
        </tr>
      `
    )
    .join("");

  elements.rejectionTable.innerHTML = `
    <div class="banner">
      Allocation status: <span class="mono">${escapeHtml(summary.allocation_status)}</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Partner ID</th>
            <th>Rejection Reason</th>
            <th>Rule Name</th>
          </tr>
        </thead>
        <tbody>${rows || `<tr><td colspan="3">No hard-rule failures recorded.</td></tr>`}</tbody>
      </table>
    </div>
  `;
}

function renderReplay(data) {
  const replayedByOrder = new Map((data.replayed_allocations || []).map((item) => [item.order_id, item]));
  const rows = (data.original_allocations || [])
    .map((original) => {
      const replayed = replayedByOrder.get(original.order_id) || { partner_id: null };
      const match = original.partner_id === replayed.partner_id;
      return `
        <tr class="${match ? "" : "mismatch-row"}">
          <td class="mono">${escapeHtml(original.order_id)}</td>
          <td class="mono">${escapeHtml(original.partner_id ?? "UNALLOCATED")}</td>
          <td class="mono">${escapeHtml(replayed.partner_id ?? "UNALLOCATED")}</td>
          <td>${match ? "Match" : "Non-determinism detected — rule configuration may have changed"}</td>
        </tr>
      `;
    })
    .join("");

  elements.replayResults.innerHTML = `
    <div class="banner">
      <span class="result-badge ${data.status === "SUCCESS" ? "success" : "mismatch"}">${escapeHtml(data.status)}</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Original Partner</th>
            <th>Replayed Partner</th>
            <th>Match?</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <details>
      <summary>Raw replay response</summary>
      <div class="details-body"><pre>${escapeHtml(prettyJson(data.raw_replay_response))}</pre></div>
    </details>
  `;
}

function renderSimulation(data) {
  const rows = data.trace_diff || [];
  const changedCount = Number(data.counterfactual_summary?.total_changed_orders || 0);
  const unchangedCount = Math.max(0, rows.length - changedCount);
  const explanations = rows
    .filter((row) => row.changed)
    .map(
      (row) => `
        <div class="diagnostic-item">
          Under the mutated ruleset, <span class="mono">${escapeHtml(row.hypothetical_partner ?? "UNALLOCATED")}</span>
          replaced <span class="mono">${escapeHtml(row.original_partner ?? "UNALLOCATED")}</span>
          because the decision reason changed from
          <span class="mono">${escapeHtml(row.original_reason ?? "unknown")}</span>
          to <span class="mono">${escapeHtml(row.hypothetical_reason ?? "unknown")}</span>.
        </div>
      `
    )
    .join("");

  const tableRows = rows
    .map(
      (row) => `
        <tr class="${row.changed ? "changed-row" : ""}">
          <td class="mono">${escapeHtml(row.order_id)}</td>
          <td class="mono">${escapeHtml(row.original_partner ?? "UNALLOCATED")}</td>
          <td class="mono">${escapeHtml(row.hypothetical_partner ?? "UNALLOCATED")}</td>
          <td>${row.changed ? "Changed" : "Unchanged"}</td>
        </tr>
      `
    )
    .join("");

  elements.simulationResults.innerHTML = `
    <div class="stats">
      <div class="stat-card">
        <span class="stat-label">Changed Orders</span>
        <span class="stat-value">${escapeHtml(changedCount)}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Unchanged Orders</span>
        <span class="stat-value">${escapeHtml(unchangedCount)}</span>
      </div>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Order ID</th>
            <th>Original Partner</th>
            <th>Mutated Partner</th>
            <th>Changed?</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>

    <div class="stack">
      <h3>Assignment deltas</h3>
      <div class="explanation-list">${explanations || `<div class="diagnostic-item">No partner selections changed under this counterfactual run.</div>`}</div>
    </div>

    <details>
      <summary>Raw simulation response</summary>
      <div class="details-body"><pre>${escapeHtml(prettyJson(data))}</pre></div>
    </details>
  `;
}

function renderDiagnostics(health, runtime, diagnostics, reservations) {
  elements.diagnosticsHealth.innerHTML = `
    <div class="diagnostic-list">
      <div class="diagnostic-item">
        <div class="candidate-head">
          <span>API Health</span>
          <span class="result-badge ${health.status === "ok" ? "success" : "mismatch"}">${escapeHtml(health.status)}</span>
        </div>
      </div>
      <div class="diagnostic-item">
        <strong>DB Connected</strong>
        <div class="small mono">${escapeHtml(runtime.db_connected)}</div>
      </div>
      <div class="diagnostic-item">
        <strong>Version</strong>
        <div class="small mono">${escapeHtml(runtime.version)}</div>
      </div>
    </div>
  `;

  const activeRules = (diagnostics.active_rules || [])
    .map((rule) => `<span class="rule-chip mono">${escapeHtml(rule)}</span>`)
    .join("");
  elements.diagnosticsSummary.innerHTML = `
    <div class="diagnostic-list">
      <div class="diagnostic-item"><strong>Total allocations</strong><div class="small mono">${escapeHtml(diagnostics.total_allocations)}</div></div>
      <div class="diagnostic-item"><strong>Total unallocated</strong><div class="small mono">${escapeHtml(diagnostics.total_unallocated)}</div></div>
      <div class="diagnostic-item"><strong>Average score</strong><div class="small mono">${escapeHtml(diagnostics.avg_score ?? "N/A")}</div></div>
      <div class="diagnostic-item"><strong title="Requires event log">Fairness Gini: N/A</strong></div>
      <div class="diagnostic-item">
        <strong>Active rules</strong>
        <div class="rule-list" style="margin-top: 8px">${activeRules || `<span class="hint">No active rules reported.</span>`}</div>
      </div>
    </div>
  `;

  const reservationEntries = Object.entries(reservations || {});
  elements.diagnosticsReservations.innerHTML = reservationEntries.length
    ? `<div class="reservation-list">
        ${reservationEntries
          .map(([partnerId, reservation]) => {
            const remaining = Math.max(0, Number(reservation.expires_at) - Date.now() / 1000);
            return `
              <div class="reservation-item mono">
                Partner ${escapeHtml(partnerId)} → Order ${escapeHtml(reservation.order_id)}
                (expires in ${remaining.toFixed(1)} seconds)
              </div>
            `;
          })
          .join("")}
      </div>`
    : `<div class="diagnostic-item">No active reservations.</div>`;
}

async function loadDatasetCatalog() {
  try {
    const payload = await fetchJson("/demo/sample-datasets");
    state.datasets = payload.datasets || [];
    elements.datasetSelect.innerHTML = state.datasets
      .map((dataset) => `<option value="${escapeHtml(dataset.slug)}">${escapeHtml(dataset.name)} (${dataset.orders} orders / ${dataset.partners} partners)</option>`)
      .join("");
    elements.datasetSelect.value = payload.default;
    await loadSampleDataset(payload.default);
  } catch (error) {
    showError(elements.allocateStatus, error);
  }
}

async function loadSimulationPresets() {
  try {
    const presets = await fetchJson("/demo/simulation-presets");
    state.presets = presets || [];
    elements.presetSelect.innerHTML =
      `<option value="">Select a mutation preset...</option>` +
      state.presets
        .map((preset, index) => `<option value="${index}">${escapeHtml(preset.name)}</option>`)
        .join("");
  } catch (error) {
    showError(elements.simulateStatus, error);
  }
}

function selectedPreset() {
  const presetIndex = elements.presetSelect.value.trim();
  if (!presetIndex) {
    return null;
  }
  return state.presets[Number(presetIndex)] || null;
}

async function loadMutationOptions() {
  try {
    state.mutationOptions = await fetchJson("/demo/mutation-options");
    renderMutationFields();
  } catch (error) {
    showError(elements.simulateStatus, error);
  }
}

async function loadSampleDataset(datasetSlug) {
  showLoading(elements.allocateStatus, "Loading allocation dataset...");
  try {
    const payload = await fetchJson(`/demo/sample-payload?dataset=${encodeURIComponent(datasetSlug)}`);
    const json = prettyJson(payload);
    state.loadedPayloadText = json;
    elements.allocationPayload.value = json;
    elements.idempotencyKey.value = generateIdempotencyKey();
    elements.allocateStatus.innerHTML = `<div class="banner">Loaded allocation dataset <span class="mono">${escapeHtml(datasetSlug)}</span>.</div>`;
    elements.allocationResults.innerHTML = `<div class="banner">Run allocation to populate this panel. The first order ID and manifest ID are copied into the audit, replay, and simulation tabs so the investigation flow stays aligned.</div>`;
  } catch (error) {
    showError(elements.allocateStatus, error);
  }
}

async function runAllocation() {
  elements.allocateStatus.innerHTML = "";
  showLoading(elements.allocateStatus, "Running allocation...");

  let payload = null;
  try {
    payload = JSON.parse(elements.allocationPayload.value);
  } catch (error) {
    showError(elements.allocateStatus, { message: `Invalid JSON: ${error.message}` });
    return;
  }

  if (elements.allocationPayload.value !== state.loadedPayloadText && !elements.idempotencyKey.value.trim()) {
    elements.idempotencyKey.value = generateIdempotencyKey();
  }

  try {
    const response = await fetchJson("/allocations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Idempotency-Key": elements.idempotencyKey.value.trim() || generateIdempotencyKey(),
      },
      body: JSON.stringify(payload),
    });

    elements.allocateStatus.innerHTML = `<div class="banner">Allocation completed successfully.</div>`;
    renderAllocationResults(response);
  } catch (error) {
    showError(elements.allocateStatus, error);
    elements.allocationResults.innerHTML = `<div class="banner">Results unavailable because the request failed.</div>`;
  }
}

async function findManifest() {
  const orderId = elements.auditOrderId.value.trim();
  if (!orderId) {
    showError(elements.auditManifestStatus, { message: "Order ID is required." });
    return;
  }

  showLoading(elements.auditManifestStatus, "Loading manifest...");
  try {
    const manifest = await fetchJson(`/audit/manifest/${encodeURIComponent(orderId)}`);
    elements.auditManifestStatus.innerHTML = `<div class="banner">Manifest located for order <span class="mono">${escapeHtml(orderId)}</span>.</div>`;
    renderManifestCard(manifest);
    elements.verifyManifestId.value = manifest.manifest_id;
    elements.replayManifestId.value = manifest.manifest_id;
    elements.simulateManifestId.value = manifest.manifest_id;
  } catch (error) {
    showError(elements.auditManifestStatus, error);
    elements.manifestCard.innerHTML = "";
  }
}

async function viewTrace() {
  const orderId = elements.auditOrderId.value.trim();
  if (!orderId) {
    showError(elements.traceContainer, { message: "Order ID is required." });
    return;
  }

  showLoading(elements.traceContainer, "Loading stored trace...");
  try {
    const trace = await fetchJson(`/audit/trace/${encodeURIComponent(orderId)}`);
    renderTrace(trace, orderId);
  } catch (error) {
    showError(elements.traceContainer, error);
  }
}

async function verifyIntegrity() {
  const manifestId = elements.verifyManifestId.value.trim();
  if (!manifestId) {
    showError(elements.verifyStatus, { message: "Manifest ID is required." });
    return;
  }

  showLoading(elements.verifyStatus, "Verifying manifest integrity...");
  try {
    const result = await fetchJson(`/audit/verify/${encodeURIComponent(manifestId)}`);
    elements.verifyStatus.innerHTML = `<div class="banner">Verification finished for <span class="mono">${escapeHtml(manifestId)}</span>.</div>`;
    renderVerifyResult(result);
  } catch (error) {
    showError(elements.verifyStatus, error);
    elements.verifyResult.innerHTML = "";
  }
}

async function viewRejections() {
  const orderId = elements.rejectionOrderId.value.trim();
  if (!orderId) {
    showError(elements.rejectionStatus, { message: "Order ID is required." });
    return;
  }

  showLoading(elements.rejectionStatus, "Loading rejection summary...");
  try {
    const result = await fetchJson(`/audit/rejections/${encodeURIComponent(orderId)}`);
    elements.rejectionStatus.innerHTML = `<div class="banner">Loaded rejection summary for <span class="mono">${escapeHtml(orderId)}</span>.</div>`;
    renderRejections(result);
  } catch (error) {
    showError(elements.rejectionStatus, error);
    elements.rejectionTable.innerHTML = "";
  }
}

async function runReplay() {
  const manifestId = elements.replayManifestId.value.trim();
  if (!manifestId) {
    showError(elements.replayStatus, { message: "Manifest ID is required." });
    return;
  }

  showLoading(elements.replayStatus, "Replaying deterministic trace...");
  try {
    const result = await fetchJson(`/audit/replay/${encodeURIComponent(manifestId)}`);
    elements.replayStatus.innerHTML = `<div class="banner">Replay completed for <span class="mono">${escapeHtml(manifestId)}</span>.</div>`;
    renderReplay(result);
  } catch (error) {
    showError(elements.replayStatus, error);
    elements.replayResults.innerHTML = "";
  }
}

async function runSimulation() {
  const manifestId = elements.simulateManifestId.value.trim();
  if (!manifestId) {
    showError(elements.simulateStatus, { message: "Manifest ID is required." });
    return;
  }

  if (!state.mutations.length) {
    showError(elements.simulateStatus, { message: "Add at least one mutation before running a simulation." });
    return;
  }

  showLoading(elements.simulateStatus, "Running counterfactual simulation...");
  try {
    const payload = {
      manifest_id: manifestId,
      mutations: state.mutations.map(mutationToApi),
    };
    const result = await fetchJson("/simulations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    elements.simulateStatus.innerHTML = `<div class="banner">Simulation completed for <span class="mono">${escapeHtml(manifestId)}</span>.</div>`;
    renderSimulation(result);
  } catch (error) {
    showError(elements.simulateStatus, error);
    elements.simulationResults.innerHTML = `<div class="banner">Simulation results unavailable because the request failed.</div>`;
  }
}

async function refreshDiagnostics() {
  showLoading(elements.diagnosticsStatus, "Refreshing diagnostics...");
  const [health, runtime, diagnostics, reservations] = await Promise.allSettled([
    fetchJson("/health"),
    fetchJson("/diagnostics/runtime"),
    fetchJson("/audit/diagnostics"),
    fetchJson("/allocations/reservations/active"),
  ]);

  const firstFailure = [health, runtime, diagnostics, reservations].find((result) => result.status === "rejected");
  if (firstFailure) {
    showError(elements.diagnosticsStatus, firstFailure.reason);
  } else {
    elements.diagnosticsStatus.innerHTML = `<div class="banner">Diagnostics refreshed successfully.</div>`;
  }

  elements.diagnosticsHealth.innerHTML = health.status === "fulfilled" && runtime.status === "fulfilled"
    ? ""
    : `<div class="error-card"><strong>Health unavailable</strong><div class="small">One or more diagnostics calls failed.</div></div>`;
  elements.diagnosticsSummary.innerHTML = diagnostics.status === "fulfilled"
    ? ""
    : `<div class="error-card"><strong>Allocation diagnostics unavailable</strong><div class="small">The latest diagnostics endpoint did not return data.</div></div>`;
  elements.diagnosticsReservations.innerHTML = reservations.status === "fulfilled"
    ? ""
    : `<div class="error-card"><strong>Reservations unavailable</strong><div class="small">Active reservation diagnostics did not return data.</div></div>`;

  if (
    health.status === "fulfilled" &&
    runtime.status === "fulfilled" &&
    diagnostics.status === "fulfilled" &&
    reservations.status === "fulfilled"
  ) {
    renderDiagnostics(health.value, runtime.value, diagnostics.value, reservations.value);
  }
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setTab(button.dataset.tab));
});

elements.datasetLoad.addEventListener("click", () => loadSampleDataset(elements.datasetSelect.value));
elements.refreshIdempotency.addEventListener("click", () => {
  elements.idempotencyKey.value = generateIdempotencyKey();
});
elements.runAllocation.addEventListener("click", runAllocation);
elements.findManifest.addEventListener("click", findManifest);
elements.viewTrace.addEventListener("click", viewTrace);
elements.verifyIntegrity.addEventListener("click", verifyIntegrity);
elements.viewRejections.addEventListener("click", viewRejections);
elements.runReplay.addEventListener("click", runReplay);
elements.mutationType.addEventListener("change", renderMutationFields);
elements.addMutation.addEventListener("click", () => {
  const mutation = collectMutationFromFields();
  if (!validateMutation(mutation)) {
    showError(elements.simulateStatus, { message: "Complete the mutation fields before adding it." });
    return;
  }
  elements.simulateStatus.innerHTML = "";
  state.mutations.push(mutation);
  renderMutationList();
});
elements.clearMutations.addEventListener("click", () => {
  state.mutations = [];
  renderMutationList();
});
elements.runSimulation.addEventListener("click", runSimulation);
elements.presetSelect.addEventListener("change", () => {
  const selected = selectedPreset();
  if (!selected) {
    elements.presetHelper.textContent = "Run an allocation first, then provide its manifest_id here.";
    return;
  }
  elements.presetHelper.textContent = `${selected.description}${selected.requires_manifest_id ? " Run an allocation first, then provide its manifest_id here." : ""}`;
});
elements.applyPreset.addEventListener("click", () => {
  const selected = selectedPreset();
  if (!selected) {
    showError(elements.simulateStatus, { message: "Select a mutation preset before applying it." });
    return;
  }
  elements.simulateStatus.innerHTML = "";
  state.mutations = selected.mutations.map((mutation) => ({ ...mutation }));
  renderMutationList();
  elements.presetHelper.textContent = `${selected.description}${selected.requires_manifest_id ? " Run an allocation first, then provide its manifest_id here." : ""}`;
});
elements.diagnosticsToggle.addEventListener("click", () => {
  elements.diagnosticsSidebar.classList.toggle("open");
});
elements.diagnosticsRefresh.addEventListener("click", refreshDiagnostics);

renderMutationFields();
renderMutationList();
elements.idempotencyKey.value = generateIdempotencyKey();
loadDatasetCatalog();
loadSimulationPresets();
loadMutationOptions();
