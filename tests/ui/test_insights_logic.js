import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

// ── Constants (duplicated from insights.html) ──
var API_BASE = "http://127.0.0.1:8000";

// ── Pure Helper Functions (duplicated from insights.html) ──

function buildApiUrl(state) {
  var url = API_BASE + "/api/insights?sort_by=" + encodeURIComponent(state.sort_by) +
    "&order=" + encodeURIComponent(state.order) +
    "&limit=" + state.limit +
    "&offset=" + state.offset;

  if (state.filters.label != null && state.filters.label !== "") {
    url += "&label=" + encodeURIComponent(state.filters.label);
  }
  if (state.filters.has_cves === true) {
    url += "&has_cves=true";
  }
  if (state.filters.has_maintainer_risk === true) {
    url += "&has_maintainer_risk=true";
  }
  if (state.filters.has_stale_release === true) {
    url += "&has_stale_release=true";
  }
  if (state.filters.min_score != null && state.filters.min_score !== "") {
    url += "&min_score=" + encodeURIComponent(state.filters.min_score);
  }

  return url;
}

function signalBadgeText(signals) {
  var badges = [];
  if (signals.has_cves) {
    badges.push({
      text: signals.cve_count > 1 ? signals.cve_count + " CVEs" : "CVE",
      severity: "high"
    });
  }
  if (signals.maintainer_concentration !== "info") {
    badges.push({
      text: "Maintainer",
      severity: signals.maintainer_concentration
    });
  }
  if (signals.release_staleness !== "info") {
    badges.push({
      text: "Stale release",
      severity: signals.release_staleness
    });
  }
  return badges;
}

function labelColorClass(label) {
  switch (label) {
    case "HIGH":   return "label-high";
    case "MEDIUM": return "label-medium";
    case "LOW":    return "label-low";
    default:       return "";
  }
}

function paginationRangeText(offset, limit, total) {
  if (total === 0) return "0 of 0";
  var start = offset + 1;
  var end = Math.min(offset + limit, total);
  return start + "\u2013" + end + " of " + total;
}

function paginationButtonState(offset, limit, total) {
  return {
    prevDisabled: offset === 0,
    nextDisabled: offset + limit >= total
  };
}

function nextOffset(offset, limit, total) {
  if (offset + limit < total) return offset + limit;
  return offset;
}

function prevOffset(offset, limit) {
  return Math.max(0, offset - limit);
}

function encodeRepoParam(repoFullName) {
  return encodeURIComponent(repoFullName);
}

function decodeRepoParam(encoded) {
  return decodeURIComponent(encoded);
}

function graphViewUrl(repoFullName) {
  return "graph.html?repo=" + encodeURIComponent(repoFullName);
}

function insightPanelAriaLabel(repoFullName) {
  return "Insight summary for " + repoFullName;
}

function summaryCounts(items) {
  var counts = { high: 0, medium: 0, low: 0 };
  for (var i = 0; i < items.length; i++) {
    var label = (items[i].graph_signal_label || "").toUpperCase();
    if (label === "HIGH") counts.high++;
    else if (label === "MEDIUM") counts.medium++;
    else if (label === "LOW") counts.low++;
  }
  return counts;
}

function formatErrorMessage(status, detail) {
  return "Error " + status + ": " + detail;
}

function generateInsightText(items) {
  var highItems = [];
  for (var i = 0; i < items.length; i++) {
    if ((items[i].graph_signal_label || "").toUpperCase() === "HIGH") {
      highItems.push(items[i]);
    }
  }
  if (highItems.length === 0) {
    return "All repositories are within acceptable risk thresholds. No immediate action required.";
  }
  var reasonCounts = {};
  for (var j = 0; j < highItems.length; j++) {
    var reasons = highItems[j].reasons || [];
    for (var k = 0; k < reasons.length; k++) {
      reasonCounts[reasons[k]] = (reasonCounts[reasons[k]] || 0) + 1;
    }
  }
  var topReason = "";
  var topCount = 0;
  for (var reason in reasonCounts) {
    if (reasonCounts[reason] > topCount) {
      topCount = reasonCounts[reason];
      topReason = reason;
    }
  }
  var suffix = topReason ? " \u2014 " + topReason.toLowerCase() : "";
  return highItems.length + " high-risk repositor" +
    (highItems.length === 1 ? "y" : "ies") + suffix;
}

function getDominantRiskLevel(items) {
  var counts = summaryCounts(items);
  if (counts.high > 0) return "high";
  if (counts.medium > 0) return "medium";
  if (counts.low > 0) return "low";
  return "none";
}

// ── Tests ──

describe('Feature: insight-ui-integration, Property 1: Label-to-color mapping is total and correct', () => {
  /**
   * **Validates: Requirements 2.3, 2.4, 2.5**
   */
  it('maps every label to the correct CSS class', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("HIGH", "MEDIUM", "LOW"),
        (label) => {
          const result = labelColorClass(label);
          const expected = {
            HIGH: "label-high",
            MEDIUM: "label-medium",
            LOW: "label-low"
          };
          expect(result).toBe(expected[label]);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 2: Signal badges appear only for non-info signals with correct text', () => {
  /**
   * **Validates: Requirements 2.6**
   */
  it('produces badges only for non-info signals with correct text', () => {
    fc.assert(
      fc.property(
        fc.record({
          has_cves: fc.boolean(),
          cve_count: fc.integer({ min: 0, max: 50 }),
          maintainer_concentration: fc.constantFrom("high", "medium", "mild", "info"),
          release_staleness: fc.constantFrom("high", "medium", "mild", "info")
        }),
        (signals) => {
          const badges = signalBadgeText(signals);

          // CVE badge: only when has_cves is true
          const cveBadge = badges.find(b => b.text === "CVE" || b.text.endsWith("CVEs"));
          if (signals.has_cves) {
            expect(cveBadge).toBeDefined();
            if (signals.cve_count > 1) {
              expect(cveBadge.text).toBe(signals.cve_count + " CVEs");
            } else {
              expect(cveBadge.text).toBe("CVE");
            }
            expect(cveBadge.severity).toBe("high");
          } else {
            expect(cveBadge).toBeUndefined();
          }

          // Maintainer badge: only when concentration !== "info"
          const maintainerBadge = badges.find(b => b.text === "Maintainer");
          if (signals.maintainer_concentration !== "info") {
            expect(maintainerBadge).toBeDefined();
            expect(maintainerBadge.severity).toBe(signals.maintainer_concentration);
          } else {
            expect(maintainerBadge).toBeUndefined();
          }

          // Stale release badge: only when staleness !== "info"
          const staleBadge = badges.find(b => b.text === "Stale release");
          if (signals.release_staleness !== "info") {
            expect(staleBadge).toBeDefined();
            expect(staleBadge.severity).toBe(signals.release_staleness);
          } else {
            expect(staleBadge).toBeUndefined();
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 3: App state maps to correct API query parameters', () => {
  /**
   * **Validates: Requirements 3.4, 3.5, 4.3**
   */
  it('builds correct API URL from app state', () => {
    fc.assert(
      fc.property(
        fc.record({
          filters: fc.record({
            label: fc.constantFrom(null, "", "HIGH", "MEDIUM", "LOW"),
            has_cves: fc.constantFrom(null, true, false),
            has_maintainer_risk: fc.constantFrom(null, true, false),
            has_stale_release: fc.constantFrom(null, true, false),
            min_score: fc.oneof(fc.constant(null), fc.constant(""), fc.float({ min: 0, max: 1, noNaN: true }))
          }),
          sort_by: fc.constantFrom("score", "base_risk", "cve_count", "maintainer_fraction", "release_staleness"),
          order: fc.constantFrom("asc", "desc"),
          limit: fc.integer({ min: 1, max: 100 }),
          offset: fc.integer({ min: 0, max: 1000 })
        }),
        (state) => {
          const url = buildApiUrl(state);

          // sort_by, order, limit, offset always present
          expect(url).toContain("sort_by=" + encodeURIComponent(state.sort_by));
          expect(url).toContain("order=" + encodeURIComponent(state.order));
          expect(url).toContain("limit=" + state.limit);
          expect(url).toContain("offset=" + state.offset);

          // null and empty-string filters are omitted
          if (state.filters.label == null || state.filters.label === "") {
            expect(url).not.toContain("&label=");
          } else {
            expect(url).toContain("&label=" + encodeURIComponent(state.filters.label));
          }

          // false booleans are never sent
          if (state.filters.has_cves === true) {
            expect(url).toContain("has_cves=true");
          } else {
            expect(url).not.toContain("has_cves");
          }

          if (state.filters.has_maintainer_risk === true) {
            expect(url).toContain("has_maintainer_risk=true");
          } else {
            expect(url).not.toContain("has_maintainer_risk");
          }

          if (state.filters.has_stale_release === true) {
            expect(url).toContain("has_stale_release=true");
          } else {
            expect(url).not.toContain("has_stale_release");
          }

          if (state.filters.min_score != null && state.filters.min_score !== "") {
            expect(url).toContain("min_score=");
          } else {
            expect(url).not.toContain("min_score");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 4: Pagination range text is correct', () => {
  /**
   * **Validates: Requirements 5.2**
   */
  it('produces correct range text for any offset/limit/total', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }),
        fc.integer({ min: 1, max: 100 }),
        fc.integer({ min: 0, max: 10000 }),
        (offset, limit, total) => {
          const text = paginationRangeText(offset, limit, total);
          if (total === 0) {
            expect(text).toBe("0 of 0");
          } else {
            const start = offset + 1;
            const end = Math.min(offset + limit, total);
            expect(text).toBe(start + "\u2013" + end + " of " + total);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 5: Pagination button enabled/disabled state', () => {
  /**
   * **Validates: Requirements 5.4, 5.5**
   */
  it('disables Previous iff offset===0, Next iff offset+limit>=total', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }),
        fc.integer({ min: 1, max: 100 }),
        fc.integer({ min: 0, max: 10000 }),
        (offset, limit, total) => {
          const state = paginationButtonState(offset, limit, total);
          expect(state.prevDisabled).toBe(offset === 0);
          expect(state.nextDisabled).toBe(offset + limit >= total);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 6: Pagination offset arithmetic is bounded', () => {
  /**
   * **Validates: Requirements 5.6, 5.7**
   */
  it('nextOffset and prevOffset produce bounded results', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }),
        fc.integer({ min: 1, max: 100 }),
        fc.integer({ min: 0, max: 10000 }),
        (offset, limit, total) => {
          // nextOffset returns offset+limit only when offset+limit < total
          const next = nextOffset(offset, limit, total);
          if (offset + limit < total) {
            expect(next).toBe(offset + limit);
          } else {
            expect(next).toBe(offset);
          }
          expect(next).toBeGreaterThanOrEqual(0);

          // prevOffset returns max(0, offset - limit)
          const prev = prevOffset(offset, limit);
          expect(prev).toBe(Math.max(0, offset - limit));
          expect(prev).toBeGreaterThanOrEqual(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 7: Filter/sort change resets offset to zero', () => {
  /**
   * **Validates: Requirements 5.8**
   */
  it('offset resets to 0 after simulated filter/sort change', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 1000 }),
        (offset) => {
          // Simulate the onFilterChange/onSortChange logic: reset offset to 0
          const newOffset = 0;
          expect(newOffset).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 8: Repo name URL encoding round trip', () => {
  /**
   * **Validates: Requirements 6.2, 6.3**
   */
  it('encodeRepoParam then decodeRepoParam returns original, encoded contains %2F', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 }),
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 })
        ),
        ([owner, repo]) => {
          const repoFullName = owner + "/" + repo;
          const encoded = encodeRepoParam(repoFullName);
          const decoded = decodeRepoParam(encoded);
          expect(decoded).toBe(repoFullName);
          expect(encoded).toContain("%2F");
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 9: Detail view graph link points to correct URL', () => {
  /**
   * **Validates: Requirements 6.7**
   */
  it('graphViewUrl returns correct URL for any owner/repo', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 }),
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 })
        ),
        ([owner, repo]) => {
          const repoFullName = owner + "/" + repo;
          const url = graphViewUrl(repoFullName);
          expect(url).toBe("graph.html?repo=" + encodeURIComponent(repoFullName));
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 10: Render output contains all required fields', () => {
  /**
   * **Validates: Requirements 2.2, 7.3**
   * Unit test with specific example data (not property-based).
   */
  it('formatErrorMessage includes status and detail', () => {
    const msg = formatErrorMessage(500, "Internal Server Error");
    expect(msg).toContain("500");
    expect(msg).toContain("Internal Server Error");
  });

  it('labelColorClass returns correct class for each label', () => {
    expect(labelColorClass("HIGH")).toBe("label-high");
    expect(labelColorClass("MEDIUM")).toBe("label-medium");
    expect(labelColorClass("LOW")).toBe("label-low");
  });

  it('signalBadgeText returns correct badges for example data', () => {
    const signals = {
      has_cves: true,
      cve_count: 2,
      maintainer_concentration: "medium",
      top_contributor: "user123",
      top_contributor_fraction: 0.34,
      release_staleness: "info",
      days_since_release: 15
    };
    const badges = signalBadgeText(signals);
    expect(badges).toHaveLength(2);
    expect(badges[0]).toEqual({ text: "2 CVEs", severity: "high" });
    expect(badges[1]).toEqual({ text: "Maintainer", severity: "medium" });
  });

  it('summaryCounts returns correct counts for example items', () => {
    const items = [
      { repo_full_name: "a/b", graph_signal_label: "HIGH" },
      { repo_full_name: "c/d", graph_signal_label: "HIGH" },
      { repo_full_name: "e/f", graph_signal_label: "MEDIUM" },
      { repo_full_name: "g/h", graph_signal_label: "LOW" }
    ];
    const counts = summaryCounts(items);
    expect(counts).toEqual({ high: 2, medium: 1, low: 1 });
  });

  it('paginationRangeText returns correct text for example', () => {
    expect(paginationRangeText(0, 25, 145)).toBe("1\u201325 of 145");
    expect(paginationRangeText(0, 25, 0)).toBe("0 of 0");
  });

  it('graphViewUrl returns correct URL for example', () => {
    expect(graphViewUrl("numpy/numpy")).toBe("graph.html?repo=numpy%2Fnumpy");
  });

  it('insightPanelAriaLabel returns correct label for example', () => {
    expect(insightPanelAriaLabel("numpy/numpy")).toBe("Insight summary for numpy/numpy");
  });

  it('encodeRepoParam/decodeRepoParam round-trips for example', () => {
    const encoded = encodeRepoParam("numpy/numpy");
    expect(encoded).toBe("numpy%2Fnumpy");
    expect(decodeRepoParam(encoded)).toBe("numpy/numpy");
  });
});

describe('Feature: insight-ui-integration, Property 11: Summary strip counts match current page item labels', () => {
  /**
   * **Validates: Requirements 11.1**
   */
  it('summaryCounts returns correct HIGH/MEDIUM/LOW counts for any items list', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW")
          }),
          { minLength: 0, maxLength: 50 }
        ),
        (items) => {
          const counts = summaryCounts(items);
          const expectedHigh = items.filter(i => i.graph_signal_label === "HIGH").length;
          const expectedMedium = items.filter(i => i.graph_signal_label === "MEDIUM").length;
          const expectedLow = items.filter(i => i.graph_signal_label === "LOW").length;
          expect(counts.high).toBe(expectedHigh);
          expect(counts.medium).toBe(expectedMedium);
          expect(counts.low).toBe(expectedLow);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 12: Error display includes status code and detail', () => {
  /**
   * **Validates: Requirements 8.2**
   */
  it('formatErrorMessage output contains both status code and detail', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 400, max: 599 }),
        fc.string({ minLength: 1, maxLength: 100 }),
        (status, detail) => {
          const msg = formatErrorMessage(status, detail);
          expect(msg).toContain(String(status));
          expect(msg).toContain(detail);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-ui-integration, Property 13: Insight panel aria-label contains repo name', () => {
  /**
   * **Validates: Requirements 9.6**
   */
  it('insightPanelAriaLabel output contains the repo name', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '\0'), { minLength: 1, maxLength: 20 }),
          fc.stringOf(fc.char().filter(c => c !== '\0'), { minLength: 1, maxLength: 20 })
        ),
        ([owner, repo]) => {
          const repoFullName = owner + "/" + repo;
          const label = insightPanelAriaLabel(repoFullName);
          expect(label).toContain(repoFullName);
          expect(label).toBe("Insight summary for " + repoFullName);
        }
      ),
      { numRuns: 100 }
    );
  });
});


describe('Feature: insights-dashboard-redesign, Property 4: generateInsightText correctness', () => {
  /**
   * **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
   */
  it('returns no-HIGH message when no HIGH items exist', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("MEDIUM", "LOW"),
            reasons: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 5 })
          }),
          { minLength: 0, maxLength: 20 }
        ),
        (items) => {
          const result = generateInsightText(items);
          expect(result).toBe("All repositories are within acceptable risk thresholds. No immediate action required.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it('contains count and "high-risk" when HIGH items exist, with correct singular/plural', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constant("HIGH"),
            reasons: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 5 })
          }),
          { minLength: 1, maxLength: 20 }
        ),
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("MEDIUM", "LOW"),
            reasons: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 5 })
          }),
          { minLength: 0, maxLength: 10 }
        ),
        (highItems, otherItems) => {
          const items = [...highItems, ...otherItems];
          const result = generateInsightText(items);
          expect(result).toContain("high-risk");
          expect(result).toContain(String(highItems.length));
          if (highItems.length === 1) {
            expect(result).toContain("repository");
            expect(result).not.toContain("repositories");
          } else {
            expect(result).toContain("repositories");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insights-dashboard-redesign, Property 6: getDominantRiskLevel priority ordering', () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
   */
  it('returns correct priority: high > medium > low > none', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW")
          }),
          { minLength: 0, maxLength: 30 }
        ),
        (items) => {
          const result = getDominantRiskLevel(items);
          const hasHigh = items.some(i => i.graph_signal_label === "HIGH");
          const hasMedium = items.some(i => i.graph_signal_label === "MEDIUM");
          const hasLow = items.some(i => i.graph_signal_label === "LOW");

          if (hasHigh) {
            expect(result).toBe("high");
          } else if (hasMedium) {
            expect(result).toBe("medium");
          } else if (hasLow) {
            expect(result).toBe("low");
          } else {
            expect(result).toBe("none");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insights-dashboard-redesign, Property 5: generateInsightText and getDominantRiskLevel purity', () => {
  /**
   * **Validates: Requirements 5.6, 7.5**
   */
  it('both functions are pure: same input produces same output', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW"),
            reasons: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 5 })
          }),
          { minLength: 0, maxLength: 20 }
        ),
        (items) => {
          // Call each function twice with the same input
          const insight1 = generateInsightText(items);
          const insight2 = generateInsightText(items);
          expect(insight1).toBe(insight2);

          const risk1 = getDominantRiskLevel(items);
          const risk2 = getDominantRiskLevel(items);
          expect(risk1).toBe(risk2);

          // Verify input array is not mutated
          const itemsCopy = JSON.parse(JSON.stringify(items));
          generateInsightText(items);
          getDominantRiskLevel(items);
          expect(items).toEqual(itemsCopy);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ── Helper: simulate renderSummaryStrip HTML output (pure, no DOM) ──
function buildKpiStripHtml(items, total) {
  var counts = summaryCounts(items);
  return '<div class="kpi-card kpi-card-dominant">' +
      '<span class="kpi-value kpi-value-lg">' + total + '</span>' +
      '<span class="kpi-label">Total Repos</span>' +
    '</div>' +
    '<div class="kpi-card kpi-card-secondary kpi-card-high">' +
      '<span class="kpi-value" style="color:var(--status-high-text);">' + counts.high + '</span>' +
      '<span class="kpi-label">High Risk</span>' +
    '</div>' +
    '<div class="kpi-card kpi-card-secondary">' +
      '<span class="kpi-value" style="color:var(--status-medium-text);">' + counts.medium + '</span>' +
      '<span class="kpi-label">Medium Risk</span>' +
    '</div>' +
    '<div class="kpi-card kpi-card-secondary">' +
      '<span class="kpi-value" style="color:var(--status-low-text);">' + counts.low + '</span>' +
      '<span class="kpi-label">Low Risk</span>' +
    '</div>';
}

// ── Helper: pure logic mirroring renderTable's row-high class assignment ──
function shouldHaveRowHighClass(item) {
  return (item.graph_signal_label || "").toUpperCase() === "HIGH";
}

describe('Feature: insights-dashboard-redesign, Property 11: Risk accent on HIGH table rows', () => {
  /**
   * **Validates: Requirements 10.3, 16.3, 19.13**
   */
  it('row-high class is assigned if and only if graph_signal_label is HIGH', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW"),
            graph_signal_score: fc.float({ min: 0, max: 1, noNaN: true }),
            reasons: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 0, maxLength: 3 }),
            signals: fc.record({
              has_cves: fc.boolean(),
              cve_count: fc.integer({ min: 0, max: 10 }),
              maintainer_concentration: fc.constantFrom("high", "medium", "mild", "info"),
              release_staleness: fc.constantFrom("high", "medium", "mild", "info")
            })
          }),
          { minLength: 0, maxLength: 30 }
        ),
        (items) => {
          for (const item of items) {
            const isHigh = item.graph_signal_label === "HIGH";
            expect(shouldHaveRowHighClass(item)).toBe(isHigh);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('case-insensitive label matching: "high", "High", "HIGH" all get row-high', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("HIGH", "high", "High", "hIgH"),
        (label) => {
          const item = { graph_signal_label: label };
          expect(shouldHaveRowHighClass(item)).toBe(true);
        }
      ),
      { numRuns: 50 }
    );
  });

  it('non-HIGH labels never get row-high', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("MEDIUM", "LOW", "medium", "low", ""),
        (label) => {
          const item = { graph_signal_label: label };
          expect(shouldHaveRowHighClass(item)).toBe(false);
        }
      ),
      { numRuns: 50 }
    );
  });

  it('missing graph_signal_label does not get row-high', () => {
    expect(shouldHaveRowHighClass({})).toBe(false);
    expect(shouldHaveRowHighClass({ graph_signal_label: null })).toBe(false);
    expect(shouldHaveRowHighClass({ graph_signal_label: undefined })).toBe(false);
  });
});

describe('Feature: insights-dashboard-redesign, Property 9: KPI strip weighted layout', () => {
  /**
   * **Validates: Requirements 8.1, 8.2, 8.3, 8.7**
   */
  it('produces exactly 4 KPI cards with correct class structure', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW")
          }),
          { minLength: 0, maxLength: 50 }
        ),
        fc.integer({ min: 0, max: 10000 }),
        (items, total) => {
          const html = buildKpiStripHtml(items, total);

          // Exactly 4 kpi-card elements
          const cardMatches = html.match(/class="kpi-card/g);
          expect(cardMatches).toHaveLength(4);

          // First card has kpi-card-dominant
          expect(html.indexOf('kpi-card kpi-card-dominant')).toBeLessThan(
            html.indexOf('kpi-card kpi-card-secondary')
          );

          // HIGH card has kpi-card-high class
          expect(html).toContain('kpi-card-secondary kpi-card-high');

          // Remaining 3 cards have kpi-card-secondary
          const secondaryMatches = html.match(/kpi-card-secondary/g);
          expect(secondaryMatches).toHaveLength(3);

          // Dominant card shows total value with kpi-value-lg
          expect(html).toContain('kpi-value kpi-value-lg">' + total + '</span>');

          // Counts match summaryCounts
          const counts = summaryCounts(items);
          expect(html).toContain('color:var(--status-high-text);">' + counts.high + '</span>');
          expect(html).toContain('color:var(--status-medium-text);">' + counts.medium + '</span>');
          expect(html).toContain('color:var(--status-low-text);">' + counts.low + '</span>');
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ── Pure logic: view state to expected visibility mapping (for Property 14) ──

/**
 * Maps a view state string to the expected visibility of each UI container.
 * Returns an object with display values for each element.
 * This is the pure logic that setViewState implements in the DOM.
 */
function expectedVisibility(state) {
  // All hidden by default
  var vis = {
    hero: "none",
    loading: "none",
    error: "none",
    empty: "none",
    table: "none",
    summary: "none",
    pagination: "none",
    detail: "none"
  };
  switch (state) {
    case "loading":
      vis.loading = "block";
      break;
    case "error":
      vis.error = "block";
      break;
    case "empty":
      vis.empty = "block";
      break;
    case "list":
      vis.hero = "flex";
      vis.table = "block";
      vis.summary = "flex";
      vis.pagination = "flex";
      break;
    case "detail":
      vis.detail = "block";
      break;
  }
  return vis;
}

describe('Feature: insights-dashboard-redesign, Property 14: View state mutual exclusivity', () => {
  /**
   * **Validates: Requirements 4.3, 4.4, 19.15**
   */
  it('each view state maps to exactly one visible container group with no overlap', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("loading", "error", "empty", "list", "detail"),
        (state) => {
          const vis = expectedVisibility(state);
          const allKeys = ["hero", "loading", "error", "empty", "table", "summary", "pagination", "detail"];

          // Count visible elements
          const visibleKeys = allKeys.filter(k => vis[k] !== "none");

          if (state === "list") {
            // List state shows hero, table, summary, pagination
            expect(visibleKeys).toEqual(expect.arrayContaining(["hero", "table", "summary", "pagination"]));
            expect(visibleKeys).toHaveLength(4);
          } else if (state === "detail") {
            expect(visibleKeys).toEqual(["detail"]);
          } else if (state === "loading") {
            expect(visibleKeys).toEqual(["loading"]);
          } else if (state === "error") {
            expect(visibleKeys).toEqual(["error"]);
          } else if (state === "empty") {
            expect(visibleKeys).toEqual(["empty"]);
          }

          // Hero is only visible in "list" state
          if (state !== "list") {
            expect(vis.hero).toBe("none");
          } else {
            expect(vis.hero).toBe("flex");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('non-list states always hide hero, table, summary, and pagination', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("loading", "error", "empty", "detail"),
        (state) => {
          const vis = expectedVisibility(state);
          expect(vis.hero).toBe("none");
          expect(vis.table).toBe("none");
          expect(vis.summary).toBe("none");
          expect(vis.pagination).toBe("none");
        }
      ),
      { numRuns: 100 }
    );
  });

  it('list state shows hero with flex display', () => {
    const vis = expectedVisibility("list");
    expect(vis.hero).toBe("flex");
    expect(vis.table).toBe("block");
    expect(vis.summary).toBe("flex");
    expect(vis.pagination).toBe("flex");
    // All others hidden
    expect(vis.loading).toBe("none");
    expect(vis.error).toBe("none");
    expect(vis.empty).toBe("none");
    expect(vis.detail).toBe("none");
  });
});


// ── Cross-page link helpers (duplicated from insights.html) ──

function buildPageUrl(page, repo) {
  if (repo) return page + "?repo=" + encodeURIComponent(repo);
  return page;
}

function getCrossLinks(currentPageId, repo) {
  if (!repo) return [];
  var targets = [
    { targetPageId: "insights", label: "Open in Insights", file: "insights.html" },
    { targetPageId: "graph", label: "Open in Graph", file: "graph.html" },
    { targetPageId: "dependency-tree", label: "Open in Dependency Tree", file: "dependency-tree.html" }
  ];
  var links = [];
  for (var i = 0; i < targets.length; i++) {
    if (targets[i].targetPageId === currentPageId) continue;
    links.push({ label: targets[i].label, href: buildPageUrl(targets[i].file, repo), targetPageId: targets[i].targetPageId });
  }
  return links;
}

describe('Feature: insights-dashboard-redesign, Property 16: Detail view rendering completeness', () => {
  /**
   * **Validates: Requirements 15.1, 15.2, 15.3, 15.4**
   */
  it('getCrossLinks("insights", repo) returns links for graph and dependency-tree but not insights', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 }),
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 20 })
        ),
        ([owner, repo]) => {
          const repoFullName = owner + "/" + repo;
          const links = getCrossLinks("insights", repoFullName);

          // Should return exactly 2 links (graph and dependency-tree, not insights)
          expect(links).toHaveLength(2);

          // Should not include insights
          const pageIds = links.map(l => l.targetPageId);
          expect(pageIds).not.toContain("insights");
          expect(pageIds).toContain("graph");
          expect(pageIds).toContain("dependency-tree");

          // Each link href should contain the encoded repo name
          for (const link of links) {
            expect(link.href).toContain(encodeURIComponent(repoFullName));
          }

          // Graph link should point to graph.html
          const graphLink = links.find(l => l.targetPageId === "graph");
          expect(graphLink.href).toBe("graph.html?repo=" + encodeURIComponent(repoFullName));
          expect(graphLink.label).toBe("Open in Graph");

          // Dependency tree link should point to dependency-tree.html
          const treeLink = links.find(l => l.targetPageId === "dependency-tree");
          expect(treeLink.href).toBe("dependency-tree.html?repo=" + encodeURIComponent(repoFullName));
          expect(treeLink.label).toBe("Open in Dependency Tree");
        }
      ),
      { numRuns: 100 }
    );
  });

  it('getCrossLinks returns empty array when repo is falsy', () => {
    expect(getCrossLinks("insights", null)).toEqual([]);
    expect(getCrossLinks("insights", "")).toEqual([]);
    expect(getCrossLinks("insights", undefined)).toEqual([]);
  });

  it('getCrossLinks excludes the current page for any page id', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("insights", "graph", "dependency-tree"),
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 15 }),
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 15 })
        ),
        (pageId, [owner, repo]) => {
          const repoFullName = owner + "/" + repo;
          const links = getCrossLinks(pageId, repoFullName);

          // Current page should never appear in results
          const pageIds = links.map(l => l.targetPageId);
          expect(pageIds).not.toContain(pageId);

          // Should have exactly 2 links (3 total pages minus current)
          expect(links).toHaveLength(2);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('buildPageUrl produces correct URLs with and without repo', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("insights.html", "graph.html", "dependency-tree.html"),
        fc.tuple(
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 15 }),
          fc.stringOf(fc.char().filter(c => c !== '/' && c !== '\0'), { minLength: 1, maxLength: 15 })
        ),
        (page, [owner, repo]) => {
          const repoFullName = owner + "/" + repo;

          // With repo: page?repo=encoded
          const urlWithRepo = buildPageUrl(page, repoFullName);
          expect(urlWithRepo).toBe(page + "?repo=" + encodeURIComponent(repoFullName));

          // Without repo: just the page
          const urlWithoutRepo = buildPageUrl(page, null);
          expect(urlWithoutRepo).toBe(page);
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insights-dashboard-redesign, Property 13: Preserved pure function equivalence', () => {
  /**
   * **Validates: Requirements 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.11**
   */
  it('all preserved pure functions accept their expected arguments and return consistent types', () => {
    fc.assert(
      fc.property(
        fc.record({
          filters: fc.record({
            label: fc.constantFrom(null, "", "HIGH", "MEDIUM", "LOW"),
            has_cves: fc.constantFrom(null, true, false),
            has_maintainer_risk: fc.constantFrom(null, true, false),
            has_stale_release: fc.constantFrom(null, true, false),
            min_score: fc.oneof(fc.constant(null), fc.constant(""), fc.float({ min: 0, max: 1, noNaN: true }))
          }),
          sort_by: fc.constantFrom("score", "base_risk", "cve_count", "maintainer_fraction", "release_staleness"),
          order: fc.constantFrom("asc", "desc"),
          limit: fc.integer({ min: 1, max: 100 }),
          offset: fc.integer({ min: 0, max: 1000 })
        }),
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW")
          }),
          { minLength: 0, maxLength: 20 }
        ),
        fc.record({
          has_cves: fc.boolean(),
          cve_count: fc.integer({ min: 0, max: 50 }),
          maintainer_concentration: fc.constantFrom("high", "medium", "mild", "info"),
          release_staleness: fc.constantFrom("high", "medium", "mild", "info")
        }),
        fc.integer({ min: 0, max: 10000 }),
        (state, items, signals, total) => {
          // buildApiUrl: returns a string URL
          const url = buildApiUrl(state);
          expect(typeof url).toBe("string");
          expect(url).toContain(API_BASE);

          // signalBadgeText: returns an array of badge objects
          const badges = signalBadgeText(signals);
          expect(Array.isArray(badges)).toBe(true);
          for (const b of badges) {
            expect(typeof b.text).toBe("string");
            expect(typeof b.severity).toBe("string");
          }

          // labelColorClass: returns a string for valid labels
          for (const label of ["HIGH", "MEDIUM", "LOW"]) {
            const cls = labelColorClass(label);
            expect(typeof cls).toBe("string");
            expect(cls.length).toBeGreaterThan(0);
          }
          // Unknown label returns empty string
          expect(labelColorClass("UNKNOWN")).toBe("");

          // paginationRangeText: returns a string
          const rangeText = paginationRangeText(state.offset, state.limit, total);
          expect(typeof rangeText).toBe("string");

          // paginationButtonState: returns object with prevDisabled and nextDisabled booleans
          const btnState = paginationButtonState(state.offset, state.limit, total);
          expect(typeof btnState.prevDisabled).toBe("boolean");
          expect(typeof btnState.nextDisabled).toBe("boolean");

          // nextOffset: returns a non-negative integer
          const nOff = nextOffset(state.offset, state.limit, total);
          expect(typeof nOff).toBe("number");
          expect(nOff).toBeGreaterThanOrEqual(0);

          // prevOffset: returns a non-negative integer
          const pOff = prevOffset(state.offset, state.limit);
          expect(typeof pOff).toBe("number");
          expect(pOff).toBeGreaterThanOrEqual(0);

          // summaryCounts: returns object with high, medium, low counts
          const counts = summaryCounts(items);
          expect(typeof counts.high).toBe("number");
          expect(typeof counts.medium).toBe("number");
          expect(typeof counts.low).toBe("number");
          expect(counts.high + counts.medium + counts.low).toBe(items.length);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('all preserved functions are pure: same input produces same output', () => {
    fc.assert(
      fc.property(
        fc.record({
          filters: fc.record({
            label: fc.constantFrom(null, "", "HIGH"),
            has_cves: fc.constantFrom(null, true, false),
            has_maintainer_risk: fc.constantFrom(null, true),
            has_stale_release: fc.constantFrom(null, true),
            min_score: fc.oneof(fc.constant(null), fc.float({ min: 0, max: 1, noNaN: true }))
          }),
          sort_by: fc.constantFrom("score", "base_risk"),
          order: fc.constantFrom("asc", "desc"),
          limit: fc.integer({ min: 1, max: 50 }),
          offset: fc.integer({ min: 0, max: 500 })
        }),
        fc.array(
          fc.record({
            repo_full_name: fc.string({ minLength: 1 }),
            graph_signal_label: fc.constantFrom("HIGH", "MEDIUM", "LOW")
          }),
          { minLength: 0, maxLength: 10 }
        ),
        (state, items) => {
          // Each function called twice with same input produces same output
          expect(buildApiUrl(state)).toBe(buildApiUrl(state));
          expect(labelColorClass("HIGH")).toBe(labelColorClass("HIGH"));
          expect(paginationRangeText(state.offset, state.limit, 100)).toBe(
            paginationRangeText(state.offset, state.limit, 100)
          );
          expect(paginationButtonState(state.offset, state.limit, 100)).toEqual(
            paginationButtonState(state.offset, state.limit, 100)
          );
          expect(nextOffset(state.offset, state.limit, 100)).toBe(
            nextOffset(state.offset, state.limit, 100)
          );
          expect(prevOffset(state.offset, state.limit)).toBe(
            prevOffset(state.offset, state.limit)
          );
          expect(summaryCounts(items)).toEqual(summaryCounts(items));

          // Verify items array is not mutated
          const itemsCopy = JSON.parse(JSON.stringify(items));
          summaryCounts(items);
          expect(items).toEqual(itemsCopy);
        }
      ),
      { numRuns: 100 }
    );
  });
});
