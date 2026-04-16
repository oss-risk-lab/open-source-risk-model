/**
 * nav-render.js
 *
 * Navigation rendering functions. This file exists for development/test
 * synchronization only and is NOT referenced by the HTML pages at runtime.
 * The HTML pages inline these functions directly.
 */

var helpers = require('./nav-helpers');
var buildPageUrl = helpers.buildPageUrl;

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

/**
 * renderNav(currentPageId, repo, scopeId) → void
 * Creates the <nav> element and inserts it as the first child of .wrap.
 * Applies aria-current="page" and active class to the link matching currentPageId.
 * If repo is non-null, all nav links include ?repo= param via buildPageUrl.
 * If scopeId is non-null, propagates scope_id to Overview, Graph, and Tree links.
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
    // Propagate scope_id to scope-aware pages, repo to all pages
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

/**
 * getCrossLinks(currentPageId, repo, scopeId) → Array<{label, href, targetPageId}>
 * Returns data objects for cross-page links, filtering out the link whose
 * targetPageId matches currentPageId. Returns empty array when both repo and
 * scopeId are null/empty (no cross-links without context).
 * When scopeId is present, propagates it to scope-aware pages (overview, graph, dependency-tree).
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

module.exports = {
  renderNav: renderNav,
  getCrossLinks: getCrossLinks
};
