/**
 * Deep Signal — Dependency Tree UI
 *
 * Vanilla JS frontend for the dependency tree API.
 * All filtering/sorting/truncation is backend-driven.
 * The fetched response object is never mutated.
 */

const API_BASE = window.DS_API_BASE || "";

// ─── State ───────────────────────────────────────────────────────────
let currentResponse = null;   // immutable API response
let expandedKeys = new Set();  // tree-occurrence keys that are expanded
let selectedKey = null;        // tree-occurrence key of selected node
let isRefetching = false;

// ─── DOM refs ────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const repoInput       = $("repoInput");
const loadBtn         = $("loadBtn");
const errBox          = $("errBox");
const summarySection  = $("summarySection");
const summaryGrid     = $("summaryGrid");
const repoNameDisplay = $("repoNameDisplay");
const provenanceBanner= $("provenanceBanner");
const filterSection   = $("filterSection");
const treeContainer   = $("treeContainer");
const treeRoot        = $("treeRoot");
const initialState    = $("initialState");
const loadingState    = $("loadingState");
const emptyState      = $("emptyState");
const detailContent   = $("detailContent");
const refetchIndicator= $("refetchIndicator");

// Controls
const maxDepthSelect  = $("maxDepthSelect");
const highRiskOnly    = $("highRiskOnly");
const vulnerableOnly  = $("vulnerableOnly");
const directOnly      = $("directOnly");
const sortBySelect    = $("sortBySelect");
const truncateSelect  = $("truncateSelect");

// ─── Scope constants ─────────────────────────────────────────────────
const SCOPE_BADGE_CLASSES = {
  runtime:  "scope-runtime",
  dev:      "scope-dev",
  test:     "scope-dev",
  build:    "scope-dev",
  optional: "scope-neutral",
  peer:     "scope-neutral",
  unknown:  "scope-unknown",
};

const SCOPE_TOOLTIPS = {
  runtime:  "Runtime: loaded when your application runs",
  dev:      "Dev: used only during development",
  test:     "Test: used only during testing",
  build:    "Build: used during compilation or build process",
  optional: "Optional: not required for core functionality",
  peer:     "Peer: expected to be provided by the consumer",
  unknown:  "Unknown: scope could not be determined from manifests",
};

const SCOPE_FILTER_RULES = {
  "runtime-direct": (node) => node.dependency_scope === "runtime" && node.depth === 1,
  "runtime-all":    (node) => node.dependency_scope === "runtime",
  "dev-test":       (node) => node.dependency_scope === "dev" || node.dependency_scope === "test",
  "build":          (node) => node.dependency_scope === "build",
  "optional-peer":  (node) => node.dependency_scope === "optional" || node.dependency_scope === "peer",
  "unknown":        (node) => node.dependency_scope === "unknown",
};

// ─── Scope data detection helpers ────────────────────────────────────

/**
 * Check if the API response contains scope-related fields at all.
 * Used to decide whether to render the scope summary section.
 */
function hasScopeFields(data) {
  if (!data || !data.summary_metrics) return false;
  const m = data.summary_metrics;
  return m.direct_runtime_dependency_count != null
      || m.direct_dev_dependency_count != null
      || m.direct_total_dependency_count != null;
}

/**
 * Recursively check if any tree node has a non-null dependency_scope.
 */
function treeHasAnyScope(node) {
  if (!node) return false;
  if (node.dependency_scope) return true;
  if (node.children) {
    return node.children.some(child => treeHasAnyScope(child));
  }
  return false;
}

/**
 * Check if the API response contains meaningful (non-trivial) scope data.
 * Returns true if at least one non-unknown scope count > 0,
 * OR at least one tree node has a non-null dependency_scope.
 * Used to decide whether to show the scope filter and full breakdown.
 */
function hasMeaningfulScopeData(data) {
  if (!data || !data.summary_metrics) return false;
  const m = data.summary_metrics;
  if ((m.direct_runtime_dependency_count || 0) > 0
      || (m.direct_dev_dependency_count || 0) > 0
      || (m.direct_test_dependency_count || 0) > 0
      || (m.direct_build_dependency_count || 0) > 0
      || (m.direct_optional_dependency_count || 0) > 0
      || (m.direct_peer_dependency_count || 0) > 0) {
    return true;
  }
  if (data.tree) {
    return treeHasAnyScope(data.tree);
  }
  return false;
}

// ─── Scope filtering ─────────────────────────────────────────────────

/**
 * Check if a node matches the active scope filter.
 * Uses SCOPE_FILTER_RULES exclusively — no duplicated filter logic.
 */
function matchesScopeFilter(node, scopeFilter) {
  if (!scopeFilter) return true; // "All" — no filtering
  const rule = SCOPE_FILTER_RULES[scopeFilter];
  return rule ? rule(node) : true;
}

/**
 * Filter a tree by scope, preserving ancestor paths for matching nodes.
 * Returns a new tree (immutable — does not modify the original).
 * Preserved ancestors retain their original dependency_scope values.
 */
function filterTreeByScope(tree, scopeFilter) {
  if (!scopeFilter) return tree; // "All" — return original tree

  function cloneAndFilter(node) {
    // Check if this node matches
    const nodeMatches = matchesScopeFilter(node, scopeFilter);

    // Recursively filter children
    let filteredChildren = [];
    if (node.children) {
      for (const child of node.children) {
        const result = cloneAndFilter(child);
        if (result) filteredChildren.push(result);
      }
    }

    // Include this node if it matches OR if any descendant matches (ancestor preservation)
    if (nodeMatches || filteredChildren.length > 0) {
      // Clone the node — preserve all original properties including dependency_scope
      return Object.assign({}, node, { children: filteredChildren });
    }

    return null; // Exclude this subtree
  }

  return cloneAndFilter(tree) || Object.assign({}, tree, { children: [] });
}

// ─── Occurrence key generation ───────────────────────────────────────
// Because the same canonical ID can appear in multiple branches,
// we use a path-based key: parentKey/index:id
function makeOccurrenceKey(parentKey, index, nodeId) {
  return parentKey ? `${parentKey}/${index}:${nodeId}` : `root:${nodeId}`;
}

// ─── URL state sync ──────────────────────────────────────────────────
function readUrlState() {
  const params = new URLSearchParams(window.location.search);
  return {
    repo: params.get("repo") || "",
    maxDepth: params.get("maxDepth") || "",
    highRiskOnly: params.get("highRiskOnly") === "true",
    vulnerableOnly: params.get("vulnerableOnly") === "true",
    directOnly: params.get("directOnly") === "true",
    sortBy: params.get("sortBy") || "",
    truncateAfterChildren: params.get("truncateAfterChildren") || "",
    scopeFilter: params.get("scopeFilter") || "",
  };
}

function writeUrlState() {
  const params = new URLSearchParams();
  const repo = repoInput.value.trim();
  if (repo) params.set("repo", repo);
  if (maxDepthSelect.value) params.set("maxDepth", maxDepthSelect.value);
  if (highRiskOnly.checked) params.set("highRiskOnly", "true");
  if (vulnerableOnly.checked) params.set("vulnerableOnly", "true");
  if (directOnly.checked) params.set("directOnly", "true");
  if (sortBySelect.value) params.set("sortBy", sortBySelect.value);
  if (truncateSelect.value) params.set("truncateAfterChildren", truncateSelect.value);
  const scopeFilterEl = $("scopeFilter");
  if (scopeFilterEl && scopeFilterEl.value) params.set("scopeFilter", scopeFilterEl.value);
  const qs = params.toString();
  const url = window.location.pathname + (qs ? "?" + qs : "");
  window.history.replaceState(null, "", url);
}

function applyUrlState() {
  const s = readUrlState();
  if (s.repo) repoInput.value = s.repo;
  maxDepthSelect.value = s.maxDepth;
  highRiskOnly.checked = s.highRiskOnly;
  vulnerableOnly.checked = s.vulnerableOnly;
  directOnly.checked = s.directOnly;
  sortBySelect.value = s.sortBy;
  truncateSelect.value = s.truncateAfterChildren;
  const scopeFilterEl = $("scopeFilter");
  if (scopeFilterEl) scopeFilterEl.value = s.scopeFilter;
}

// ─── API client ──────────────────────────────────────────────────────
function buildApiUrl(repo) {
  const url = new URL(`${API_BASE}/repos/${encodeURIComponent(repo)}/dependency-tree`, window.location.origin);
  if (maxDepthSelect.value) url.searchParams.set("max_depth", maxDepthSelect.value);
  if (highRiskOnly.checked) url.searchParams.set("high_risk_only", "true");
  if (vulnerableOnly.checked) url.searchParams.set("vulnerable_only", "true");
  if (directOnly.checked) url.searchParams.set("direct_only", "true");
  if (sortBySelect.value) url.searchParams.set("sort_by", sortBySelect.value);
  if (truncateSelect.value) url.searchParams.set("truncate_after_children", truncateSelect.value);
  return url.toString();
}

async function fetchTree(repo) {
  const url = buildApiUrl(repo);
  const res = await fetch(url);
  const body = await res.json();
  if (!res.ok) {
    const msg = body?.error?.message || body?.detail?.message || JSON.stringify(body);
    const code = body?.error?.code || "";
    if (res.status === 404) throw new Error(`Repository not found: ${repo}`);
    if (res.status === 503) throw new Error(code === "TIMEOUT" ? "Tree construction timed out. Try limiting depth or adding truncation." : `Service unavailable: ${msg}`);
    throw new Error(`HTTP ${res.status}: ${msg}`);
  }
  return body;
}

// ─── Rendering: Scope Summary ────────────────────────────────────────

function scopeCard(label, count, isRuntime) {
  const borderStyle = isRuntime ? "border-top:2px solid var(--accent);" : "";
  return `<div class="stat-card ds-kpi" style="${borderStyle}">
    <div class="ds-kpi-value">${count}</div>
    <div class="ds-kpi-label">${label}</div>
  </div>`;
}

function renderScopeSummary(data) {
  if (!hasScopeFields(data)) return "";

  if (!hasMeaningfulScopeData(data)) {
    return `<div class="scope-summary-unavailable" style="margin-top:1rem;padding:0.75rem 1rem;background:var(--bg-overlay);border:1px solid var(--border);border-radius:8px;color:var(--text-secondary);font-size:0.85rem;">
      Scope data is limited or unavailable for this repository.
    </div>`;
  }

  const m = data.summary_metrics;
  const runtime = m.direct_runtime_dependency_count || 0;
  const devTest = (m.direct_dev_dependency_count || 0) + (m.direct_test_dependency_count || 0);
  const build = m.direct_build_dependency_count || 0;
  const optionalPeer = (m.direct_optional_dependency_count || 0) + (m.direct_peer_dependency_count || 0);
  const unknown = m.direct_unknown_dependency_count || 0;
  const transitiveRuntime = m.transitive_runtime_dependency_count || 0;

  const label = m.scope_classification_label || "";
  const note = m.scope_note || "";

  let html = `<div class="scope-summary" style="margin-top:1rem;">`;
  if (label) html += `<div style="font-size:0.85rem;color:var(--text-secondary);margin-bottom:0.5rem;">${label}</div>`;

  // Direct dependencies section
  html += `<div style="font-size:0.8rem;color:var(--text-tertiary);margin-bottom:0.25rem;">Direct Dependencies</div>`;
  html += `<div class="summary-grid" style="margin-bottom:0.75rem;">`;
  html += scopeCard("Runtime", runtime, true);
  html += scopeCard("Dev/Test", devTest, false);
  html += scopeCard("Build", build, false);
  html += scopeCard("Optional/Peer", optionalPeer, false);
  html += scopeCard("Unknown", unknown, false);
  html += `</div>`;

  // Transitive dependencies section
  html += `<div style="font-size:0.8rem;color:var(--text-tertiary);margin-bottom:0.25rem;">Transitive Dependencies</div>`;
  html += `<div class="summary-grid" style="margin-bottom:0.5rem;">`;
  html += scopeCard("Runtime", transitiveRuntime, true);
  html += `</div>`;

  // Helper text
  html += `<div style="font-size:0.75rem;color:var(--text-tertiary);margin-top:0.5rem;">`;
  html += `Dependency scope is classified from manifests and may not reflect actual runtime usage.`;
  html += `</div>`;
  html += `<div style="font-size:0.75rem;color:var(--text-tertiary);margin-top:0.25rem;">`;
  html += `Only runtime scope is currently tracked for transitive dependencies. Dev/test/build/optional/peer counts represent direct dependencies only.`;
  html += `</div>`;

  if (note) {
    html += `<div style="font-size:0.75rem;color:var(--text-tertiary);margin-top:0.25rem;">${note}</div>`;
  }

  html += `</div>`;
  return html;
}

// ─── Rendering: Summary ──────────────────────────────────────────────
function collectTreeStats(node, ecosystemCounts, riskCounts) {
  if (!node) return;
  if (node.node_type !== "repository") {
    if (node.ecosystem) {
      ecosystemCounts[node.ecosystem] = (ecosystemCounts[node.ecosystem] || 0) + 1;
    }
    if (node.risk_metadata && node.risk_metadata.risk_level) {
      const level = node.risk_metadata.risk_level.toLowerCase();
      if (riskCounts.hasOwnProperty(level)) {
        riskCounts[level]++;
      }
    }
  }
  if (node.children) {
    node.children.forEach(function(child) { collectTreeStats(child, ecosystemCounts, riskCounts); });
  }
}

function renderSummary(data) {
  const m = data.summary_metrics;
  const p = data.provenance;
  repoNameDisplay.textContent = data.repo;

  const stats = [
    { num: m.total_dependencies, label: "Total deps" },
    { num: m.direct_dependencies, label: "Direct" },
    { num: m.transitive_dependencies, label: "Transitive" },
    { num: m.high_risk_count, label: "High risk", color: m.high_risk_count > 0 ? "var(--red)" : null },
    { num: m.vulnerable_count, label: "Vulnerable", color: m.vulnerable_count > 0 ? "var(--orange)" : null },
    { num: m.max_depth, label: "Max depth" },
  ];

  summaryGrid.innerHTML = stats.map(s =>
    `<div class="stat-card ds-kpi">
      <div class="num ds-kpi-value" ${s.color ? `style="color:${s.color}"` : ""}>${s.num}</div>
      <div class="label ds-kpi-label">${s.label}</div>
    </div>`
  ).join("");

  // Append scope summary after the existing stat cards
  summaryGrid.innerHTML += renderScopeSummary(data);

  summarySection.style.display = "block";

  // Populate sidebar tree summary with interpretive statements + breakdowns
  const sidebarSummary = $("treeSummaryContent");
  if (sidebarSummary) {
    const lines = [];

    // Composition insight
    if (m.total_dependencies > 0 && m.transitive_dependencies > m.direct_dependencies) {
      const pct = Math.round((m.transitive_dependencies / m.total_dependencies) * 100);
      lines.push(`${pct}% of dependencies are transitive.`);
    } else if (m.total_dependencies > 0 && m.direct_dependencies >= m.transitive_dependencies) {
      lines.push("Most dependencies are direct.");
    }

    // Risk insight
    if (m.high_risk_count > 0) {
      lines.push(`<span style="color:var(--red);">${m.high_risk_count} high-risk</span> dependenc${m.high_risk_count === 1 ? "y" : "ies"} identified.`);
    } else {
      lines.push("No high-risk dependencies detected.");
    }

    // Vulnerability insight
    if (m.vulnerable_count > 0) {
      lines.push(`<span style="color:var(--orange);">${m.vulnerable_count} vulnerable</span> dependenc${m.vulnerable_count === 1 ? "y" : "ies"} found.`);
    } else {
      lines.push("No known vulnerabilities.");
    }

    // Depth insight
    if (m.max_depth <= 2) {
      lines.push("Dependency depth is shallow (max " + m.max_depth + ").");
    } else if (m.max_depth <= 5) {
      lines.push("Dependency depth is moderate (max " + m.max_depth + ").");
    } else {
      lines.push("Dependency tree is deep (max " + m.max_depth + ").");
    }

    let html = lines.map(l =>
      `<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;padding:2px 0;">${l}</div>`
    ).join("");

    // Ecosystem breakdown
    const ecosystemCounts = {};
    const riskCounts = { high: 0, medium: 0, low: 0 };
    collectTreeStats(data.tree, ecosystemCounts, riskCounts);

    const ecosystemEntries = Object.entries(ecosystemCounts).sort((a, b) => b[1] - a[1]);
    if (ecosystemEntries.length > 0) {
      html += `<div class="sidebar-ecosystem-breakdown" style="margin-top:var(--sp-8);">`;
      html += `<div style="font-size:11px;color:var(--text-tertiary);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:var(--sp-4);">Ecosystems</div>`;
      html += ecosystemEntries.map(([eco, count]) =>
        `<div style="font-size:12px;color:var(--text-secondary);padding:1px 0;display:flex;justify-content:space-between;"><span>${eco}</span><span style="font-family:var(--font-mono);color:var(--text-tertiary);">${count}</span></div>`
      ).join("");
      html += `</div>`;
    }

    // Risk level distribution
    const totalRisk = riskCounts.high + riskCounts.medium + riskCounts.low;
    if (totalRisk > 0) {
      html += `<div class="sidebar-risk-distribution" style="margin-top:var(--sp-8);">`;
      html += `<div style="font-size:11px;color:var(--text-tertiary);font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:var(--sp-4);">Risk Distribution</div>`;
      if (riskCounts.high > 0) html += `<div style="font-size:12px;padding:1px 0;display:flex;justify-content:space-between;"><span style="color:var(--status-high-text);">High</span><span style="font-family:var(--font-mono);color:var(--text-tertiary);">${riskCounts.high}</span></div>`;
      if (riskCounts.medium > 0) html += `<div style="font-size:12px;padding:1px 0;display:flex;justify-content:space-between;"><span style="color:var(--status-medium-text);">Medium</span><span style="font-family:var(--font-mono);color:var(--text-tertiary);">${riskCounts.medium}</span></div>`;
      if (riskCounts.low > 0) html += `<div style="font-size:12px;padding:1px 0;display:flex;justify-content:space-between;"><span style="color:var(--status-low-text);">Low</span><span style="font-family:var(--font-mono);color:var(--text-tertiary);">${riskCounts.low}</span></div>`;
      html += `</div>`;
    }

    sidebarSummary.innerHTML = html;
  }
}

// ─── Rendering: Provenance ───────────────────────────────────────────
function renderProvenance(data) {
  const p = data.provenance;
  if (!p) { provenanceBanner.style.display = "none"; return; }

  const messages = [];
  const badges = [];

  badges.push(`<span class="prov-badge">${p.data_source}</span>`);
  badges.push(`<span class="prov-badge">${p.data_completeness}</span>`);

  if (p.data_completeness === "partial") {
    if (p.nodes_with_missing_risk > 0)
      messages.push(`${p.nodes_with_missing_risk} node(s) missing risk metadata.`);
    if (p.nodes_with_errors > 0)
      messages.push(`${p.nodes_with_errors} node(s) failed to resolve.`);
  }
  if (p.data_source === "mixed")
    messages.push("Some nodes were fetched live.");
  if (p.data_source === "live")
    messages.push("All data was fetched live (not from database).");

  // Check for any truncated nodes in the tree
  if (hasAnyTruncation(data.tree))
    messages.push("Some branches are truncated based on current child limit.");

  if (messages.length === 0 && p.data_completeness === "full") {
    provenanceBanner.style.display = "none";
    return;
  }

  const isWarn = p.data_completeness === "partial" || p.nodes_with_errors > 0;
  provenanceBanner.className = `provenance-banner ${isWarn ? "warn" : "info"}`;
  provenanceBanner.innerHTML = badges.join("") + " " + messages.join(" ");
  provenanceBanner.style.display = "flex";
}

function hasAnyTruncation(node) {
  if (!node) return false;
  if (node.children_truncated) return true;
  return (node.children || []).some(c => hasAnyTruncation(c));
}

// ─── Rendering: Tree ─────────────────────────────────────────────────
function renderTree(data) {
  const tree = data.tree;
  if (!tree) return;

  // Zero dependencies
  if (tree.node_type === "repository" && (!tree.children || tree.children.length === 0)) {
    treeRoot.style.display = "none";
    emptyState.style.display = "flex";
    return;
  }

  emptyState.style.display = "none";
  treeRoot.style.display = "block";
  treeRoot.innerHTML = "";
  treeRoot.appendChild(buildNodeEl(tree, "", 0));
}

function buildNodeEl(node, parentKey, siblingIndex) {
  const key = makeOccurrenceKey(parentKey, siblingIndex, node.id);
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = expandedKeys.has(key);
  const isSelected = selectedKey === key;
  const isError = node.resolution_status === "error";
  const isRepo = node.node_type === "repository";

  const container = document.createElement("div");
  container.className = `tree-node depth-${node.depth}`;

  // Row
  const row = document.createElement("div");
  row.className = "tree-row" + (isSelected ? " selected" : "") + (isError ? " error-node" : "");
  row.setAttribute("role", "treeitem");
  if (hasChildren) row.setAttribute("aria-expanded", String(isExpanded));
  row.setAttribute("tabindex", "0");

  // Caret
  const caret = document.createElement("span");
  caret.className = "caret" + (hasChildren ? (isExpanded ? " expanded" : "") : " empty");
  caret.textContent = hasChildren ? "▶" : "";
  caret.addEventListener("click", (e) => { e.stopPropagation(); toggleExpand(key); });

  // Icon
  const icon = document.createElement("span");
  icon.className = "node-icon" + (isRepo ? " repo" : isError ? " error" : " pkg");
  icon.textContent = isRepo ? "◆" : isError ? "!" : "·";

  // Name
  const name = document.createElement("span");
  name.className = "node-name";
  name.textContent = node.name;
  name.title = node.name;

  // Version
  const version = document.createElement("span");
  version.className = "node-version";
  version.textContent = node.version && node.version !== "unknown" ? `@${node.version}` : "";

  // Badges
  const badges = document.createElement("span");
  badges.className = "node-badges";
  badges.innerHTML = buildBadges(node);

  row.appendChild(caret);
  row.appendChild(icon);
  row.appendChild(name);
  row.appendChild(version);
  row.appendChild(badges);

  // Click to select
  row.addEventListener("click", () => selectNode(key, node));
  row.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectNode(key, node); }
    if (e.key === "ArrowRight" && hasChildren && !isExpanded) { e.preventDefault(); toggleExpand(key); }
    if (e.key === "ArrowLeft" && hasChildren && isExpanded) { e.preventDefault(); toggleExpand(key); }
  });

  container.appendChild(row);

  // Children
  if (hasChildren && isExpanded) {
    node.children.forEach((child, i) => {
      container.appendChild(buildNodeEl(child, key, i));
    });
    // Truncation indicator
    if (node.children_truncated && node.child_count != null) {
      const trunc = document.createElement("div");
      trunc.className = "truncation-row";
      trunc.textContent = `Showing ${node.children.length} of ${node.child_count} children`;
      container.appendChild(trunc);
    }
  }

  return container;
}

function buildBadges(node) {
  const parts = [];
  if (node.node_type !== "repository" && node.dependency_type) {
    const cls = node.dependency_type === "direct" ? "direct" : "transitive";
    parts.push(`<span class="badge ${cls}">${node.dependency_type}</span>`);
  }
  if (node.ecosystem) {
    parts.push(`<span class="badge ecosystem">${node.ecosystem}</span>`);
  }
  const rm = node.risk_metadata;
  if (rm && rm.risk_level) {
    parts.push(`<span class="badge risk-${rm.risk_level}">${rm.risk_score != null ? Math.round(rm.risk_score) : "?"}</span>`);
  }
  if (rm && rm.vulnerability_count > 0) {
    parts.push(`<span class="badge vuln">${rm.vulnerability_count} CVE${rm.vulnerability_count > 1 ? "s" : ""}</span>`);
  }
  if (node.resolution_status === "error") {
    parts.push(`<span class="badge error-badge">error</span>`);
  }
  // Scope badge
  if (node.dependency_scope) {
    const scopeClass = SCOPE_BADGE_CLASSES[node.dependency_scope] || "scope-unknown";
    const tooltip = SCOPE_TOOLTIPS[node.dependency_scope] || "";
    parts.push(`<span class="badge ${scopeClass}" title="${tooltip}">${node.dependency_scope}</span>`);
  }
  return parts.join("");
}

// ─── Expand / Collapse ───────────────────────────────────────────────
function toggleExpand(key) {
  if (expandedKeys.has(key)) expandedKeys.delete(key);
  else expandedKeys.add(key);
  rerender();
}

function expandAll() {
  if (!currentResponse) return;
  walkTree(currentResponse.tree, "", 0, (node, key) => {
    if (node.children && node.children.length > 0) expandedKeys.add(key);
  });
  rerender();
}

function collapseAll() {
  expandedKeys.clear();
  // Keep root expanded
  if (currentResponse) {
    const rootKey = makeOccurrenceKey("", 0, currentResponse.tree.id);
    expandedKeys.add(rootKey);
  }
  rerender();
}

function setDefaultExpansion(tree) {
  expandedKeys.clear();
  const rootKey = makeOccurrenceKey("", 0, tree.id);
  expandedKeys.add(rootKey);
  // Expand depth-1 nodes
  if (tree.children) {
    tree.children.forEach((child, i) => {
      const childKey = makeOccurrenceKey(rootKey, i, child.id);
      if (child.children && child.children.length > 0) expandedKeys.add(childKey);
    });
  }
}

function walkTree(node, parentKey, siblingIndex, fn) {
  const key = makeOccurrenceKey(parentKey, siblingIndex, node.id);
  fn(node, key);
  if (node.children) {
    node.children.forEach((child, i) => walkTree(child, key, i, fn));
  }
}

// ─── Node selection & detail panel ───────────────────────────────────
function selectNode(key, node) {
  selectedKey = key;
  renderDetailPanel(node);
  rerender();
}

function renderDetailPanel(node) {
  if (!node) {
    detailContent.innerHTML = `<div class="state-msg" style="padding:30px 10px;">
      <div class="msg">Click a node to inspect its metadata</div>
    </div>`;
    return;
  }

  const rm = node.risk_metadata;
  let html = "";

  // Identity
  html += `<div class="detail-section"><h4>Identity</h4>`;
  html += detailItem("Name", node.name);
  if (node.version) html += detailItem("Version", node.version);
  if (node.ecosystem) html += detailItem("Ecosystem", node.ecosystem);
  if (node.dependency_type) html += detailItem("Type", node.dependency_type);
  html += detailItem("Depth", node.depth);
  html += detailItem("ID", node.id);
  html += `</div>`;

  // Risk
  if (rm) {
    html += `<div class="detail-section"><h4>Risk</h4>`;
    if (rm.risk_score != null) {
      const color = riskColor(rm.risk_score);
      html += detailItem("Risk score", `${rm.risk_score.toFixed(1)} / 100`);
      html += `<div class="risk-bar-container"><div class="risk-bar"><div class="risk-bar-fill" style="width:${rm.risk_score}%; background:${color};"></div></div><div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-tertiary);margin-top:3px;"><span>LOW</span><span style="color:${color};font-weight:700;">${rm.risk_score.toFixed(0)}%</span><span>HIGH</span></div></div>`;
    }
    if (rm.risk_level) html += detailItem("Risk level", rm.risk_level);
    html += detailItem("Vulnerabilities", rm.vulnerability_count != null ? rm.vulnerability_count : "—");
    if (rm.release_recency_days != null) html += detailItem("Last release", `${rm.release_recency_days} days ago`);
    if (rm.maintainer_count != null) html += detailItem("Maintainers", rm.maintainer_count);
    if (rm.score_source) html += detailItem("Score source", rm.score_source);
    if (rm.score_completeness) html += detailItem("Completeness", rm.score_completeness);
    html += `</div>`;
  } else if (node.node_type !== "repository") {
    html += `<div class="detail-section"><h4>Risk</h4>`;
    html += `<div style="font-size:13px; color:var(--muted2); padding:8px 0;">No risk metadata available</div>`;
    html += `</div>`;
  }

  // Status
  if (node.resolution_status === "error") {
    html += `<div class="detail-section"><h4>Status</h4>`;
    html += detailItem("Resolution", "Error");
    if (node.error_reason) html += detailItem("Reason", node.error_reason);
    html += `</div>`;
  }

  // Children info
  if (node.children) {
    html += `<div class="detail-section"><h4>Children</h4>`;
    html += detailItem("Visible children", node.children.length);
    if (node.children_truncated && node.child_count != null)
      html += detailItem("Total children", `${node.child_count} (truncated)`);
    html += `</div>`;
  }

  // Placeholder for future risk reasons
  html += `<div class="detail-section" style="opacity:.4;"><h4>Risk Reasons</h4>
    <div style="font-size:12px; color:var(--muted2); padding:8px 0;">Coming soon</div></div>`;

  detailContent.innerHTML = html;
}

function detailItem(label, value) {
  return `<div class="detail-item"><div class="dl">${label}</div><div class="dv">${value}</div></div>`;
}

function riskColor(score) {
  if (score == null) return "var(--muted2)";
  if (score > 70) return "var(--red)";
  if (score > 30) return "var(--yellow)";
  return "var(--green)";
}

// ─── Page states ─────────────────────────────────────────────────────
function showState(state) {
  initialState.style.display = state === "initial" ? "flex" : "none";
  loadingState.style.display = state === "loading" ? "flex" : "none";
  emptyState.style.display = state === "empty" ? "flex" : "none";
  treeRoot.style.display = state === "tree" ? "block" : "none";
  const scopeEmptyState = $("scopeFilterEmptyState");
  if (scopeEmptyState) scopeEmptyState.style.display = "none";
}

function showError(msg) {
  errBox.style.display = msg ? "block" : "none";
  errBox.textContent = msg || "";
}

// ─── Rerender (UI state only, no fetch) ──────────────────────────────
function rerender() {
  if (!currentResponse) return;
  const scopeFilterEl = $("scopeFilter");
  const scopeVal = scopeFilterEl ? scopeFilterEl.value : "";
  const scopeEmptyState = $("scopeFilterEmptyState");

  if (scopeVal) {
    const filteredTree = filterTreeByScope(currentResponse.tree, scopeVal);
    const hasChildren = filteredTree.children && filteredTree.children.length > 0;
    if (!hasChildren && filteredTree.node_type === "repository") {
      // No nodes match — show scope empty state
      treeRoot.style.display = "none";
      emptyState.style.display = "none";
      if (scopeEmptyState) scopeEmptyState.style.display = "flex";
    } else {
      if (scopeEmptyState) scopeEmptyState.style.display = "none";
      renderTree({ ...currentResponse, tree: filteredTree });
    }
  } else {
    if (scopeEmptyState) scopeEmptyState.style.display = "none";
    renderTree(currentResponse);
  }
  writeUrlState();
}

// ─── Scope Insight Card (Phase 4) ────────────────────────────────────

/**
 * Render the Scope Insight Card from /api/insights/{owner}/{repo} response.
 * Shows score, label, runtime exposure, vulnerable runtime count, top drivers, and notes.
 * Distinguishes between score=0.0 (valid low-risk) and missing data (unavailable).
 */
function renderScopeInsightCard(insightData) {
  const container = $("scopeInsightCard");
  const panel = $("scopeInsightPanel");
  if (!container || !panel) return;

  const swr = insightData?.scope_weighted_risk;

  if (!swr || swr.scope_weighted_dependency_risk == null) {
    // Unavailable state (Req 9.7, 9.9)
    container.innerHTML = '<div style="font-size:12px;color:var(--text-tertiary);">Scope-weighted risk is not available for this repository.</div>';
    panel.style.display = "";
    return;
  }

  // Score = 0.0 with valid data → show "low" label (Req 9.9)
  const score = swr.scope_weighted_dependency_risk;
  const label = swr.risk_label;
  const color = label === "high" ? "var(--status-high-text)" : label === "medium" ? "var(--status-medium-text)" : "var(--status-low-text)";

  let html = '<div style="display:flex;align-items:baseline;gap:var(--sp-8);margin-bottom:var(--sp-8);">';
  html += '<span style="font-size:18px;font-weight:700;font-family:var(--font-mono);color:' + color + ';">' + (score * 100).toFixed(1) + '%</span>';
  html += '<span class="badge" style="color:' + color + ';">' + label + '</span>';
  html += '</div>';

  // Runtime exposure (Req 9.3)
  const metrics = currentResponse?.summary_metrics;
  if (metrics?.runtime_dependency_exposure != null) {
    html += '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:var(--sp-4);">Runtime exposure: ' + (metrics.runtime_dependency_exposure * 100).toFixed(0) + '%</div>';
  }

  // Vulnerable runtime count (Req 9.4)
  if (metrics?.vulnerable_runtime_dependency_count != null) {
    html += '<div style="font-size:12px;color:var(--text-secondary);margin-bottom:var(--sp-4);">Vulnerable runtime deps: ' + metrics.vulnerable_runtime_dependency_count + '</div>';
  }

  // Top drivers (Req 9.5)
  if (swr.top_drivers?.length > 0) {
    html += '<div style="margin-top:var(--sp-8);margin-bottom:var(--sp-4);font-size:11px;font-weight:700;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.5px;">Top Risk Drivers</div>';
    for (const d of swr.top_drivers) {
      const badgeClass = SCOPE_BADGE_CLASSES[d.scope] || "scope-unknown";
      html += '<div style="display:flex;align-items:center;gap:var(--sp-4);font-size:12px;padding:var(--sp-4) 0;border-bottom:1px solid var(--border-subtle);">';
      html += '<span style="font-weight:600;color:var(--text-primary);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + d.package + '</span>';
      html += '<span class="badge ' + badgeClass + '" style="font-size:9px;">' + d.scope + '</span>';
      html += '<span style="color:var(--text-tertiary);flex-shrink:0;">' + (d.contribution * 100).toFixed(1) + '%</span>';
      html += '</div>';
    }
  }

  // Notes (Req 9.6)
  if (swr.scope_note) {
    html += '<div style="font-size:11px;color:var(--text-tertiary);margin-top:var(--sp-8);line-height:1.4;">' + swr.scope_note + '</div>';
  }
  if (swr.confidence_note) {
    html += '<div style="font-size:11px;color:var(--text-tertiary);margin-top:var(--sp-4);line-height:1.4;">' + swr.confidence_note + '</div>';
  }

  // Interpretation based on risk label
  const interpretations = {
    low: "Low overall dependency risk, but runtime-scoped packages still deserve review.",
    medium: "Moderate dependency risk — prioritize runtime-scoped packages with vulnerabilities.",
    high: "Significant dependency risk — immediate attention recommended for runtime dependencies."
  };
  if (interpretations[label]) {
    html += '<div style="font-size:11px;color:var(--text-primary);margin-top:var(--sp-8);line-height:1.4;font-weight:600;">' + interpretations[label] + '</div>';
  }

  // Footnote
  html += '<div style="font-size:10px;color:var(--text-tertiary);margin-top:var(--sp-8);line-height:1.3;border-top:1px solid var(--border-subtle);padding-top:var(--sp-4);">Scope-weighted risk is separate from repository maintenance risk.</div>';

  container.innerHTML = html;
  panel.style.display = "";
}

// ─── Phase 5: Actionable Insight Panels ──────────────────────────────

function renderFixFirst(insightData) {
    const recs = insightData?.priority_recommendations;
    const container = document.getElementById("fixFirstContent");
    const panel = document.getElementById("fixFirstPanel");
    if (!container || !panel) return;

    if (!recs || recs.length === 0) {
        container.innerHTML = '<div style="font-size:12px;color:var(--text-tertiary);">No high-priority issues found.</div>';
        panel.style.display = "block";
        return;
    }

    let html = '<div class="fix-first-list">';
    recs.forEach((rec, i) => {
        const scopeClass = SCOPE_BADGE_CLASSES[rec.dependency_scope] || "scope-unknown";
        const pct = (rec.priority_score * 100).toFixed(1);
        const barWidth = Math.max(4, rec.priority_score * 100);
        const isLast = i === recs.length - 1;
        html += '<div style="padding:var(--sp-8) 0;' + (isLast ? '' : 'border-bottom:1px solid var(--border-subtle);') + 'font-size:12px;">';
        // Header row: rank, name, scope badge
        html += '<div style="display:flex;align-items:center;gap:var(--sp-4);margin-bottom:var(--sp-4);">';
        html += '<span style="font-weight:700;color:var(--text-tertiary);min-width:16px;font-size:11px;">' + (i + 1) + '</span>';
        html += '<span style="font-weight:600;color:var(--text-primary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + rec.package_name + '</span>';
        html += '<span class="badge ' + scopeClass + '" style="font-size:9px;">' + rec.dependency_scope + '</span>';
        html += '</div>';
        // Action text — prominent
        html += '<div style="color:var(--accent);padding-left:20px;font-weight:700;font-size:12px;margin-bottom:var(--sp-4);">' + rec.action + '</div>';
        // Reason — supporting context
        html += '<div style="color:var(--text-tertiary);padding-left:20px;font-size:11px;line-height:1.4;margin-bottom:var(--sp-4);">' + rec.reason + '</div>';
        // Priority score as mini progress bar
        html += '<div style="padding-left:20px;display:flex;align-items:center;gap:var(--sp-8);">';
        html += '<div style="flex:1;height:4px;background:var(--bg-overlay);border-radius:2px;overflow:hidden;">';
        html += '<div style="width:' + barWidth + '%;height:100%;background:var(--accent);border-radius:2px;"></div>';
        html += '</div>';
        html += '<span style="font-size:10px;color:var(--text-tertiary);font-family:var(--font-mono);flex-shrink:0;">' + pct + '%</span>';
        html += '</div>';
        html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
    panel.style.display = "block";
}

function renderRiskBreakdown(insightData) {
    const clusters = insightData?.risk_clusters;
    const container = document.getElementById("riskBreakdownContent");
    const panel = document.getElementById("riskBreakdownPanel");
    if (!container || !panel) return;
    if (!clusters || clusters.length === 0) return;

    let html = '';
    clusters.forEach(cluster => {
        const isMuted = cluster.count === 0;
        const pct = (cluster.risk_contribution * 100).toFixed(1);
        html += '<div style="padding:var(--sp-8);margin-bottom:var(--sp-4);border:1px solid var(--border-subtle);border-radius:6px;' + (isMuted ? 'opacity:0.45;' : '') + '">';
        html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--sp-4);">';
        html += '<span style="font-size:12px;font-weight:700;color:var(--text-primary);">' + cluster.cluster_name + '</span>';
        if (!isMuted) {
            html += '<span style="font-size:11px;color:var(--text-tertiary);font-family:var(--font-mono);">' + cluster.count + ' deps · ' + pct + '%</span>';
        }
        html += '</div>';
        if (isMuted) {
            html += '<div style="font-size:11px;color:var(--text-tertiary);font-style:italic;">No dependencies in this cluster.</div>';
        } else {
            html += '<div style="font-size:11px;color:var(--text-secondary);margin-bottom:var(--sp-4);line-height:1.4;">' + cluster.summary + '</div>';
            // Risk contribution mini bar
            html += '<div style="height:3px;background:var(--bg-overlay);border-radius:2px;overflow:hidden;margin-bottom:var(--sp-4);">';
            html += '<div style="width:' + Math.max(2, cluster.risk_contribution * 100) + '%;height:100%;background:var(--accent);border-radius:2px;"></div>';
            html += '</div>';
            if (cluster.example_packages && cluster.example_packages.length > 0) {
                html += '<div style="font-size:10px;color:var(--text-tertiary);">e.g. ' + cluster.example_packages.join(', ') + '</div>';
            }
        }
        html += '</div>';
    });
    container.innerHTML = html;
    panel.style.display = "block";
}

function renderNarrative(insightData) {
    const narrative = insightData?.risk_narrative;
    const container = document.getElementById("narrativeContent");
    const panel = document.getElementById("narrativePanel");
    if (!container || !panel) return;
    if (!narrative) return;

    let html = '';
    html += '<div style="font-size:13px;font-weight:600;color:var(--text-primary);margin-bottom:var(--sp-8);line-height:1.5;">' + narrative.summary + '</div>';

    if (narrative.key_findings && narrative.key_findings.length > 0) {
        html += '<div style="font-size:10px;font-weight:700;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.5px;margin-bottom:var(--sp-4);">Key Insights</div>';
        html += '<ul style="margin:0 0 var(--sp-8) 0;padding-left:16px;">';
        narrative.key_findings.forEach(finding => {
            html += '<li style="font-size:12px;color:var(--text-secondary);line-height:1.5;margin-bottom:var(--sp-4);">' + finding + '</li>';
        });
        html += '</ul>';
    }

    if (narrative.recommendation) {
        html += '<div style="font-size:12px;font-weight:700;color:var(--accent);padding:var(--sp-8) var(--sp-12);background:var(--accent-muted);border-radius:6px;border-left:3px solid var(--accent);line-height:1.5;">' + narrative.recommendation + '</div>';
    }

    container.innerHTML = html;
    panel.style.display = "block";
}

function renderConfidence(insightData) {
    const confidence = insightData?.overall_confidence;
    const container = document.getElementById("confidenceContent");
    const panel = document.getElementById("confidencePanel");
    if (!container || !panel) return;
    if (!confidence) return;

    const colorMap = { high: "var(--green)", medium: "var(--yellow)", low: "var(--red)" };
    const color = colorMap[confidence.label] || "var(--text-tertiary)";
    const pct = (confidence.score * 100).toFixed(1);

    let html = '';
    html += '<div style="display:flex;align-items:center;gap:var(--sp-8);margin-bottom:var(--sp-4);">';
    html += '<span style="font-size:18px;font-weight:700;font-family:var(--font-mono);color:' + color + ';">' + pct + '%</span>';
    html += '<span class="badge" style="color:' + color + ';border-color:' + color + ';">' + confidence.label + '</span>';
    html += '</div>';
    html += '<div style="font-size:10px;color:var(--text-tertiary);margin-bottom:var(--sp-8);line-height:1.4;">Confidence reflects data quality and scope coverage, not risk level.</div>';
    html += '<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;">' + confidence.explanation + '</div>';

    container.innerHTML = html;
    panel.style.display = "block";
}

// ─── Main load flow ──────────────────────────────────────────────────
async function loadTree(isRefetch) {
  const repo = repoInput.value.trim();
  if (!repo) return;

  showError("");
  writeUrlState();

  if (isRefetch && currentResponse) {
    isRefetching = true;
    refetchIndicator.classList.add("active");
  } else {
    showState("loading");
    summarySection.style.display = "none";
    filterSection.style.display = "none";
    provenanceBanner.style.display = "none";
  }

  loadBtn.disabled = true;
  loadBtn.textContent = "Loading…";

  try {
    const data = await fetchTree(repo);
    currentResponse = Object.freeze(data); // immutable
    selectedKey = null;

    if (!isRefetch) setDefaultExpansion(data.tree);

    renderSummary(data);
    renderProvenance(data);
    filterSection.style.display = "block";

    // Show/hide scope filter based on meaningful scope data
    const scopeFilterGroup = $("scopeFilterGroup");
    const scopeLegend = $("scopeLegend");
    if (scopeFilterGroup) {
      const showScope = hasMeaningfulScopeData(data);
      scopeFilterGroup.style.display = showScope ? "" : "none";
      if (scopeLegend) scopeLegend.style.display = showScope ? "" : "none";
    }

    if (data.tree.node_type === "repository" && (!data.tree.children || data.tree.children.length === 0)) {
      showState("empty");
    } else {
      showState("tree");
    }
    rerender();
    renderDetailPanel(null);

    // Fire-and-forget: fetch scope insight data (Phase 4)
    if (repo.includes("/")) {
      const [owner, repoName] = repo.split("/", 2);
      fetch(API_BASE + "/api/insights/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repoName))
        .then(r => r.ok ? r.json() : null)
        .then(d => {
            if (d) {
                renderScopeInsightCard(d);
                renderFixFirst(d);
                renderNarrative(d);
                renderRiskBreakdown(d);
                renderConfidence(d);
            }
        })
        .catch(() => {});
    }
  } catch (e) {
    if (!isRefetch) showState("initial");
    showError(e.message);
  } finally {
    loadBtn.disabled = false;
    loadBtn.textContent = "Load Tree";
    isRefetching = false;
    refetchIndicator.classList.remove("active");
  }
}

function refetch() {
  loadTree(true);
}

// ─── Reset ───────────────────────────────────────────────────────────
function resetFilters() {
  maxDepthSelect.value = "";
  highRiskOnly.checked = false;
  vulnerableOnly.checked = false;
  directOnly.checked = false;
  sortBySelect.value = "";
  truncateSelect.value = "";
  const scopeFilterEl = $("scopeFilter");
  if (scopeFilterEl) scopeFilterEl.value = "";
  refetch();
}

// ─── Event listeners ─────────────────────────────────────────────────
loadBtn.addEventListener("click", () => loadTree(false));
repoInput.addEventListener("keydown", (e) => { if (e.key === "Enter") loadTree(false); });

// Controls trigger refetch
[maxDepthSelect, sortBySelect, truncateSelect].forEach(el =>
  el.addEventListener("change", refetch)
);
[highRiskOnly, vulnerableOnly, directOnly].forEach(el =>
  el.addEventListener("change", refetch)
);

$("expandAllBtn").addEventListener("click", expandAll);
$("collapseAllBtn").addEventListener("click", collapseAll);
$("resetBtn").addEventListener("click", resetFilters);

// Scope filter triggers client-side re-render (no refetch)
const scopeFilterEl = $("scopeFilter");
if (scopeFilterEl) scopeFilterEl.addEventListener("change", rerender);

// ─── Init from URL ───────────────────────────────────────────────────
applyUrlState();
if (repoInput.value.trim()) loadTree(false);


// ── Scope-aware mode ──
(function() {
  var scopeId = parseScopeParam(window.location.search);
  if (scopeId) {
    // Hide single-repo input controls
    var topbar = document.querySelector('.topbar');
    if (topbar) topbar.style.display = 'none';
    
    // Fetch scope data
    var apiBase = window.DS_API_BASE || '';
    fetch(apiBase + '/api/scope/' + encodeURIComponent(scopeId))
      .then(function(res) {
        if (!res.ok) throw new Error('Failed to load scope: ' + res.status);
        return res.json();
      })
      .then(function(data) {
        document.title = (data.name || 'Scope') + ' — Dependency Tree';
        
        // Build tree from merged graph data
        // Adapt the scope graph data to the tree format expected by the existing rendering
        var graph = data.graph || { nodes: [], edges: [] };
        renderScopeTree(graph, data.name || 'Analysis Scope');
      })
      .catch(function(err) {
        // Show error in the tree container
        var container = document.getElementById('tree-container') || document.getElementById('treeContainer');
        if (container) {
          container.innerHTML = '<div style="text-align:center;padding:32px;color:var(--text-secondary);">' + err.message + '</div>';
        }
      });
  }
})();

function renderScopeTree(graph, scopeName) {
  // Build a simple tree view from the merged graph nodes
  var container = document.getElementById('tree-container') || document.getElementById('treeContainer');
  if (!container) return;
  
  container.innerHTML = '';
  
  var title = document.createElement('h3');
  title.style.cssText = 'font-size:16px;font-weight:700;margin-bottom:16px;color:var(--text-primary);';
  title.textContent = scopeName + ' — Merged Dependencies';
  container.appendChild(title);
  
  var nodes = graph.nodes || [];
  // Group nodes by type
  var repos = nodes.filter(function(n) { return n.type === 'repo'; });
  var packages = nodes.filter(function(n) { return n.type === 'package' || n.type === 'dependency'; });
  
  if (repos.length > 0) {
    var repoHeader = document.createElement('div');
    repoHeader.style.cssText = 'font-size:12px;font-weight:700;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.5px;margin:12px 0 8px;';
    repoHeader.textContent = 'Repositories (' + repos.length + ')';
    container.appendChild(repoHeader);
    repos.forEach(function(n) {
      var el = document.createElement('div');
      el.style.cssText = 'padding:6px 12px;font-size:13px;color:var(--text-primary);border-left:2px solid var(--accent);margin-bottom:4px;';
      el.textContent = n.label || n.id;
      container.appendChild(el);
    });
  }
  
  if (packages.length > 0) {
    var pkgHeader = document.createElement('div');
    pkgHeader.style.cssText = 'font-size:12px;font-weight:700;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.5px;margin:12px 0 8px;';
    pkgHeader.textContent = 'Dependencies (' + packages.length + ')';
    container.appendChild(pkgHeader);
    packages.forEach(function(n) {
      var el = document.createElement('div');
      el.style.cssText = 'padding:6px 12px;font-size:13px;color:var(--text-secondary);border-left:2px solid var(--border);margin-bottom:4px;';
      var usedBy = (n.source_repos || []).length;
      el.textContent = (n.label || n.id) + (usedBy > 0 ? ' (used by ' + usedBy + ' repos)' : '');
      container.appendChild(el);
    });
  }
  
  if (nodes.length === 0) {
    container.innerHTML = '<div style="text-align:center;padding:32px;color:var(--text-tertiary);">No dependency data available for this scope.</div>';
  }
}
