import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

// ── Pure Helper Functions (extracted from overview.html inline JS) ──

/**
 * Extracts KPI values from scope data, mirroring renderKPIs logic.
 */
function extractKPIs(data) {
  var summary = data.system_risk_summary || {};
  return [
    { value: summary.total_repos != null ? summary.total_repos : 0, label: "Repos Analyzed" },
    { value: summary.total_unique_dependencies != null ? summary.total_unique_dependencies : 0, label: "Unique Dependencies" },
    { value: summary.high_risk_dependencies != null ? summary.high_risk_dependencies : 0, label: "High-Risk Deps" },
    { value: summary.vulnerable_dependencies != null ? summary.vulnerable_dependencies : 0, label: "Vulnerable Deps" },
    { value: summary.aggregate_risk_score != null ? summary.aggregate_risk_score.toFixed(2) : "N/A", label: "Aggregate Score (" + (summary.aggregate_label || "N/A") + ")" }
  ];
}

/**
 * Extracts risk badge info from scope data, mirroring renderRiskSummary logic.
 */
function extractRiskBadge(data) {
  var summary = data.system_risk_summary || {};
  var label = (summary.aggregate_label || "LOW").toUpperCase();
  return {
    text: label,
    cssClass: "risk-badge risk-badge-" + label.toLowerCase()
  };
}

/**
 * Extracts system summary sentence from scope data.
 */
function extractSystemSummary(data) {
  var summary = data.system_risk_summary || {};
  return summary.system_summary || "";
}

/**
 * Formats a priority risk item for rendering, mirroring renderPriorityRisks logic.
 */
function formatPriorityRisk(risk) {
  var usedBy = risk.used_by_repos || [];
  return {
    name: risk.name || "",
    type: risk.type || "repo",
    reason: risk.reason || "",
    severity: risk.severity || "low",
    usedByText: usedBy.length > 0
      ? "Used by " + usedBy.length + " repo" + (usedBy.length !== 1 ? "s" : "") + ": " + usedBy.join(", ")
      : null
  };
}

/**
 * Sorts risk drivers by descending risk score and limits to 5,
 * mirroring the data contract for top_risk_drivers.
 */
function getTopRiskDrivers(perRepoResults) {
  var valid = [];
  for (var i = 0; i < perRepoResults.length; i++) {
    var r = perRepoResults[i];
    if (r.error == null && r.risk_score != null) {
      valid.push({ repo: r.repo, risk_score: r.risk_score, risk_label: r.risk_label || "LOW" });
    }
  }
  valid.sort(function(a, b) { return b.risk_score - a.risk_score; });
  return valid.slice(0, 5);
}

/**
 * Determines the partial banner message, mirroring renderPartialBanner logic.
 */
function getPartialBannerMessage(data) {
  if (data.status !== "partial") return null;
  var errors = data.errors || {};
  var failedRepos = Object.keys(errors);
  var msg = "\u26A0\uFE0F Partial results: ";
  if (failedRepos.length > 0) {
    msg += "Analysis failed for " + failedRepos.length + " repo" + (failedRepos.length !== 1 ? "s" : "") + ": " + failedRepos.join(", ") + ". ";
    msg += "Results below are based on successfully analyzed repositories only.";
  } else {
    msg += "Some repositories could not be analyzed. Results may be incomplete.";
  }
  return msg;
}

/**
 * Determines error display for missing scope_id, mirroring page init logic.
 */
function getErrorForMissingScopeId(scopeId) {
  if (!scopeId) {
    return 'No scope ID provided. <a href="/">Return to homepage</a>';
  }
  return null;
}

// ── Tests ──


describe('Feature: multi-repo-ingestion-mvp, KPI computation from scope data', () => {
  /**
   * **Validates: Requirements 9.1**
   */
  it('extracts correct KPI values from scope data', () => {
    fc.assert(
      fc.property(
        fc.record({
          total_repos: fc.integer({ min: 0, max: 100 }),
          total_unique_dependencies: fc.integer({ min: 0, max: 500 }),
          high_risk_dependencies: fc.integer({ min: 0, max: 100 }),
          vulnerable_dependencies: fc.integer({ min: 0, max: 100 }),
          aggregate_risk_score: fc.float({ min: 0, max: 1, noNaN: true }),
          aggregate_label: fc.constantFrom("LOW", "MEDIUM", "HIGH")
        }),
        (summary) => {
          var data = { system_risk_summary: summary };
          var kpis = extractKPIs(data);

          expect(kpis).toHaveLength(5);
          expect(kpis[0].value).toBe(summary.total_repos);
          expect(kpis[0].label).toBe("Repos Analyzed");
          expect(kpis[1].value).toBe(summary.total_unique_dependencies);
          expect(kpis[1].label).toBe("Unique Dependencies");
          expect(kpis[2].value).toBe(summary.high_risk_dependencies);
          expect(kpis[2].label).toBe("High-Risk Deps");
          expect(kpis[3].value).toBe(summary.vulnerable_dependencies);
          expect(kpis[3].label).toBe("Vulnerable Deps");
          expect(kpis[4].value).toBe(summary.aggregate_risk_score.toFixed(2));
          expect(kpis[4].label).toContain("Aggregate Score");
          expect(kpis[4].label).toContain(summary.aggregate_label);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('handles missing system_risk_summary gracefully', () => {
    var kpis = extractKPIs({});
    expect(kpis).toHaveLength(5);
    expect(kpis[0].value).toBe(0);
    expect(kpis[1].value).toBe(0);
    expect(kpis[2].value).toBe(0);
    expect(kpis[3].value).toBe(0);
    expect(kpis[4].value).toBe("N/A");
  });

  it('handles null aggregate_risk_score', () => {
    var data = { system_risk_summary: { aggregate_risk_score: null, aggregate_label: null } };
    var kpis = extractKPIs(data);
    expect(kpis[4].value).toBe("N/A");
    expect(kpis[4].label).toContain("N/A");
  });
});

describe('Feature: multi-repo-ingestion-mvp, Priority risk rendering with used_by_repos', () => {
  /**
   * **Validates: Requirements 9.2**
   */
  it('formats priority risk items with all required fields', () => {
    fc.assert(
      fc.property(
        fc.record({
          name: fc.string({ minLength: 1, maxLength: 30 }),
          type: fc.constantFrom("dependency", "repo", "maintainer", "cve"),
          reason: fc.string({ minLength: 1, maxLength: 80 }),
          severity: fc.constantFrom("high", "medium", "low"),
          used_by_repos: fc.array(
            fc.stringOf(fc.char().filter(c => c !== '\0'), { minLength: 1, maxLength: 20 }),
            { minLength: 0, maxLength: 5 }
          )
        }),
        (risk) => {
          var formatted = formatPriorityRisk(risk);

          expect(formatted.name).toBe(risk.name);
          expect(formatted.type).toBe(risk.type);
          expect(formatted.reason).toBe(risk.reason);
          expect(formatted.severity).toBe(risk.severity);

          if (risk.used_by_repos.length > 0) {
            expect(formatted.usedByText).toContain("Used by " + risk.used_by_repos.length);
            expect(formatted.usedByText).toContain(risk.used_by_repos.join(", "));
            if (risk.used_by_repos.length === 1) {
              expect(formatted.usedByText).toContain("repo:");
              expect(formatted.usedByText).not.toContain("repos:");
            } else {
              expect(formatted.usedByText).toContain("repos:");
            }
          } else {
            expect(formatted.usedByText).toBeNull();
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('handles missing fields with defaults', () => {
    var formatted = formatPriorityRisk({});
    expect(formatted.name).toBe("");
    expect(formatted.type).toBe("repo");
    expect(formatted.reason).toBe("");
    expect(formatted.severity).toBe("low");
    expect(formatted.usedByText).toBeNull();
  });
});

describe('Feature: multi-repo-ingestion-mvp, Top risk drivers sorting', () => {
  /**
   * **Validates: Requirements 9.3**
   */
  it('sorts drivers by descending risk score and limits to 5', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            repo: fc.string({ minLength: 1, maxLength: 30 }),
            risk_score: fc.float({ min: 0, max: 1, noNaN: true }),
            risk_label: fc.constantFrom("LOW", "MEDIUM", "HIGH"),
            error: fc.constant(null)
          }),
          { minLength: 0, maxLength: 15 }
        ),
        (results) => {
          var drivers = getTopRiskDrivers(results);

          // Limited to 5
          expect(drivers.length).toBeLessThanOrEqual(5);

          // Sorted descending by risk_score
          for (var i = 1; i < drivers.length; i++) {
            expect(drivers[i - 1].risk_score).toBeGreaterThanOrEqual(drivers[i].risk_score);
          }

          // Each driver has required fields
          for (var j = 0; j < drivers.length; j++) {
            expect(drivers[j]).toHaveProperty("repo");
            expect(drivers[j]).toHaveProperty("risk_score");
            expect(drivers[j]).toHaveProperty("risk_label");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it('excludes error results from drivers', () => {
    var results = [
      { repo: "a/b", risk_score: 0.8, risk_label: "HIGH", error: null },
      { repo: "c/d", risk_score: 0.5, risk_label: "MEDIUM", error: "failed" },
      { repo: "e/f", risk_score: 0.3, risk_label: "LOW", error: null }
    ];
    var drivers = getTopRiskDrivers(results);
    expect(drivers).toHaveLength(2);
    expect(drivers[0].repo).toBe("a/b");
    expect(drivers[1].repo).toBe("e/f");
  });

  it('returns at most 5 even with many results', () => {
    var results = [];
    for (var i = 0; i < 10; i++) {
      results.push({ repo: "org/repo" + i, risk_score: i * 0.1, risk_label: "LOW", error: null });
    }
    var drivers = getTopRiskDrivers(results);
    expect(drivers).toHaveLength(5);
    // First driver should have highest score
    expect(drivers[0].risk_score).toBe(0.9);
  });
});

describe('Feature: multi-repo-ingestion-mvp, Error display for missing scope_id', () => {
  /**
   * **Validates: Requirements 9.4**
   */
  it('returns error HTML when scope_id is missing or falsy', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(null, undefined, "", false, 0),
        (scopeId) => {
          var error = getErrorForMissingScopeId(scopeId);
          expect(error).not.toBeNull();
          expect(error).toContain("No scope ID provided");
          expect(error).toContain("Return to homepage");
          expect(error).toContain('href="/"');
        }
      ),
      { numRuns: 20 }
    );
  });

  it('returns null when scope_id is present', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 50 }),
        (scopeId) => {
          var error = getErrorForMissingScopeId(scopeId);
          expect(error).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: multi-repo-ingestion-mvp, System risk summary sentence display', () => {
  /**
   * **Validates: Requirements 9.1**
   */
  it('extracts system summary sentence from scope data', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (sentence) => {
          var data = { system_risk_summary: { system_summary: sentence } };
          var result = extractSystemSummary(data);
          expect(result).toBe(sentence);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('returns empty string when system_summary is missing', () => {
    expect(extractSystemSummary({})).toBe("");
    expect(extractSystemSummary({ system_risk_summary: {} })).toBe("");
    expect(extractSystemSummary({ system_risk_summary: { system_summary: "" } })).toBe("");
  });

  it('risk badge reflects aggregate label correctly', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("LOW", "MEDIUM", "HIGH"),
        (label) => {
          var data = { system_risk_summary: { aggregate_label: label } };
          var badge = extractRiskBadge(data);
          expect(badge.text).toBe(label);
          expect(badge.cssClass).toBe("risk-badge risk-badge-" + label.toLowerCase());
        }
      ),
      { numRuns: 30 }
    );
  });

  it('risk badge defaults to LOW when aggregate_label is missing', () => {
    var badge = extractRiskBadge({});
    expect(badge.text).toBe("LOW");
    expect(badge.cssClass).toBe("risk-badge risk-badge-low");
  });
});

describe('Feature: multi-repo-ingestion-mvp, Partial results banner', () => {
  /**
   * **Validates: Requirements 9.1**
   */
  it('returns null for non-partial status', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("complete", "failed", "processing"),
        (status) => {
          var msg = getPartialBannerMessage({ status: status, errors: {} });
          expect(msg).toBeNull();
        }
      ),
      { numRuns: 30 }
    );
  });

  it('returns warning message for partial status with failed repos', () => {
    var data = {
      status: "partial",
      errors: { "org/repo1": "timeout", "org/repo2": "not found" }
    };
    var msg = getPartialBannerMessage(data);
    expect(msg).not.toBeNull();
    expect(msg).toContain("Partial results");
    expect(msg).toContain("2 repos");
    expect(msg).toContain("org/repo1");
    expect(msg).toContain("org/repo2");
  });

  it('returns generic message for partial status with no error details', () => {
    var data = { status: "partial", errors: {} };
    var msg = getPartialBannerMessage(data);
    expect(msg).not.toBeNull();
    expect(msg).toContain("Some repositories could not be analyzed");
  });
});

describe('Feature: multi-repo-ingestion-mvp, Pure function consistency', () => {
  /**
   * **Validates: Requirements 9.1, 9.2, 9.3**
   */
  it('all extracted functions are pure: same input produces same output', () => {
    fc.assert(
      fc.property(
        fc.record({
          total_repos: fc.integer({ min: 0, max: 50 }),
          total_unique_dependencies: fc.integer({ min: 0, max: 200 }),
          high_risk_dependencies: fc.integer({ min: 0, max: 50 }),
          vulnerable_dependencies: fc.integer({ min: 0, max: 50 }),
          aggregate_risk_score: fc.float({ min: 0, max: 1, noNaN: true }),
          aggregate_label: fc.constantFrom("LOW", "MEDIUM", "HIGH"),
          system_summary: fc.string({ minLength: 0, maxLength: 100 })
        }),
        (summary) => {
          var data = { system_risk_summary: summary };

          // extractKPIs is pure
          var kpis1 = extractKPIs(data);
          var kpis2 = extractKPIs(data);
          expect(kpis1).toEqual(kpis2);

          // extractRiskBadge is pure
          var badge1 = extractRiskBadge(data);
          var badge2 = extractRiskBadge(data);
          expect(badge1).toEqual(badge2);

          // extractSystemSummary is pure
          expect(extractSystemSummary(data)).toBe(extractSystemSummary(data));

          // Input not mutated
          var dataCopy = JSON.parse(JSON.stringify(data));
          extractKPIs(data);
          extractRiskBadge(data);
          extractSystemSummary(data);
          expect(data).toEqual(dataCopy);
        }
      ),
      { numRuns: 100 }
    );
  });
});
