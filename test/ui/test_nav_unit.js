// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';

const { parseRepoParam, buildPageUrl, getCurrentPageId } = require('../../ui/nav-helpers.js');
const { renderNav, getCrossLinks } = require('../../ui/nav-render.js');

// ── Section 1: Pure helper unit tests ──

describe('parseRepoParam', () => {
  it('parses "?repo=numpy%2Fnumpy" → "numpy/numpy"', () => {
    expect(parseRepoParam('?repo=numpy%2Fnumpy')).toBe('numpy/numpy');
  });

  it('parses "?repo=pallets%2Fflask" → "pallets/flask"', () => {
    expect(parseRepoParam('?repo=pallets%2Fflask')).toBe('pallets/flask');
  });

  it('returns null for multiple slashes "?repo=a%2Fb%2Fc"', () => {
    expect(parseRepoParam('?repo=a%2Fb%2Fc')).toBeNull();
  });

  it('returns null for empty string ""', () => {
    expect(parseRepoParam('')).toBeNull();
  });

  it('returns null for whitespace "?repo=%20"', () => {
    expect(parseRepoParam('?repo=%20')).toBeNull();
  });

  it('returns null for just slash "?repo=%2F"', () => {
    expect(parseRepoParam('?repo=%2F')).toBeNull();
  });

  it('returns null for empty name "?repo=a%2F"', () => {
    expect(parseRepoParam('?repo=a%2F')).toBeNull();
  });

  it('returns null for empty owner "?repo=%2Fb"', () => {
    expect(parseRepoParam('?repo=%2Fb')).toBeNull();
  });
});

describe('buildPageUrl', () => {
  it('builds URL with repo param', () => {
    expect(buildPageUrl('graph.html', 'numpy/numpy')).toBe('graph.html?repo=numpy%2Fnumpy');
  });

  it('builds bare URL when repo is null', () => {
    expect(buildPageUrl('graph.html', null)).toBe('graph.html');
  });

  it('builds bare URL when repo is empty string', () => {
    expect(buildPageUrl('graph.html', '')).toBe('graph.html');
  });
});

describe('getCurrentPageId', () => {
  it('returns "insights" for pathname containing "insights.html"', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/ui/insights.html', search: '' },
      writable: true,
      configurable: true,
    });
    expect(getCurrentPageId()).toBe('insights');
  });

  it('returns "graph" for pathname containing "graph.html"', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/ui/graph.html', search: '' },
      writable: true,
      configurable: true,
    });
    expect(getCurrentPageId()).toBe('graph');
  });

  it('returns "dependency-tree" for pathname containing "dependency-tree.html"', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/ui/dependency-tree.html', search: '' },
      writable: true,
      configurable: true,
    });
    expect(getCurrentPageId()).toBe('dependency-tree');
  });

  it('returns "index" for pathname "/"', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/', search: '' },
      writable: true,
      configurable: true,
    });
    expect(getCurrentPageId()).toBe('index');
  });

  it('returns "index" for pathname "/ui/"', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/ui/', search: '' },
      writable: true,
      configurable: true,
    });
    expect(getCurrentPageId()).toBe('index');
  });
});

describe('getCrossLinks exclusion', () => {
  it('on graph page with repo: no "Open in Graph" link, has Insights and Dependency Tree', () => {
    const links = getCrossLinks('graph', 'numpy/numpy');
    const labels = links.map(l => l.label);
    expect(labels).not.toContain('Open in Graph');
    expect(labels).toContain('Open in Insights');
    expect(labels).toContain('Open in Dependency Tree');
  });

  it('on dependency-tree page with repo: no "Open in Dependency Tree" link', () => {
    const links = getCrossLinks('dependency-tree', 'numpy/numpy');
    const labels = links.map(l => l.label);
    expect(labels).not.toContain('Open in Dependency Tree');
  });

  it('on insights page with repo: no "Open in Insights" link', () => {
    const links = getCrossLinks('insights', 'numpy/numpy');
    const labels = links.map(l => l.label);
    expect(labels).not.toContain('Open in Insights');
  });

  it('on index page with repo: all three links present', () => {
    const links = getCrossLinks('index', 'numpy/numpy');
    expect(links.length).toBe(3);
  });
});

describe('renderNav idempotency', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div class="wrap"></div>';
  });

  it('calling renderNav twice produces exactly one <nav> element', () => {
    renderNav('index', null);
    renderNav('index', null);
    const navs = document.querySelectorAll('nav.ds-nav');
    expect(navs.length).toBe(1);
  });
});

// ── Section 2: DOM integration tests ──

describe('DOM integration: nav insertion as first child of .wrap', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div class="wrap"><div class="topbar">Top</div></div>';
  });

  it('nav is inserted as the first child of .wrap, before .topbar', () => {
    renderNav('index', null);
    const wrap = document.querySelector('.wrap');
    expect(wrap.firstChild.tagName).toBe('NAV');
    expect(wrap.firstChild.classList.contains('ds-nav')).toBe(true);
    expect(wrap.children[1].classList.contains('topbar')).toBe(true);
  });
});

describe('DOM integration: cross-link placement verification', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div class="wrap"></div>';
  });

  it('renderNav creates nav with brand span and links div', () => {
    renderNav('graph', 'numpy/numpy');
    const nav = document.querySelector('nav.ds-nav');
    expect(nav).not.toBeNull();

    const brand = nav.querySelector('.ds-nav-brand');
    expect(brand).not.toBeNull();
    expect(brand.textContent).toBe('Deep Signal');

    const linksDiv = nav.querySelector('.ds-nav-links');
    expect(linksDiv).not.toBeNull();

    const links = linksDiv.querySelectorAll('a.ds-nav-link');
    expect(links.length).toBe(4);
  });
});
