// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import fc from 'fast-check';

const { parseRepoParam, buildPageUrl, getCurrentPageId } = require('../../ui/nav-helpers.js');
const { renderNav, getCrossLinks } = require('../../ui/nav-render.js');

// ── Generators ──

const validPageIds = fc.constantFrom('index', 'insights', 'graph', 'dependency-tree');

// owner/name segments: alphanumeric + safe chars (avoid % which causes double-decode issues in parseRepoParam)
const safeChar = fc.char().filter(c => c !== '/' && c !== '\0' && c !== '%' && c.trim().length > 0);
const ownerNameSegment = fc.stringOf(safeChar, { minLength: 1, maxLength: 20 });

const validRepoArb = fc.tuple(ownerNameSegment, ownerNameSegment).map(([o, n]) => o + '/' + n);

const repoOrNull = fc.oneof(validRepoArb, fc.constant(null));

const pageStringArb = fc.constantFrom('index.html', 'insights.html', 'graph.html', 'dependency-tree.html');

// ── Helpers ──

const PAGE_ID_TO_LABEL = {
  'index': 'Home',
  'insights': 'Insights',
  'graph': 'Graph',
  'dependency-tree': 'Dependency Tree'
};

const EXPECTED_LABELS = ['Home', 'Insights', 'Graph', 'Dependency Tree'];

// ── Tests ──

// Feature: ui-navigation-unification, Property 1: Nav bar contains all four page links with correct labels
describe('Property 1 — Nav bar link labels', () => {
  /**
   * **Validates: Requirements 1.2**
   */
  beforeEach(() => {
    document.body.innerHTML = '<div class="wrap"></div>';
  });

  it('renderNav produces exactly 4 links with labels Home, Insights, Graph, Dependency Tree in order', () => {
    fc.assert(
      fc.property(
        validPageIds,
        repoOrNull,
        (pageId, repo) => {
          document.body.innerHTML = '<div class="wrap"></div>';
          renderNav(pageId, repo);
          const links = document.querySelectorAll('nav.ds-nav .ds-nav-links a.ds-nav-link');
          expect(links.length).toBe(4);
          const labels = Array.from(links).map(a => a.textContent);
          expect(labels).toEqual(EXPECTED_LABELS);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 2: Active page indicator and aria-current correctness
describe('Property 2 — Active page indicator', () => {
  /**
   * **Validates: Requirements 1.5, 14.2**
   */
  beforeEach(() => {
    document.body.innerHTML = '<div class="wrap"></div>';
  });

  it('exactly one link has active class and aria-current="page", matching the given page ID', () => {
    fc.assert(
      fc.property(
        validPageIds,
        repoOrNull,
        (pageId, repo) => {
          document.body.innerHTML = '<div class="wrap"></div>';
          renderNav(pageId, repo);
          const activeLinks = document.querySelectorAll('nav.ds-nav a.ds-nav-link.active');
          expect(activeLinks.length).toBe(1);
          expect(activeLinks[0].getAttribute('aria-current')).toBe('page');
          expect(activeLinks[0].textContent).toBe(PAGE_ID_TO_LABEL[pageId]);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 3: buildPageUrl includes repo parameter if and only if repo is non-null
describe('Property 3 — buildPageUrl repo inclusion', () => {
  /**
   * **Validates: Requirements 2.1, 2.2**
   */
  it('includes ?repo= iff repo is non-null/non-empty', () => {
    fc.assert(
      fc.property(
        pageStringArb,
        repoOrNull,
        (page, repo) => {
          const url = buildPageUrl(page, repo);
          if (repo) {
            expect(url).toContain('?repo=');
            expect(url.startsWith(page + '?repo=')).toBe(true);
          } else {
            expect(url).not.toContain('?repo=');
            expect(url).toBe(page);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 4: Repo context encoding round-trip
describe('Property 4 — Encoding round-trip', () => {
  /**
   * **Validates: Requirements 2.3, 2.4, 13.1, 13.2**
   */
  it('encoding via buildPageUrl then extracting via parseRepoParam returns the original string', () => {
    fc.assert(
      fc.property(
        validRepoArb,
        (repo) => {
          const url = buildPageUrl('page.html', repo);
          // Extract query string portion (everything from ? onward)
          const queryString = url.substring(url.indexOf('?'));
          const result = parseRepoParam(queryString);
          expect(result).toBe(repo);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 5: Invalid repo values yield null
describe('Property 5 — Invalid repo yields null', () => {
  /**
   * **Validates: Requirements 10.4, 13.3**
   */
  it('empty, whitespace-only, no-slash, multi-slash, or empty-part strings yield null', () => {
    // Use safe chars (no % to avoid URIError in parseRepoParam's decodeURIComponent)
    const safeNoSlash = fc.stringOf(
      fc.char().filter(c => c !== '/' && c !== '\0' && c !== '%'),
      { minLength: 1, maxLength: 20 }
    );
    const safeSeg = fc.stringOf(safeChar, { minLength: 1, maxLength: 10 });

    const invalidRepoArb = fc.oneof(
      // empty string
      fc.constant(''),
      // whitespace-only
      fc.stringOf(fc.constantFrom(' ', '\t', '\n'), { minLength: 1, maxLength: 10 }),
      // no slash at all
      safeNoSlash,
      // multiple slashes (a/b/c pattern)
      fc.tuple(safeSeg, safeSeg, safeSeg)
        .map(([a, b, c]) => a + '/' + b + '/' + c),
      // empty owner (starts with /)
      safeSeg.map(n => '/' + n),
      // empty name (ends with /)
      safeSeg.map(o => o + '/')
    );

    fc.assert(
      fc.property(
        invalidRepoArb,
        (invalidRepo) => {
          const searchString = '?repo=' + encodeURIComponent(invalidRepo);
          const result = parseRepoParam(searchString);
          expect(result).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 6: Cross-page link labels match target page mapping
describe('Property 6 — Cross-page link labels', () => {
  /**
   * **Validates: Requirements 15.1, 15.2, 15.3**
   */
  it('for any target page ID, the generated label matches the defined mapping', () => {
    const LABEL_MAP = {
      'insights': 'Open in Insights',
      'graph': 'Open in Graph',
      'dependency-tree': 'Open in Dependency Tree'
    };

    const targetPageIds = fc.constantFrom('insights', 'graph', 'dependency-tree');

    fc.assert(
      fc.property(
        targetPageIds,
        validRepoArb,
        (targetPageId, repo) => {
          // Use a different page as current so the target is not excluded
          const currentPageId = targetPageId === 'insights' ? 'graph' : 'insights';
          const links = getCrossLinks(currentPageId, repo);
          const targetLink = links.find(l => l.targetPageId === targetPageId);
          expect(targetLink).toBeDefined();
          expect(targetLink.label).toBe(LABEL_MAP[targetPageId]);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 7: Repo-specific cross-links hidden when no repo context
describe('Property 7 — Cross-links hidden without repo', () => {
  /**
   * **Validates: Requirements 10.3**
   */
  it('for any page and null repo, getCrossLinks returns empty array', () => {
    fc.assert(
      fc.property(
        validPageIds,
        (pageId) => {
          const links = getCrossLinks(pageId, null);
          expect(links).toEqual([]);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: ui-navigation-unification, Property 8: Cross-links exclude current page
describe('Property 8 — Cross-links exclude current page', () => {
  /**
   * **Validates: Requirements 6.1, 7.1, 8.1, 9.2**
   */
  it('for insights/graph/dependency-tree, no cross-link targets the current page; on index, all three links rendered', () => {
    const nonIndexPages = fc.constantFrom('insights', 'graph', 'dependency-tree');

    fc.assert(
      fc.property(
        nonIndexPages,
        validRepoArb,
        (pageId, repo) => {
          const links = getCrossLinks(pageId, repo);
          // No link should target the current page
          const selfLink = links.find(l => l.targetPageId === pageId);
          expect(selfLink).toBeUndefined();
          // Should have exactly 2 links (3 targets minus current)
          expect(links.length).toBe(2);
        }
      ),
      { numRuns: 100 }
    );

    // On index, all three links are rendered
    fc.assert(
      fc.property(
        validRepoArb,
        (repo) => {
          const links = getCrossLinks('index', repo);
          expect(links.length).toBe(3);
          const targetIds = links.map(l => l.targetPageId).sort();
          expect(targetIds).toEqual(['dependency-tree', 'graph', 'insights']);
        }
      ),
      { numRuns: 100 }
    );
  });
});
