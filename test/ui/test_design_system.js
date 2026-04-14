/**
 * Unit tests for design system CSS structure.
 * Validates: Requirements 5.2, 5.3, 16.1
 *
 * Run: node test/ui/test_design_system.js
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const cssPath = path.join(__dirname, '..', '..', 'ui', 'design-system.css');
const css = fs.readFileSync(cssPath, 'utf-8');

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

// ── 1. Required CSS custom properties (Requirement 5.2) ──

console.log('\n▸ CSS Custom Properties (Requirement 5.2)');

const requiredProperties = [
  // Background layers
  '--bg', '--bg-surface', '--bg-elevated', '--bg-overlay',
  // Borders
  '--border', '--border-subtle', '--border-emphasis',
  // Text
  '--text-primary', '--text-secondary', '--text-tertiary',
  // Accent
  '--accent', '--accent-muted',
  // Status colors
  '--status-high-bg', '--status-high-text', '--status-high-border',
  '--status-medium-bg', '--status-medium-text', '--status-medium-border',
  '--status-low-bg', '--status-low-text', '--status-low-border',
  '--status-mild-bg', '--status-mild-text',
  // Spacing
  '--sp-4', '--sp-8', '--sp-12', '--sp-16', '--sp-24', '--sp-32',
  // Radius
  '--radius-sm', '--radius-md', '--radius-lg', '--radius-pill',
  // Shadows
  '--shadow-sm', '--shadow-md',
  // Typography
  '--font-sans', '--font-mono',
  // Backward-compat aliases
  '--mono', '--sans', '--green', '--yellow', '--red',
  '--orange', '--indigo', '--muted', '--muted2',
];

for (const prop of requiredProperties) {
  test(`defines custom property ${prop}`, () => {
    // Match property definition like "--bg:" (with possible whitespace)
    const pattern = new RegExp(`${prop.replace(/[-]/g, '\\-')}\\s*:`);
    assert.ok(pattern.test(css), `Missing CSS custom property: ${prop}`);
  });
}

// ── 2. Required component classes (Requirement 5.3, 16.1) ──

console.log('\n▸ Component Classes (Requirements 5.3, 16.1)');

const requiredClasses = [
  '.ds-card',
  '.ds-section',
  '.ds-kpi',
  '.ds-risk-tag',
  '.ds-btn-primary',
  '.ds-btn-subtle',
  '.ds-nav',
  '.ds-loading',
  '.ds-spinner',
];

for (const cls of requiredClasses) {
  test(`defines component class ${cls}`, () => {
    // Match class selector like ".ds-card" (possibly with modifiers, pseudo-classes, or opening brace)
    const escaped = cls.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(escaped + '[\\s{:,]');
    assert.ok(pattern.test(css), `Missing component class: ${cls}`);
  });
}

// ── 3. Transition durations between 100ms and 200ms (Requirement 16.1) ──

console.log('\n▸ Transition Durations (Requirement 16.1)');

test('all transition durations use 150ms', () => {
  // Extract all transition shorthand and transition-duration values
  const transitionPattern = /transition\s*:[^;]+/g;
  const matches = css.match(transitionPattern) || [];
  assert.ok(matches.length > 0, 'No transition declarations found');

  // Extract duration values (e.g., "150ms", "0.15s")
  const durationPattern = /(\d+)ms/g;
  const durations = [];
  for (const match of matches) {
    let m;
    while ((m = durationPattern.exec(match)) !== null) {
      durations.push(parseInt(m[1], 10));
    }
  }

  assert.ok(durations.length > 0, 'No ms-based transition durations found');

  for (const ms of durations) {
    assert.ok(
      ms >= 100 && ms <= 200,
      `Transition duration ${ms}ms is outside 100-200ms range`
    );
  }
});

test('transitions use 150ms specifically', () => {
  const transitionPattern = /transition\s*:[^;]+/g;
  const matches = css.match(transitionPattern) || [];
  const durationPattern = /(\d+)ms/g;

  for (const match of matches) {
    let m;
    while ((m = durationPattern.exec(match)) !== null) {
      const ms = parseInt(m[1], 10);
      assert.strictEqual(ms, 150, `Expected 150ms but found ${ms}ms in: ${match.trim()}`);
    }
  }
});

// ── Summary ──

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
