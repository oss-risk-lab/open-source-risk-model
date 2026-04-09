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

// ─── Rendering: Summary ──────────────────────────────────────────────
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
    `<div class="stat-card">
      <div class="num" ${s.color ? `style="color:${s.color}"` : ""}>${s.num}</div>
      <div class="label">${s.label}</div>
    </div>`
  ).join("");

  summarySection.style.display = "block";

  // Populate sidebar tree summary with interpretive statements
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

    sidebarSummary.innerHTML = lines.map(l =>
      `<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;padding:2px 0;">${l}</div>`
    ).join("");
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
  icon.textContent = isRepo ? "📦" : isError ? "⚠" : "📄";

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
      <div class="icon" style="font-size:28px;">👆</div>
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
      html += `<div class="risk-bar-container"><div class="risk-bar"><div class="risk-bar-fill" style="width:${rm.risk_score}%; background:${color};"></div></div></div>`;
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
}

function showError(msg) {
  errBox.style.display = msg ? "block" : "none";
  errBox.textContent = msg || "";
}

// ─── Rerender (UI state only, no fetch) ──────────────────────────────
function rerender() {
  if (!currentResponse) return;
  renderTree(currentResponse);
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

    if (data.tree.node_type === "repository" && (!data.tree.children || data.tree.children.length === 0)) {
      showState("empty");
    } else {
      showState("tree");
    }
    renderTree(data);
    renderDetailPanel(null);
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

// ─── Init from URL ───────────────────────────────────────────────────
applyUrlState();
if (repoInput.value.trim()) loadTree(false);
