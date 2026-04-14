/**
 * Unit tests for Dependency Tree page enhancements.
 * Validates: Requirements 14.1, 14.2, 15.1, 17.1
 *
 * Run: node test/ui/test_dependency_tree_page.js
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

// ── 1. Summary Bar renders stat cards with ds-kpi classes (Requirement 14.1, 14.2) ──

console.log('\n▸ Summary Bar KPI Classes (Requirements 14.1, 14.2)');

test('stat cards use ds-kpi class', () => {
  assert.ok(
    js.includes('stat-card ds-kpi'),
    'stat-card elements should have ds-kpi class in dependency-tree.js'
  );
});

test('stat card number uses ds-kpi-value class', () => {
  assert.ok(
    js.includes('ds-kpi-value'),
    'stat card number elements should have ds-kpi-value class'
  );
});

test('stat card label uses ds-kpi-label class', () => {
  assert.ok(
    js.includes('ds-kpi-label'),
    'stat card label elements should have ds-kpi-label class'
  );
});

test('summary grid renders total deps, direct, transitive, high risk, vulnerable, max depth', () => {
  assert.ok(js.includes('"Total deps"'), 'Missing "Total deps" stat');
  assert.ok(js.includes('"Direct"'), 'Missing "Direct" stat');
  assert.ok(js.includes('"Transitive"'), 'Missing "Transitive" stat');
  assert.ok(js.includes('"High risk"'), 'Missing "High risk" stat');
  assert.ok(js.includes('"Vulnerable"'), 'Missing "Vulnerable" stat');
  assert.ok(js.includes('"Max depth"'), 'Missing "Max depth" stat');
});

// ── 2. Sidebar summary content area (Requirement 15.1) ──

console.log('\n▸ Sidebar Summary (Requirement 15.1)');

test('treeSummaryContent element exists in HTML', () => {
  assert.ok(
    html.includes('id="treeSummaryContent"'),
    'treeSummaryContent element not found in dependency-tree.html'
  );
});

test('sidebar summary includes ecosystem breakdown', () => {
  assert.ok(
    js.includes('sidebar-ecosystem-breakdown'),
    'Ecosystem breakdown section not found in dependency-tree.js'
  );
});

test('sidebar summary includes risk distribution', () => {
  assert.ok(
    js.includes('sidebar-risk-distribution'),
    'Risk distribution section not found in dependency-tree.js'
  );
});

test('collectTreeStats function exists for tree walking', () => {
  assert.ok(
    js.includes('function collectTreeStats'),
    'collectTreeStats helper function not found in dependency-tree.js'
  );
});

// ── 3. Loading state spinner (Requirement 17.1) ──

console.log('\n▸ Loading State Spinner (Requirement 17.1)');

test('loading state uses ds-spinner class', () => {
  assert.ok(
    html.includes('class="ds-spinner"'),
    'ds-spinner class not found in dependency-tree.html loading state'
  );
});

test('page-specific .spinner class is removed (uses ds-spinner from design system)', () => {
  // The page should NOT define its own .spinner CSS rule since ds-spinner is in design-system.css
  const spinnerRule = html.match(/\.spinner\s*\{[^}]*animation\s*:[^}]*spin/);
  assert.ok(
    !spinnerRule,
    'Page-specific .spinner CSS rule should be removed — ds-spinner from design-system.css is used instead'
  );
});

// ── 4. Design system CSS is imported (Requirement 20.1) ──

console.log('\n▸ Design System Import (Requirement 20.1)');

test('design-system.css is imported in dependency-tree.html', () => {
  assert.ok(
    html.includes('href="design-system.css"'),
    'design-system.css stylesheet link not found in dependency-tree.html'
  );
});

// ── Summary ──

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
