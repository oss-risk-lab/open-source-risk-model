import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

// ── Pure Helper Functions (extracted from overview.html inline JS — upgrade additions) ──

/**
 * Extracts primary_risk_factor from scope data, mirroring renderRiskSummary logic.
 */
function extractPrimaryRiskFactor(data) {
  var summary = data.system_risk_summary || {};
  return summary.primary_risk_factor || "";
}

/**
 * Extracts risk_explanation from scope data, mirroring renderRiskSummary logic.
 */
function extractRiskExplanation(data) {
  var summary = data.system_risk_summary || {};
  return summary.risk_explanation || "";
}

/**
 * Extracts key_factors from scope data, mirroring renderRiskSummary logic.
 */
function extractKeyFactors(data) {
  var summary = data.system_risk_summary || {};
  return summary.key_factors || [];
}

/**
 * Extracts recommended_action from scope data, mirroring renderRiskSummary logic.
 */
function extractRecommendedAction(data) {
  var summary = data.system_risk_summary || {};
  return summary.recommended_action || "";
}

/**
 * Extracts insight_statements from scope data, mirroring renderRiskSummary logic.
 * Note: insight_statements lives at the top level of scope data, not inside system_risk_summary.
 */
function extractInsightStatements(data) {
  return data.insight_statements || [];
}

/**
 * Determines the contextual empty state message for priority risks,
 * mirroring renderPriorityRisks logic when risks array is empty.
 */
function getPriorityRisksEmptyMessage(data) {
  var risks = data.priority_risks || [];
  if (risks.length > 0) return null;

  var aggregateLabel = ((data.system_risk_summary || {}).aggregate_label || "").toUpperCase();
  if (aggregateLabel === "LOW") {
    return "No priority risks found \u2014 your system shows low risk across all analyzed components.";
  } else if (aggregateLabel === "MEDIUM") {
    return "No critical risks identified, but your system shows moderate risk that warrants monitoring.";
  } else if (aggregateLabel === "HIGH") {
    return "Risk data is being evaluated. Review individual repository insights for detailed analysis.";
  } else {
    return "No priority risks identified.";
  }
}

/**
 * Formats a risk driver signal card, mirroring renderRiskDrivers logic.
 * Returns signal card data if the driver has a `signal` field,
 * or falls back to old repo-list format if `signal` is absent.
 */
function formatRiskDriver(driver) {
  if (!driver.signal) {
    // Backward compatibility: old repo-list format
    return {
      format: "repo",
      repo: driver.repo || "",
      riskLabel: (driver.risk_label || "LOW").toUpperCase(),
      riskScore: driver.risk_score != null ? driver.risk_score.toFixed(2) : "N/A"
    };
  }
  // Signal card format
  return {
    format: "signal",
    signal: driver.signal,
    category: driver.category || "maintenance",
    severity: driver.severity || "info"
  };
}

/**
 * Determines the contextual empty/all-low message for risky dependencies,
 * mirroring renderRiskyDeps logic.
 */
function getRiskyDepsMessage(data) {
  var deps = data.top_risky_dependencies || [];

  if (deps.length === 0) {
    return "No risky dependencies identified across your analyzed components.";
  }

  var allLow = true;
  for (var k = 0; k < deps.length; k++) {
    if (deps[k].risk_label && deps[k].risk_label.toUpperCase() !== "LOW") {
      allLow = false;
      break;
    }
  }
  if (allLow) {
    return "All analyzed dependencies show low risk \u2014 no immediate concerns.";
  }

  return null; // Normal rendering, no special message
}

// ── Tests ──


describe('Feature: insight-layer-upgrade, renderRiskSummary new fields', () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3, 7.8**
   */
  it('extracts primary_risk_factor from scope data', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 100 }),
        (factor) => {
          var data = { system_risk_summary: { primary_risk_factor: factor } };
          expect(extractPrimaryRiskFactor(data)).toBe(factor);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('extracts risk_explanation from scope data', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (explanation) => {
          var data = { system_risk_summary: { risk_explanation: explanation } };
          expect(extractRiskExplanation(data)).toBe(explanation);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('extracts key_factors from scope data', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 1, maxLength: 5 }),
        (factors) => {
          var data = { system_risk_summary: { key_factors: factors } };
          var result = extractKeyFactors(data);
          expect(result).toEqual(factors);
          expect(result.length).toBeGreaterThanOrEqual(1);
          expect(result.length).toBeLessThanOrEqual(5);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('extracts recommended_action from scope data', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          "No immediate action required.",
          "Monitor dependencies and maintenance activity.",
          "Review vulnerable dependencies and high-risk repositories immediately."
        ),
        (action) => {
          var data = { system_risk_summary: { recommended_action: action } };
          expect(extractRecommendedAction(data)).toBe(action);
        }
      ),
      { numRuns: 30 }
    );
  });

  it('extracts insight_statements from scope data', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 100 }), { minLength: 1, maxLength: 6 }),
        (statements) => {
          var data = { insight_statements: statements };
          var result = extractInsightStatements(data);
          expect(result).toEqual(statements);
          expect(result.length).toBeGreaterThanOrEqual(1);
          expect(result.length).toBeLessThanOrEqual(6);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('all new fields are correctly extracted together', () => {
    var data = {
      system_risk_summary: {
        primary_risk_factor: "3 vulnerable dependencies drive elevated system risk",
        risk_explanation: "Your system shows high risk because 3 vulnerable dependencies were detected.",
        key_factors: ["3 vulnerable dependencies", "2 high-risk repositories"],
        recommended_action: "Review vulnerable dependencies and high-risk repositories immediately."
      },
      insight_statements: [
        "Multiple vulnerable dependencies suggest the dependency supply chain needs immediate review.",
        "2 repositories require attention due to elevated maintenance risk."
      ]
    };

    expect(extractPrimaryRiskFactor(data)).toBe("3 vulnerable dependencies drive elevated system risk");
    expect(extractRiskExplanation(data)).toContain("because");
    expect(extractKeyFactors(data)).toHaveLength(2);
    expect(extractRecommendedAction(data)).toContain("Review");
    expect(extractInsightStatements(data)).toHaveLength(2);
  });
});

describe('Feature: insight-layer-upgrade, renderPriorityRisks contextual empty states', () => {
  /**
   * **Validates: Requirements 3.1, 3.2, 3.3, 7.5**
   */
  it('returns LOW contextual message when aggregate is LOW and no risks', () => {
    var data = {
      priority_risks: [],
      system_risk_summary: { aggregate_label: "LOW" }
    };
    var msg = getPriorityRisksEmptyMessage(data);
    expect(msg).toBe("No priority risks found \u2014 your system shows low risk across all analyzed components.");
  });

  it('returns MEDIUM contextual message when aggregate is MEDIUM and no risks', () => {
    var data = {
      priority_risks: [],
      system_risk_summary: { aggregate_label: "MEDIUM" }
    };
    var msg = getPriorityRisksEmptyMessage(data);
    expect(msg).toBe("No critical risks identified, but your system shows moderate risk that warrants monitoring.");
  });

  it('returns HIGH contextual message when aggregate is HIGH and no risks', () => {
    var data = {
      priority_risks: [],
      system_risk_summary: { aggregate_label: "HIGH" }
    };
    var msg = getPriorityRisksEmptyMessage(data);
    expect(msg).toBe("Risk data is being evaluated. Review individual repository insights for detailed analysis.");
  });

  it('returns generic fallback when aggregate label is unknown', () => {
    var data = {
      priority_risks: [],
      system_risk_summary: { aggregate_label: "UNKNOWN" }
    };
    var msg = getPriorityRisksEmptyMessage(data);
    expect(msg).toBe("No priority risks identified.");
  });

  it('returns generic fallback when aggregate label is missing', () => {
    var data = { priority_risks: [], system_risk_summary: {} };
    var msg = getPriorityRisksEmptyMessage(data);
    expect(msg).toBe("No priority risks identified.");
  });

  it('returns null when priority risks exist', () => {
    var data = {
      priority_risks: [{ name: "some-risk", severity: "high" }],
      system_risk_summary: { aggregate_label: "HIGH" }
    };
    expect(getPriorityRisksEmptyMessage(data)).toBeNull();
  });

  it('contextual message varies by aggregate label (property)', () => {
    fc.assert(
      fc.property(
        fc.constantFrom("LOW", "MEDIUM", "HIGH"),
        (label) => {
          var data = {
            priority_risks: [],
            system_risk_summary: { aggregate_label: label }
          };
          var msg = getPriorityRisksEmptyMessage(data);
          expect(msg).not.toBeNull();
          expect(msg.length).toBeGreaterThan(0);

          // Each label produces a distinct message
          if (label === "LOW") {
            expect(msg).toContain("low risk across all analyzed components");
          } else if (label === "MEDIUM") {
            expect(msg).toContain("moderate risk that warrants monitoring");
          } else if (label === "HIGH") {
            expect(msg).toContain("Review individual repository insights");
          }
        }
      ),
      { numRuns: 30 }
    );
  });
});

describe('Feature: insight-layer-upgrade, renderRiskDrivers signal cards', () => {
  /**
   * **Validates: Requirements 4.1, 7.6**
   */
  it('formats signal objects with signal, category, severity fields', () => {
    fc.assert(
      fc.property(
        fc.record({
          signal: fc.string({ minLength: 1, maxLength: 100 }),
          category: fc.constantFrom("vulnerability", "maintenance", "dependency"),
          severity: fc.constantFrom("info", "low", "medium", "high")
        }),
        (driver) => {
          var formatted = formatRiskDriver(driver);
          expect(formatted.format).toBe("signal");
          expect(formatted.signal).toBe(driver.signal);
          expect(formatted.category).toBe(driver.category);
          expect(formatted.severity).toBe(driver.severity);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('falls back to repo rendering when signal field is absent', () => {
    fc.assert(
      fc.property(
        fc.record({
          repo: fc.string({ minLength: 1, maxLength: 50 }),
          risk_score: fc.float({ min: 0, max: 1, noNaN: true }),
          risk_label: fc.constantFrom("LOW", "MEDIUM", "HIGH")
        }),
        (driver) => {
          var formatted = formatRiskDriver(driver);
          expect(formatted.format).toBe("repo");
          expect(formatted.repo).toBe(driver.repo);
          expect(formatted.riskLabel).toBe(driver.risk_label.toUpperCase());
          expect(formatted.riskScore).toBe(driver.risk_score.toFixed(2));
        }
      ),
      { numRuns: 100 }
    );
  });

  it('backward compatibility: empty object falls back to repo format with defaults', () => {
    var formatted = formatRiskDriver({});
    expect(formatted.format).toBe("repo");
    expect(formatted.repo).toBe("");
    expect(formatted.riskLabel).toBe("LOW");
    expect(formatted.riskScore).toBe("N/A");
  });

  it('signal card with specific known values', () => {
    var driver = {
      signal: "No vulnerable dependencies detected",
      category: "vulnerability",
      severity: "info"
    };
    var formatted = formatRiskDriver(driver);
    expect(formatted.format).toBe("signal");
    expect(formatted.signal).toBe("No vulnerable dependencies detected");
    expect(formatted.category).toBe("vulnerability");
    expect(formatted.severity).toBe("info");
  });

  it('defaults category to maintenance and severity to info when missing on signal card', () => {
    var driver = { signal: "Some signal text" };
    var formatted = formatRiskDriver(driver);
    expect(formatted.format).toBe("signal");
    expect(formatted.category).toBe("maintenance");
    expect(formatted.severity).toBe("info");
  });
});

describe('Feature: insight-layer-upgrade, renderRiskyDeps contextual empty states', () => {
  /**
   * **Validates: Requirements 5.1, 5.3, 7.7**
   */
  it('returns empty state message when no risky deps', () => {
    var data = { top_risky_dependencies: [] };
    var msg = getRiskyDepsMessage(data);
    expect(msg).toBe("No risky dependencies identified across your analyzed components.");
  });

  it('returns all-low-risk message when all deps are LOW', () => {
    var data = {
      top_risky_dependencies: [
        { package_name: "lodash", risk_label: "LOW", risk_score: 0.1 },
        { package_name: "express", risk_label: "LOW", risk_score: 0.05 }
      ]
    };
    var msg = getRiskyDepsMessage(data);
    expect(msg).toBe("All analyzed dependencies show low risk \u2014 no immediate concerns.");
  });

  it('returns null (normal rendering) when non-low deps exist', () => {
    var data = {
      top_risky_dependencies: [
        { package_name: "lodash", risk_label: "LOW", risk_score: 0.1 },
        { package_name: "vulnerable-pkg", risk_label: "HIGH", risk_score: 0.8 }
      ]
    };
    expect(getRiskyDepsMessage(data)).toBeNull();
  });

  it('returns empty state when top_risky_dependencies is missing', () => {
    var msg = getRiskyDepsMessage({});
    expect(msg).toBe("No risky dependencies identified across your analyzed components.");
  });

  it('all-low detection works with case-insensitive labels (property)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            package_name: fc.string({ minLength: 1, maxLength: 30 }),
            risk_label: fc.constantFrom("LOW", "low", "Low"),
            risk_score: fc.float({ min: 0, max: Math.fround(0.29), noNaN: true })
          }),
          { minLength: 1, maxLength: 10 }
        ),
        (deps) => {
          var data = { top_risky_dependencies: deps };
          var msg = getRiskyDepsMessage(data);
          expect(msg).toBe("All analyzed dependencies show low risk \u2014 no immediate concerns.");
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe('Feature: insight-layer-upgrade, Graceful degradation when new fields are missing', () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3, 7.8**
   */
  it('returns safe defaults when system_risk_summary is empty', () => {
    var data = { system_risk_summary: {} };
    expect(extractPrimaryRiskFactor(data)).toBe("");
    expect(extractRiskExplanation(data)).toBe("");
    expect(extractKeyFactors(data)).toEqual([]);
    expect(extractRecommendedAction(data)).toBe("");
  });

  it('returns safe defaults when system_risk_summary is missing entirely', () => {
    var data = {};
    expect(extractPrimaryRiskFactor(data)).toBe("");
    expect(extractRiskExplanation(data)).toBe("");
    expect(extractKeyFactors(data)).toEqual([]);
    expect(extractRecommendedAction(data)).toBe("");
    expect(extractInsightStatements(data)).toEqual([]);
  });

  it('returns safe defaults when insight_statements is missing', () => {
    var data = { system_risk_summary: { aggregate_label: "LOW" } };
    expect(extractInsightStatements(data)).toEqual([]);
  });

  it('old-format scope data without new fields does not crash extraction (property)', () => {
    fc.assert(
      fc.property(
        fc.record({
          total_repos: fc.integer({ min: 0, max: 100 }),
          aggregate_risk_score: fc.float({ min: 0, max: 1, noNaN: true }),
          aggregate_label: fc.constantFrom("LOW", "MEDIUM", "HIGH"),
          system_summary: fc.string({ minLength: 0, maxLength: 100 })
        }),
        (summary) => {
          // Old-format data: no primary_risk_factor, risk_explanation, key_factors, etc.
          var data = { system_risk_summary: summary };

          // All extraction functions return safe defaults
          expect(extractPrimaryRiskFactor(data)).toBe("");
          expect(extractRiskExplanation(data)).toBe("");
          expect(extractKeyFactors(data)).toEqual([]);
          expect(extractRecommendedAction(data)).toBe("");
          expect(extractInsightStatements(data)).toEqual([]);
        }
      ),
      { numRuns: 100 }
    );
  });

  it('partial new fields: only present fields are extracted', () => {
    var data = {
      system_risk_summary: {
        risk_explanation: "Your system shows low risk because no issues found.",
        // key_factors, recommended_action, primary_risk_factor are missing
      }
    };
    expect(extractRiskExplanation(data)).toContain("low risk");
    expect(extractPrimaryRiskFactor(data)).toBe("");
    expect(extractKeyFactors(data)).toEqual([]);
    expect(extractRecommendedAction(data)).toBe("");
  });
});
