/**
 * Unit tests for Graph page fixes.
 * Validates: Requirements 10.1, 11.2, 12.1
 *
 * Run: node test/ui/test_graph_page.js
 */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const htmlPath = path.join(__dirname, '..', '..', 'ui', 'graph.html');
const jsPath = path.join(__dirname, '..', '..', 'ui', 'graph-viz.js');
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

// ── 1. Panel overflow CSS (Requirement 10.1) ──

console.log('\n▸ Panel Overflow CSS (Requirement 10.1)');

test('.details-panel has max-height: calc(100vh - 60px)', () => {
  // Match the .details-panel rule block and check for max-height
  const panelMatch = html.match(/\.details-panel\s*\{[^}]*\}/);
  assert.ok(panelMatch, '.details-panel CSS rule not found in graph.html');
  const rule = panelMatch[0];
  assert.ok(
    /max-height\s*:\s*calc\(\s*100vh\s*-\s*60px\s*\)/.test(rule),
    '.details-panel missing max-height: calc(100vh - 60px)'
  );
});

test('.details-panel has overflow-y: auto', () => {
  const panelMatch = html.match(/\.details-panel\s*\{[^}]*\}/);
  assert.ok(panelMatch, '.details-panel CSS rule not found in graph.html');
  const rule = panelMatch[0];
  assert.ok(
    /overflow-y\s*:\s*auto/.test(rule),
    '.details-panel missing overflow-y: auto'
  );
});

test('.detail-item .value has word-break: break-word', () => {
  const valueMatch = html.match(/\.detail-item\s+\.value\s*\{[^}]*\}/);
  assert.ok(valueMatch, '.detail-item .value CSS rule not found in graph.html');
  const rule = valueMatch[0];
  assert.ok(
    /word-break\s*:\s*break-word/.test(rule),
    '.detail-item .value missing word-break: break-word'
  );
});

// ── 2. Responsive breakpoint (Requirement 10.3) ──

console.log('\n▸ Responsive Breakpoint (Requirement 10.3)');

test('responsive breakpoint at 1200px sets .details-panel width to 100% and max-height to 400px', () => {
  // Find the @media block for max-width: 1200px
  const mediaMatch = html.match(/@media\s*\(\s*max-width\s*:\s*1200px\s*\)\s*\{([\s\S]*?)\n\s*\}/);
  assert.ok(mediaMatch, '@media (max-width: 1200px) block not found in graph.html');
  const mediaBlock = mediaMatch[1];

  // Check .details-panel within the media block
  const detailsPanelMatch = mediaBlock.match(/\.details-panel\s*\{[^}]*\}/);
  assert.ok(detailsPanelMatch, '.details-panel rule not found in @media (max-width: 1200px) block');
  const rule = detailsPanelMatch[0];

  assert.ok(
    /width\s*:\s*100%/.test(rule),
    '.details-panel in responsive breakpoint missing width: 100%'
  );
  assert.ok(
    /max-height\s*:\s*400px/.test(rule),
    '.details-panel in responsive breakpoint missing max-height: 400px'
  );
});

// ── 3. Node Legend (Requirement 11.2) ──

console.log('\n▸ Node Legend (Requirement 11.2)');

test('node legend contains all 6 node types', () => {
  const nodeTypes = ['Repository', 'Release', 'Maintainer', 'CVE', 'Registry', 'Risk Factor'];
  for (const nodeType of nodeTypes) {
    assert.ok(
      html.includes(nodeType),
      `Node legend missing node type: ${nodeType}`
    );
  }
});

// ── 4. vis.js font configuration (Requirement 12.1) ──

console.log('\n▸ vis.js Font Configuration (Requirement 12.1)');

test('vis.js font configuration has vadjust: 20 default', () => {
  // Look for the nodes options block with font.vadjust: 20
  assert.ok(
    /vadjust\s*:\s*20/.test(js),
    'vis.js node font configuration missing vadjust: 20'
  );
});

test('vis.js font size is 11', () => {
  // Look for font size: 11 in the nodes options
  const nodesBlock = js.match(/nodes\s*:\s*\{[\s\S]*?font\s*:\s*\{[^}]*\}/);
  assert.ok(nodesBlock, 'nodes font configuration block not found in graph-viz.js');
  assert.ok(
    /size\s*:\s*11/.test(nodesBlock[0]),
    'vis.js node font size is not 11'
  );
});

// ── 5. Placeholder text (Requirement 13.3) ──

console.log('\n▸ Placeholder Text (Requirement 13.3)');

test('placeholder text for empty node selection is present', () => {
  const placeholder = 'Select a node to inspect its role, relationships, and risk context.';
  assert.ok(
    html.includes(placeholder),
    `Missing placeholder text: "${placeholder}"`
  );
});

// ── 6. Loading state spinner (Requirement 17.1) ──

console.log('\n▸ Loading State (Requirement 17.1)');

test('ds-spinner class is used for loading state in graph-viz.js', () => {
  assert.ok(
    js.includes('ds-spinner'),
    'ds-spinner class not found in graph-viz.js'
  );
});

// ── Summary ──

console.log(`\n${passed} passed, ${failed} failed\n`);
process.exit(failed > 0 ? 1 : 0);
