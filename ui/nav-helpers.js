/**
 * nav-helpers.js
 *
 * Pure helper functions for UI navigation. This file exists for
 * development/test synchronization only and is NOT referenced by
 * the HTML pages at runtime. The HTML pages inline these functions directly.
 */

/**
 * parseRepoParam(searchString) → string|null
 * Core parsing logic. Takes a query string (e.g. "?repo=numpy%2Fnumpy"),
 * extracts the repo param, decodes it, and validates owner/name format.
 * Returns null if missing, empty, or malformed.
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
 * Thin wrapper that reads ?repo= from current URL via parseRepoParam.
 */
function getRepoFromUrl() {
  return parseRepoParam(window.location.search);
}

/**
 * buildPageUrl(page, repo) → string
 * Builds a URL for a target page, optionally including ?repo= param.
 */
function buildPageUrl(page, repo) {
  if (repo) return page + "?repo=" + encodeURIComponent(repo);
  return page;
}

/**
 * getCurrentPageId() → string
 * Returns the current page identifier based on window.location.pathname.
 * Returns one of: "index", "insights", "graph", "dependency-tree"
 */
function getCurrentPageId() {
  var path = window.location.pathname;
  if (path.indexOf("insights") !== -1) return "insights";
  if (path.indexOf("graph") !== -1) return "graph";
  if (path.indexOf("dependency-tree") !== -1) return "dependency-tree";
  return "index";
}

module.exports = {
  parseRepoParam: parseRepoParam,
  getRepoFromUrl: getRepoFromUrl,
  buildPageUrl: buildPageUrl,
  getCurrentPageId: getCurrentPageId
};
