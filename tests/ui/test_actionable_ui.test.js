/**
 * Actionable Insights UI rendering tests (Phase 5).
 * Run with: node tests/ui/test_actionable_ui.test.js
 *
 * Validates: Requirements 8.1–8.5, 9.1–9.4, 10.1–10.4, 11.1–11.5
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const htmlPath = path.join(__dirname, '..', '..', 'ui', 'dependency-tree.html');
const jsPath = path.join(__dirname, '..', '..', 'ui', 'dependency-tree.js');
const html = fs.readFileSync(htmlPath, 'utf-8');
const js = fs.readFileSync(jsPath, 'utf-8');

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

// ─── HTML Panel Tests ────────────────────────────────────────────────

console.log('\n▸ Fix First Panel HTML (Requirements 8.1–8.5)');

test('fixFirstPanel element exists in HTML', () => {
  assert.ok(html.includes('id="fixFirstPanel"'), 'fixFirstPanel not found');
});

test('fixFirstContent container exists in HTML', () => {
  assert.ok(html.includes('id="fixFirstContent"'), 'fixFirstContent not found');
});

test('What to Fix First title exists', () => {
  assert.ok(html.includes('What to Fix First'), 'Section title not found');
});

test('fixFirstPanel starts hidden (display:none)', () => {
  assert.ok(html.includes('id="fixFirstPanel" class="panel" style="padding:var(--sp-8) var(--sp-16);margin-bottom:0;display:none;"'), 'Panel should start hidden');
});

console.log('\n▸ Risk Breakdown Panel HTML (Requirements 9.1–9.4)');

test('riskBreakdownPanel element exists in HTML', () => {
  assert.ok(html.includes('id="riskBreakdownPanel"'), 'riskBreakdownPanel not found');
});

test('riskBreakdownContent container exists in HTML', () => {
  assert.ok(html.includes('id="riskBreakdownContent"'), 'riskBreakdownContent not found');
});

test('Risk Breakdown title exists', () => {
  assert.ok(html.includes('>Risk Breakdown<'), 'Section title not found');
});

test('riskBreakdownPanel starts hidden (display:none)', () => {
  assert.ok(html.includes('id="riskBreakdownPanel" class="panel" style="padding:var(--sp-8) var(--sp-16);margin-bottom:0;display:none;"'), 'Panel should start hidden');
});

console.log('\n▸ Narrative Panel HTML (Requirements 10.1–10.4)');

test('narrativePanel element exists in HTML', () => {
  assert.ok(html.includes('id="narrativePanel"'), 'narrativePanel not found');
});

test('narrativeContent container exists in HTML', () => {
  assert.ok(html.includes('id="narrativeContent"'), 'narrativeContent not found');
});

test('Summary title exists', () => {
  assert.ok(html.includes('>Summary<'), 'Section title not found');
});

test('narrativePanel starts hidden (display:none)', () => {
  assert.ok(html.includes('id="narrativePanel" class="panel" style="padding:var(--sp-8) var(--sp-16);margin-bottom:0;display:none;"'), 'Panel should start hidden');
});

console.log('\n▸ Confidence Panel HTML (Requirements 11.1–11.5)');

test('confidencePanel element exists in HTML', () => {
  assert.ok(html.includes('id="confidencePanel"'), 'confidencePanel not found');
});

test('confidenceContent container exists in HTML', () => {
  assert.ok(html.includes('id="confidenceContent"'), 'confidenceContent not found');
});

test('Analysis Confidence title exists', () => {
  assert.ok(html.includes('Analysis Confidence'), 'Section title not found');
});

test('confidencePanel starts hidden (display:none)', () => {
  assert.ok(html.includes('id="confidencePanel" class="panel" style="padding:var(--sp-8) var(--sp-16);margin-bottom:0;display:none;"'), 'Panel should start hidden');
});

// ─── JS Function Tests ───────────────────────────────────────────────

console.log('\n▸ renderFixFirst JS (Requirements 8.1–8.5)');

test('renderFixFirst function exists', () => {
  assert.ok(js.includes('function renderFixFirst'), 'renderFixFirst not found');
});

test('renderFixFirst shows empty state message', () => {
  assert.ok(js.includes('No high-priority issues found.'), 'Empty state message not found');
});

test('renderFixFirst uses SCOPE_BADGE_CLASSES for scope badges', () => {
  assert.ok(js.includes('SCOPE_BADGE_CLASSES[rec.dependency_scope]'), 'SCOPE_BADGE_CLASSES usage not found in renderFixFirst');
});

test('renderFixFirst displays priority score as percentage', () => {
  assert.ok(js.includes('Priority Score:'), 'Priority Score label not found');
});

test('renderFixFirst renders rank numbers', () => {
  assert.ok(js.includes("(i + 1)"), 'Rank number rendering not found');
});

test('renderFixFirst renders action text', () => {
  assert.ok(js.includes('rec.action'), 'Action rendering not found');
});

console.log('\n▸ renderRiskBreakdown JS (Requirements 9.1–9.4)');

test('renderRiskBreakdown function exists', () => {
  assert.ok(js.includes('function renderRiskBreakdown'), 'renderRiskBreakdown not found');
});

test('renderRiskBreakdown applies muted opacity for zero-count clusters', () => {
  assert.ok(js.includes("cluster.count === 0"), 'Zero-count muting logic not found');
  assert.ok(js.includes("opacity:0.5"), 'Muted opacity style not found');
});

test('renderRiskBreakdown shows example packages', () => {
  assert.ok(js.includes('cluster.example_packages.join'), 'Example packages rendering not found');
});

test('renderRiskBreakdown shows risk contribution percentage', () => {
  assert.ok(js.includes('cluster.risk_contribution * 100'), 'Risk contribution percentage not found');
});

console.log('\n▸ renderNarrative JS (Requirements 10.1–10.4)');

test('renderNarrative function exists', () => {
  assert.ok(js.includes('function renderNarrative'), 'renderNarrative not found');
});

test('renderNarrative renders summary prominently', () => {
  assert.ok(js.includes('narrative.summary'), 'Summary rendering not found');
});

test('renderNarrative renders key findings as list items', () => {
  assert.ok(js.includes('narrative.key_findings'), 'Key findings rendering not found');
});

test('renderNarrative renders recommendation with accent styling', () => {
  assert.ok(js.includes('narrative.recommendation'), 'Recommendation rendering not found');
  assert.ok(js.includes('color:var(--accent)'), 'Accent color for recommendation not found');
});

console.log('\n▸ renderConfidence JS (Requirements 11.1–11.5)');

test('renderConfidence function exists', () => {
  assert.ok(js.includes('function renderConfidence'), 'renderConfidence not found');
});

test('renderConfidence uses color map for high/medium/low', () => {
  assert.ok(js.includes('high: "var(--green)"'), 'Green for high not found');
  assert.ok(js.includes('medium: "var(--yellow)"'), 'Yellow for medium not found');
  assert.ok(js.includes('low: "var(--red)"'), 'Red for low not found');
});

test('renderConfidence displays score as percentage', () => {
  assert.ok(js.includes('confidence.score * 100'), 'Score percentage calculation not found');
});

test('renderConfidence displays explanation text', () => {
  assert.ok(js.includes('confidence.explanation'), 'Explanation rendering not found');
});

test('renderConfidence displays label badge', () => {
  assert.ok(js.includes('confidence.label'), 'Label badge rendering not found');
});

// ─── Wiring Tests ────────────────────────────────────────────────────

console.log('\n▸ Data Flow Wiring (Requirements 7.5, 12.5)');

test('renderFixFirst is called after insight fetch', () => {
  assert.ok(js.includes('renderFixFirst(d)'), 'renderFixFirst not wired into data flow');
});

test('renderRiskBreakdown is called after insight fetch', () => {
  assert.ok(js.includes('renderRiskBreakdown(d)'), 'renderRiskBreakdown not wired into data flow');
});

test('renderNarrative is called after insight fetch', () => {
  assert.ok(js.includes('renderNarrative(d)'), 'renderNarrative not wired into data flow');
});

test('renderConfidence is called after insight fetch', () => {
  assert.ok(js.includes('renderConfidence(d)'), 'renderConfidence not wired into data flow');
});

test('existing renderScopeInsightCard still called', () => {
  assert.ok(js.includes('renderScopeInsightCard(d)'), 'renderScopeInsightCard should still be called');
});

// ─── Existing Panels Unaffected ──────────────────────────────────────

console.log('\n▸ Existing Panels Unaffected (Requirements 12.1–12.5)');

test('selectedNodePanel still exists', () => {
  assert.ok(html.includes('id="selectedNodePanel"'), 'selectedNodePanel should still exist');
});

test('treeSummaryPanel still exists', () => {
  assert.ok(html.includes('id="treeSummaryPanel"'), 'treeSummaryPanel should still exist');
});

test('scopeInsightPanel still exists', () => {
  assert.ok(html.includes('id="scopeInsightPanel"'), 'scopeInsightPanel should still exist');
});

test('renderScopeInsightCard function still exists', () => {
  assert.ok(js.includes('function renderScopeInsightCard'), 'renderScopeInsightCard should still exist');
});

// ─── Summary ─────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
