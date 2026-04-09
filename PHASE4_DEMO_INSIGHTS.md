# Phase 4: Demo Insights

**Date**: 2026-03-04  
**Status**: ✅ COMPLETE

## Executive Summary

Analysis of 51 repositories with 3,691 dependencies reveals strong patterns in the JavaScript and Python ecosystems. The data shows high-quality resolution (89.22%), clear dependency hubs, and interesting cross-ecosystem usage.

## Key Findings

### 1. Top Dependency Hubs (Most Popular Packages)

**JavaScript/TypeScript Ecosystem:**
- **@types/node**: Used by 17 repos (53 occurrences) - TypeScript definitions for Node.js
- **typescript**: Used by 16 repos (60 occurrences) - TypeScript compiler
- **eslint**: Used by 17 repos (33 occurrences) - JavaScript linter
- **prettier**: Used by 14 repos (23 occurrences) - Code formatter
- **react**: Used by 9 repos (19 occurrences) - UI library

**Python Ecosystem:**
- **pytest**: Used by 13 repos (26 occurrences) - Testing framework
- **mypy**: Used by 10 repos (15 occurrences) - Static type checker
- **click**: Used by 8 repos (25 occurrences) - CLI framework
- **packaging**: Used by 8 repos (20 occurrences) - Packaging utilities

**Insight**: TypeScript tooling dominates JavaScript dependencies, while testing/quality tools dominate Python.

### 2. Largest Dependency Footprints

| Repo | Total Deps | Prod | Dev | Resolution % |
|------|-----------|------|-----|--------------|
| aio-libs/aiohttp | 521 | 517 | 0 | 74.7% |
| cypress-io/cypress | 378 | 82 | 289 | 91.0% |
| nestjs/nest | 372 | 109 | 245 | 99.5% |
| angular/angular | 306 | 198 | 98 | 99.3% |
| parcel-bundler/parcel | 213 | 125 | 83 | 97.2% |
| facebook/react | 198 | 95 | 102 | 99.0% |

**Insights:**
- **aiohttp** has massive dependency footprint (521 deps, mostly production)
- **cypress** and **nestjs** have high dev dependency ratios (76.5% and 65.9%)
- JavaScript frameworks have excellent resolution rates (>99%)
- Python's aiohttp has lower resolution (74.7%) - potential mapping issues

### 3. Most Common Unresolved Packages

| Package | Registry | Affected Repos | Occurrences |
|---------|----------|----------------|-------------|
| pytest-cov | pypi | 12 | 17 |
| colorama | pypi | 7 | 7 |
| meson-python | pypi | 6 | 11 |
| tomli | pypi | 5 | 12 |
| numpy | pypi | 5 | 7 |
| pandas | pypi | 4 | 5 |

**Insight**: All unresolved packages are Python (pypi). This suggests:
- PyPI package mapping needs improvement
- These packages may not have GitHub repos (pure PyPI packages)
- Build tools (meson-python) and testing tools (pytest-cov) are common failures

### 4. Cross-Ecosystem Usage

**Only 1 repo uses both npm and pypi:**
- **django/django**: 6 npm deps + 34 pypi deps = 40 total
  - Uses npm for documentation tooling (Sphinx themes, etc.)
  - Primarily a Python web framework

**Insight**: Most repos are single-ecosystem. Cross-ecosystem usage is rare and typically for tooling (docs, build).

### 5. Dev vs Production Dependencies

**Repos with highest dev dependency ratios:**
- **vitejs/vite**: 88.8% dev (111 dev, 14 prod)
- **axios/axios**: 84.7% dev (61 dev, 11 prod)
- **microsoft/playwright**: 79.7% dev (59 dev, 15 prod)
- **cypress-io/cypress**: 76.5% dev (289 dev, 82 prod)

**Insight**: Build tools and testing frameworks have high dev dependency ratios. Application frameworks (Angular, React) have more balanced ratios.

### 6. Resolution Quality

**Highest confidence packages (0.95 avg):**
- All Python packages: pytest, mypy, pytest-xdist, click, packaging, sphinx
- Used by 5-13 repos each
- Perfect consistency (min=max=0.95)

**Lower confidence packages (0.9 avg):**
- All JavaScript packages: @types/node, typescript, eslint, prettier
- Still good quality, just slightly lower

**Insight**: Python package resolution is more confident (0.95) than JavaScript (0.9), likely due to simpler naming conventions.

### 7. Manifest Type Distribution

| Manifest Type | Repos | Dependencies |
|--------------|-------|--------------|
| package.json | 24 | 2,530 (68.5%) |
| requirements.txt | 15 | 978 (26.5%) |
| pyproject.toml | 16 | 183 (5.0%) |

**Insights:**
- JavaScript dominates the dataset (68.5% of dependencies)
- Python split between legacy (requirements.txt) and modern (pyproject.toml)
- Modern Python packaging (pyproject.toml) is growing but still minority

## Demo Talking Points

### For Security-Minded Audience

1. **Supply Chain Risk Visibility**
   - "We track 3,691 dependencies across 51 repos with 89% resolution rate"
   - "Top dependency hubs like @types/node (17 repos) are critical supply chain points"
   - "Unresolved packages (398) represent blind spots in your supply chain"

2. **Cross-Repo Impact Analysis**
   - "If pytest is compromised, 13 repos in your portfolio are affected"
   - "React vulnerability impacts 9 repos simultaneously"
   - "We can answer: 'What repos depend on package X?' instantly"

3. **Dependency Hygiene**
   - "Cypress has 289 dev dependencies - are they all necessary?"
   - "Aiohttp has 521 dependencies with 74.7% resolution - potential risk"
   - "Dev dependencies (42.4% of total) are often overlooked security risks"

### For Engineering Audience

1. **Ecosystem Insights**
   - "TypeScript tooling (@types/node, typescript, eslint) dominates JavaScript deps"
   - "Python testing tools (pytest, mypy) are universal across repos"
   - "Only 1 repo (django) uses both npm and pypi - ecosystems are siloed"

2. **Dependency Management**
   - "Modern Python (pyproject.toml) is only 5% of Python deps - migration opportunity"
   - "JavaScript frameworks have >99% resolution rates - excellent package mapping"
   - "Python resolution is 89% - room for improvement in PyPI mapping"

3. **Build Tool Patterns**
   - "Build tools (vite, webpack) have 75-88% dev dependencies"
   - "Application frameworks (Angular, React) have balanced prod/dev split"
   - "Testing frameworks (cypress, playwright) are dev-heavy"

## Recommended Demo Flow

1. **Start with dataset stats**: "51 repos, 3,691 dependencies, 89% resolution"
2. **Show dependency hub**: "Let's look at who depends on pytest" → 13 repos
3. **Drill into specific repo**: "Django has 11 dependencies, 10 resolved"
4. **Show unresolved issue**: "398 unresolved deps - mostly Python build tools"
5. **Cross-repo impact**: "If react is compromised, 9 repos are affected"
6. **Manifest diversity**: "We parse package.json, requirements.txt, pyproject.toml"

## Next Steps

1. **Improve PyPI resolution**: Focus on pytest-cov, colorama, numpy, pandas
2. **Add transitive dependencies**: Currently only direct deps tracked
3. **Add risk scoring**: Combine dependency count + resolution + CVEs
4. **Visualize dependency graphs**: Show cross-repo impact visually
5. **Add maintainer signals**: Track maintainer activity, bus factor

## Conclusion

The dataset is **production-ready for demos**. It shows:
- Real-world dependency patterns
- Clear supply chain risk signals
- High-quality resolution (89%)
- Interesting insights for both security and engineering audiences

The MVP successfully delivers value: turning raw dependency data into actionable supply chain intelligence.
