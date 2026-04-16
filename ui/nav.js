/**
 * nav.js — Shared navigation module for Deep Signal UI.
 *
 * Loaded by all HTML pages via <script src="/ui/nav.js"></script>.
 * Provides navigation rendering, repo parameter handling, scope_id
 * propagation, and cross-page links.
 *
 * Public API (global functions):
 *   parseRepoParam(searchString)       → string|null
 *   parseScopeParam(searchString)      → string|null
 *   getRepoFromUrl()                   → string|null
 *   buildPageUrl(page, repo, scopeId)  → string
 *   getCurrentPageId()                 → string
 *   renderNav(currentPageId, repo, scopeId) → void
 *   getCrossLinks(currentPageId, repo, scopeId) → Array<{label, href, targetPageId}>
 *   renderCrossLinks(containerId, repo, scopeId) → void
 */

// ── Page definitions ──

var NAV_PAGES = [
  { pageId: "index", label: "Home", file: "index.html" },
  { pageId: "overview", label: "Overview", file: "overview.html" },
  { pageId: "insights", label: "Insights", file: "insights.html" },
  { pageId: "graph", label: "Graph", file: "graph.html" },
  { pageId: "dependency-tree", label: "Dependency Tree", file: "dependency-tree.html" }
];

var CROSS_LINK_TARGETS = [
  { targetPageId: "overview", label: "Open in Overview", file: "overview.html" },
  { targetPageId: "insights", label: "Open in Insights", file: "insights.html" },
  { targetPageId: "graph", label: "Open in Graph", file: "graph.html" },
  { targetPageId: "dependency-tree", label: "Open in Dependency Tree", file: "dependency-tree.html" }
];

// ── Helper functions ──

/**
 * parseRepoParam(searchString) → string|null
 * Parse ?repo= from a query string, validate owner/name format.
 * Returns the decoded repo string or null if missing/invalid.
 */
function parseRepoParam(searchString) {
  var params = new URLSearchParams(searchString);
  var raw = params.get("repo");
  if (!raw) return null;
  var decoded = decodeURIComponent(raw);
  if (!decoded || !decoded.trim()) return null;
  decoded = decoded.trim();
  var slashIndex = decoded.indexOf("/");
  if (slashIndex === -1 || slashIndex === 0 || slashIndex === decoded.length - 1 || decoded.indexOf("/", slashIndex + 1) !== -1) return null;
  return decoded;
}

/**
 * getRepoFromUrl() → string|null
 * Reads ?repo= from the current page URL.
 */
function getRepoFromUrl() {
  return parseRepoParam(window.location.search);
}

/**
 * parseScopeParam(searchString) → string|null
 * Parse ?scope_id= from a query string.
 * Returns the decoded scope_id string or null if missing.
 */
function parseScopeParam(searchString) {
  var params = new URLSearchParams(searchString);
  var raw = params.get("scope_id");
  if (!raw) return null;
  var decoded = decodeURIComponent(raw);
  if (!decoded || !decoded.trim()) return null;
  return decoded.trim();
}

/**
 * buildPageUrl(page, repo, scopeId) → string
 * Build a URL for a target page, optionally appending ?repo= and/or ?scope_id= params.
 * If both repo and scopeId are provided, uses ?repo=...&scope_id=...
 * Backward compatible: existing calls with just (page, repo) still work.
 */
function buildPageUrl(page, repo, scopeId) {
  var params = [];
  if (repo) params.push("repo=" + encodeURIComponent(repo));
  if (scopeId) params.push("scope_id=" + encodeURIComponent(scopeId));
  if (params.length > 0) return page + "?" + params.join("&");
  return page;
}

/**
 * getCurrentPageId() → string
 * Return the current page identifier based on pathname.
 * One of: "index", "overview", "insights", "graph", "dependency-tree"
 */
function getCurrentPageId() {
  var path = window.location.pathname;
  if (path.indexOf("overview") !== -1) return "overview";
  if (path.indexOf("insights") !== -1) return "insights";
  if (path.indexOf("graph") !== -1) return "graph";
  if (path.indexOf("dependency-tree") !== -1) return "dependency-tree";
  return "index";
}

// ── Navigation rendering ──

/**
 * renderNav(currentPageId, repo, scopeId) → void
 * Creates a <nav> element with class ds-nav and inserts it as the first
 * child of .wrap. Active page link gets .active class and aria-current="page".
 * All links propagate the repo param when present.
 * When scopeId is present, propagates it to Overview, Graph, and Tree links.
 * Idempotent: removes any existing nav.ds-nav before inserting.
 */
function renderNav(currentPageId, repo, scopeId) {
  var existing = document.querySelector("nav.ds-nav");
  if (existing) existing.remove();

  var nav = document.createElement("nav");
  nav.className = "ds-nav";
  nav.setAttribute("aria-label", "Main navigation");

  var brand = document.createElement("span");
  brand.className = "ds-nav-brand";
  brand.textContent = "Deep Signal";
  nav.appendChild(brand);

  var linksDiv = document.createElement("div");
  linksDiv.className = "ds-nav-links";

  // Pages that should receive scope_id when present
  var scopePages = { "overview": true, "graph": true, "dependency-tree": true };

  for (var i = 0; i < NAV_PAGES.length; i++) {
    var page = NAV_PAGES[i];
    var a = document.createElement("a");
    var linkScopeId = (scopeId && scopePages[page.pageId]) ? scopeId : null;
    a.href = buildPageUrl(page.file, repo, linkScopeId);
    a.className = "ds-nav-link";
    a.textContent = page.label;
    if (page.pageId === currentPageId) {
      a.classList.add("active");
      a.setAttribute("aria-current", "page");
    }
    linksDiv.appendChild(a);
  }

  nav.appendChild(linksDiv);

  var wrap = document.querySelector(".wrap");
  if (wrap) {
    wrap.insertBefore(nav, wrap.firstChild);
  }
}

// ── Cross-page links ──

/**
 * getCrossLinks(currentPageId, repo, scopeId) → Array<{label, href, targetPageId}>
 * Returns link objects for cross-page navigation, excluding the current page.
 * Returns empty array when both repo and scopeId are null/empty.
 * When scopeId is present, propagates it to scope-aware pages.
 */
function getCrossLinks(currentPageId, repo, scopeId) {
  if (!repo && !scopeId) return [];

  // Pages that should receive scope_id when present
  var scopePages = { "overview": true, "graph": true, "dependency-tree": true };

  var links = [];
  for (var i = 0; i < CROSS_LINK_TARGETS.length; i++) {
    var target = CROSS_LINK_TARGETS[i];
    if (target.targetPageId === currentPageId) continue;
    var linkScopeId = (scopeId && scopePages[target.targetPageId]) ? scopeId : null;
    links.push({
      label: target.label,
      href: buildPageUrl(target.file, repo, linkScopeId),
      targetPageId: target.targetPageId
    });
  }
  return links;
}

/**
 * renderCrossLinks(containerId, repo, scopeId) → void
 * Renders cross-page link buttons into a container element.
 * Uses ds-btn-subtle class for styling.
 */
function renderCrossLinks(containerId, repo, scopeId) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var links = getCrossLinks(getCurrentPageId(), repo, scopeId);
  container.innerHTML = "";
  if (links.length === 0) {
    container.style.display = "none";
    return;
  }
  for (var i = 0; i < links.length; i++) {
    var a = document.createElement("a");
    a.href = links[i].href;
    a.className = "ds-btn-subtle";
    a.textContent = links[i].label;
    container.appendChild(a);
  }
  container.style.display = "flex";
}
