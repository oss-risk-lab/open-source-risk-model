/**
 * Unit tests for Homepage sections.
 * Validates: Requirements 1.1, 1.3, 1.6, 2.1, 3.2, 4.3, 5.3, 18.1, 18.2
 *
 * Run: node test/ui/test_homepage.js
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const htmlPath = path.join(__dirname, '..', '..', 'ui', 'index.html');
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

// ── 1. Hero Section (Requirements 1.1, 1.3, 1.6, 18.1, 18.2) ──

console.log('\n▸ Hero Section (Requirements 1.1, 1.3, 1.6, 18.1, 18.2)');

test('h1 text content is "Open Source Risk Intelligence"', () => {
  const h1Match = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  assert.ok(h1Match, 'No <h1> element found');
  const text = h1Match[1].replace(/<[^>]*>/g, '').trim();
  assert.strictEqual(text, 'Open Source Risk Intelligence');
});

test('CTA button label is "Scan a Repository"', () => {
  const btnMatch = html.match(/<button[^>]*>([\s\S]*?)<\/button>/i);
  assert.ok(btnMatch, 'No <button> element found');
  const text = btnMatch[1].replace(/<[^>]*>/g, '').trim();
  assert.strictEqual(text, 'Scan a Repository');
});

test('input placeholder is "numpy/numpy"', () => {
  const inputMatch = html.match(/<input[^>]*id=["']repoInput["'][^>]*>/i);
  assert.ok(inputMatch, 'No input with id="repoInput" found');
  const placeholderMatch = inputMatch[0].match(/placeholder=["']([^"']*)["']/);
  assert.ok(placeholderMatch, 'No placeholder attribute on repoInput');
  assert.strictEqual(placeholderMatch[1], 'numpy/numpy');
});

test('guidance text "Analyze any public GitHub repository in seconds." is present', () => {
  assert.ok(
    html.includes('Analyze any public GitHub repository in seconds.'),
    'Guidance text not found in HTML'
  );
});

test('hero has ds-card class', () => {
  const heroMatch = html.match(/<div[^>]*class=["'][^"']*hero[^"']*["'][^>]*>/i);
  assert.ok(heroMatch, 'No element with hero class found');
  assert.ok(
    heroMatch[0].includes('ds-card'),
    'Hero element does not have ds-card class'
  );
});

// ── 2. Capabilities Section (Requirement 2.1) ──

console.log('\n▸ Capabilities Section (Requirement 2.1)');

test('capability card count is between 4 and 6', () => {
  // Count actual card elements (not CSS selectors)
  const cardElements = html.match(/<div[^>]*class=["'][^"']*capability-card[^"']*["'][^>]*>/gi);
  assert.ok(cardElements, 'No capability-card elements found');
  assert.ok(
    cardElements.length >= 4 && cardElements.length <= 6,
    `Expected 4-6 capability-card elements, found ${cardElements.length}`
  );
});

// ── 3. How It Works Section (Requirement 3.2) ──

console.log('\n▸ How It Works Section (Requirement 3.2)');

test('How It Works has exactly 3 steps labeled "Analyze", "Evaluate", "Surface"', () => {
  const stepTitlePattern = /<div[^>]*class=["'][^"']*step-title[^"']*["'][^>]*>([\s\S]*?)<\/div>/gi;
  const stepTitles = [];
  let match;
  while ((match = stepTitlePattern.exec(html)) !== null) {
    stepTitles.push(match[1].replace(/<[^>]*>/g, '').trim());
  }
  assert.strictEqual(stepTitles.length, 3, `Expected 3 step-title elements, found ${stepTitles.length}`);
  assert.strictEqual(stepTitles[0], 'Analyze', `Step 1 should be "Analyze", got "${stepTitles[0]}"`);
  assert.strictEqual(stepTitles[1], 'Evaluate', `Step 2 should be "Evaluate", got "${stepTitles[1]}"`);
  assert.strictEqual(stepTitles[2], 'Surface', `Step 3 should be "Surface", got "${stepTitles[2]}"`);
});

// ── 4. Credibility Section — Stats API Fallback (Requirement 4.3) ──

console.log('\n▸ Credibility Section (Requirement 4.3)');

test('stats API fallback renders "100+" on failure', () => {
  // The fallback is in the catch block: kpiRepos textContent set to "100+"
  const fallbackPattern = /kpiRepos[^;]*["']100\+["']/;
  assert.ok(
    fallbackPattern.test(html),
    'Fallback value "100+" for kpiRepos not found in script'
  );
});

test('credibility section has 3 KPI blocks', () => {
  // Extract the credibilitySection div and count ds-kpi block occurrences within it
  const credStart = html.indexOf('id="credibilitySection"');
  assert.ok(credStart !== -1, 'credibilitySection element not found');

  // Slice a generous chunk from the credibility section
  const sectionSlice = html.slice(credStart, credStart + 2000);

  // Match elements with "ds-kpi" as a standalone class (not ds-kpi-value or ds-kpi-label)
  // The KPI block elements have class="ds-card ds-kpi" — ds-kpi followed by " (end of class attr)
  const kpiElements = sectionSlice.match(/<div[^>]*class="[^"]*ds-kpi"[^>]*>/gi);
  assert.ok(kpiElements, 'No ds-kpi block elements found in credibility section');
  assert.strictEqual(
    kpiElements.length, 3,
    `Expected 3 ds-kpi block elements in credibility section, found ${kpiElements.length}`
  );
});

// ── Summary ──

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
