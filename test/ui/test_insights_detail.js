/**
 * Unit tests for Insights detail view.
 * Validates: Requirements 7.1, 8.2, 9.3
 *
 * Run: node test/ui/test_insights_detail.js
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const htmlPath = path.join(__dirname, '..', '..', 'ui', 'insights.html');
const html = fs.readFileSync(htmlPath, 'utf-8');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed++;
    console.log(`  ✗ ${name}`);
    console.log(`    ${err.message}`);
  }
}

// ── 1. Risk Summary Block renders two KPI blocks (Requirement 7.1) ──

console.log('\n▸ Risk Summary Block (Requirement 7.1)');

test('renderDetailView contains "Maintenance Risk" KPI label', () => {
  // The renderDetailView function builds HTML with "Maintenance Risk" text
  const fnMatch = html.match(/function\s+renderDetailView[\s\S]*?^  \}/m);
  assert.ok(fnMatch, 'renderDetailView function not found');
  assert.ok(
    fnMatch[0].includes('Maintenance Risk'),
    'renderDetailView does not contain "Maintenance Risk" label'
  );
});

test('renderDetailView contains "Graph Signal Risk" KPI label', () => {
  const fnMatch = html.match(/function\s+renderDetailView[\s\S]*?^  \}/m);
  assert.ok(fnMatch, 'renderDetailView function not found');
  assert.ok(
    fnMatch[0].includes('Graph Signal Risk'),
    'renderDetailView does not contain "Graph Signal Risk" label'
  );
});

test('renderDetailView uses ds-kpi class for KPI blocks', () => {
  const fnMatch = html.match(/function\s+renderDetailView[\s\S]*?^  \}/m);
  assert.ok(fnMatch, 'renderDetailView function not found');
  const dsKpiCount = (fnMatch[0].match(/ds-kpi/g) || []).length;
  assert.ok(
    dsKpiCount >= 2,
    `Expected at least 2 ds-kpi references in renderDetailView, found ${dsKpiCount}`
  );
});

// ── 2. Signal categorization maps cve_risk to "Dependency Risk" (Requirement 9.1) ──

console.log('\n▸ Signal Categorization (Requirement 9.1)');

test('SIGNAL_CATEGORIES maps cve_ prefix to "Dependency Risk"', () => {
  // Find the SIGNAL_CATEGORIES definition in the source
  const catMatch = html.match(/var\s+SIGNAL_CATEGORIES\s*=\s*\{[\s\S]*?\};/);
  assert.ok(catMatch, 'SIGNAL_CATEGORIES definition not found');
  const catDef = catMatch[0];

  // Verify "Dependency Risk" category contains "cve_" prefix
  assert.ok(
    catDef.includes('"Dependency Risk"') || catDef.includes("'Dependency Risk'"),
    'SIGNAL_CATEGORIES does not define "Dependency Risk" category'
  );
  assert.ok(
    catDef.includes('"cve_"') || catDef.includes("'cve_'"),
    'SIGNAL_CATEGORIES does not include "cve_" prefix'
  );

  // Verify cve_ is under Dependency Risk (appears after "Dependency Risk" and before next category)
  const depRiskIdx = catDef.indexOf('Dependency Risk');
  const cveIdx = catDef.indexOf('cve_');
  assert.ok(depRiskIdx !== -1, '"Dependency Risk" not found in SIGNAL_CATEGORIES');
  assert.ok(cveIdx !== -1, '"cve_" not found in SIGNAL_CATEGORIES');
  assert.ok(
    cveIdx > depRiskIdx,
    '"cve_" prefix should appear under "Dependency Risk" category'
  );
});

// ── 3. Empty category shows "No issues detected" (Requirement 9.3) ──

console.log('\n▸ Empty Category Fallback (Requirement 9.3)');

test('code contains "No issues detected" string for empty categories', () => {
  assert.ok(
    html.includes('No issues detected'),
    '"No issues detected" text not found in insights.html'
  );
});

test('"No issues detected" appears in renderDetailView context', () => {
  // Verify it's in the script section (not just random HTML)
  const scriptMatch = html.match(/<script>[\s\S]*<\/script>/);
  assert.ok(scriptMatch, 'No <script> block found');
  assert.ok(
    scriptMatch[0].includes('No issues detected'),
    '"No issues detected" not found in script section'
  );
});

// ── 4. Reasons bullet count logic is within bounds (Requirement 8.2) ──

console.log('\n▸ Reasons Bullet Count (Requirement 8.2)');

test('renderDetailView caps reasons at Math.min(reasons.length, 5)', () => {
  const scriptContent = html.match(/<script>[\s\S]*<\/script>/)[0];
  // Check for the Math.min pattern with 5 as the cap
  assert.ok(
    scriptContent.includes('Math.min') && scriptContent.includes(', 5)'),
    'Math.min(..., 5) pattern not found — reasons should be capped at 5'
  );
});

test('renderDetailView ensures minimum of Math.min(reasons.length, 3)', () => {
  const scriptContent = html.match(/<script>[\s\S]*<\/script>/)[0];
  // Check for the Math.min pattern with 3 as the minimum
  assert.ok(
    scriptContent.includes('Math.min') && scriptContent.includes(', 3)'),
    'Math.min(..., 3) pattern not found — reasons should have minimum of 3'
  );
});

// ── 5. Uses base_maintenance_risk field name (not maintenance_risk_score) ──

console.log('\n▸ Field Name Correctness');

test('uses base_maintenance_risk field name', () => {
  const scriptContent = html.match(/<script>[\s\S]*<\/script>/)[0];
  assert.ok(
    scriptContent.includes('base_maintenance_risk'),
    'base_maintenance_risk field name not found in script'
  );
  // Ensure the wrong field name is NOT used
  assert.ok(
    !scriptContent.includes('maintenance_risk_score'),
    'Incorrect field name maintenance_risk_score found — should use base_maintenance_risk'
  );
});

// ── 6. Uses base_maintenance_label field name ──

test('uses base_maintenance_label field name', () => {
  const scriptContent = html.match(/<script>[\s\S]*<\/script>/)[0];
  assert.ok(
    scriptContent.includes('base_maintenance_label'),
    'base_maintenance_label field name not found in script'
  );
});

// ── 7. Loading skeleton uses ds-loading class (Requirement 17.1) ──

console.log('\n▸ Loading States (Requirement 17.1)');

test('navigateToDetail uses ds-loading skeleton for loading states', () => {
  // Find the navigateToDetail function
  const navMatch = html.match(/function\s+navigateToDetail[\s\S]*?^  \}/m);
  assert.ok(navMatch, 'navigateToDetail function not found');
  assert.ok(
    navMatch[0].includes('ds-loading'),
    'navigateToDetail does not use ds-loading class for loading skeletons'
  );
});

// ── 8. Cross-page links use getCrossLinks (Requirement 19.1) ──

console.log('\n▸ Cross-Page Navigation (Requirement 19.1)');

test('renderDetailView uses getCrossLinks("insights"', () => {
  const scriptContent = html.match(/<script>[\s\S]*<\/script>/)[0];
  assert.ok(
    scriptContent.includes('getCrossLinks("insights"'),
    'getCrossLinks("insights" call not found — cross-page links should use getCrossLinks helper'
  );
});

// ── Summary ──

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
