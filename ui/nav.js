/**
 * nav.js — Shared navigation module for Deep Signal UI.
 *
 * Loaded by all four HTML pages via <script src="/ui/nav.js"></script>.
 * Provides navigation rendering, repo parameter handling, and cross-page links.
 *
 * Public API (global functions):
 *   parseRepoParam(searchString) → string|null
 *   getRepoFromUrl()             → string|null
 *   buildPageUrl(page, repo)     → string
 *   getCurrentPageId()           → string
 *   renderNav(currentPageId, repo) → void
 *   getCrossLinks(currentPageId, repo) → Array<{label, href, targetPageId}>
 *   renderCrossLinks(containerId, repo) → void
 */

// ── Page definitions ──

var NAV_PAGES = [
  { pageId: "index", label: "Home", file: "index.html" },
  { pageId: "insights", label: "Insights", file: "insights.html" },
  { pageId: "graph", label: "Graph", file: "graph.html" },
  { pageId: "dependency-tree", label: "Dependency Tree", file: "dependency-tree.html" }
];

var CROSS_LINK_TARGETS = [
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
 * buildPageUrl(page, repo) → string
 * Build a URL for a target page, optionally appending ?repo= param.
 */
function buildPageUrl(page, repo) {
  if (repo) return page + "?repo=" + encodeURIComponent(repo);
  return page;
}

/**
 * getCurrentPageId() → string
 * Return the current page identifier based on pathname.
 * One of: "index", "insights", "graph", "dependency-tree"
 */
function getCurrentPageId() {
  var path = window.location.pathname;
  if (path.indexOf("insights") !== -1) return "insights";
  if (path.indexOf("graph") !== -1) return "graph";
  if (path.indexOf("dependency-tree") !== -1) return "dependency-tree";
  return "index";
}

// ── Navigation rendering ──

/**
 * renderNav(currentPageId, repo) → void
 * Creates a <nav> element with class ds-nav and inserts it as the first
 * child of .wrap. Active page link gets .active class and aria-current="page".
 * All links propagate the repo param when present.
 * Idempotent: removes any existing nav.ds-nav before inserting.
 */
function renderNav(currentPageId, repo) {
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

  for (var i = 0; i < NAV_PAGES.length; i++) {
    var page = NAV_PAGES[i];
    var a = document.createElement("a");
    a.href = buildPageUrl(page.file, repo);
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
 * getCrossLinks(currentPageId, repo) → Array<{label, href, targetPageId}>
 * Returns link objects for cross-page navigation, excluding the current page.
 * Returns empty array when repo is null/empty.
 */
function getCrossLinks(currentPageId, repo) {
  if (!repo) return [];

  var links = [];
  for (var i = 0; i < CROSS_LINK_TARGETS.length; i++) {
    var target = CROSS_LINK_TARGETS[i];
    if (target.targetPageId === currentPageId) continue;
    links.push({
      label: target.label,
      href: buildPageUrl(target.file, repo),
      targetPageId: target.targetPageId
    });
  }
  return links;
}

/**
 * renderCrossLinks(containerId, repo) → void
 * Renders cross-page link buttons into a container element.
 * Uses ds-btn-subtle class for styling.
 */
function renderCrossLinks(containerId, repo) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var links = getCrossLinks(getCurrentPageId(), repo);
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
