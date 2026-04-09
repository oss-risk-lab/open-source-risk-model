# Customer Use Case: TechCorp Security Team

## Customer Profile

**Company:** TechCorp (mid-size SaaS company)
**Team:** Security & Compliance (5 people)
**Challenge:** Managing supply chain risk across 200+ microservices
**Current Tools:** Dependabot, Snyk (frustrated with noise and lack of context)

---

## Day 1: Onboarding

### Setup (30 minutes)

Sarah, the Security Lead, connects TechCorp's GitHub organization:

```bash
# Configure GitHub integration
export GITHUB_TOKEN=<org_token>

# Ingest all org repos
python -m open_source_risk_model.cli.ingest \
  --input techcorp_repos.txt \
  --max-repos 200 \
  --concurrency 5
```

The system ingests:
- 200 microservices
- 15,000+ dependencies
- Resolves 85% to GitHub repos

---

## Day 2: First Crisis - Log4Shell Redux

### 8:00 AM - CVE Alert

Sarah gets an alert: **Critical vulnerability in `axios` (CVE-2024-XXXX)**

### Traditional Approach (2-3 hours):
1. Search GitHub for "axios" across all repos
2. Clone each repo locally
3. Check package.json files manually
4. Build a spreadsheet of affected services
5. Email each team lead
6. Wait for responses

### With Supply Chain Intelligence (5 minutes):

**Query 1: Impact Assessment**
```
"Which repos depend on axios?"
```

**Result:**
```
23 repos affected:
- api-gateway (prod)
- user-service (prod)
- payment-service (prod)
- analytics-worker (prod)
- notification-service (prod)
... 18 more
```

**Query 2: Prioritization**
```
"Show me dependency tree for payment-service"
```

**Result:**
```
payment-service
├── axios (VULNERABLE)
├── stripe-sdk
│   └── axios (VULNERABLE - transitive)
└── express
```

**Query 3: Blast Radius**
```
"Which services have the most dependencies?"
```

**Result:**
```
1. api-gateway: 342 deps (high risk)
2. payment-service: 156 deps (critical service)
3. user-service: 134 deps
```

### 8:15 AM - Action Plan

Sarah creates a prioritized remediation plan:

**Priority 1 (Critical):**
- payment-service (handles money + vulnerable)
- api-gateway (entry point + high complexity)

**Priority 2 (High):**
- user-service (auth-related)
- notification-service (customer-facing)

**Priority 3 (Medium):**
- 19 other services (internal tools, dev environments)

She sends targeted Slack messages to 4 team leads instead of 23.

---

## Week 2: Dependency Hygiene

### The Problem

TechCorp's CTO wants to reduce technical debt. Too many dependencies = slower builds, more vulnerabilities, higher maintenance.

### Query: Dependency Bloat Analysis

**Query 1: Find the worst offenders**
```
"Which repos have the most dependencies?"
```

**Result:**
```
1. legacy-monolith: 847 deps (includes dev/test)
2. api-gateway: 342 deps
3. admin-dashboard: 298 deps
```

**Query 2: Drill into the monolith**
```
"Show me dependencies for legacy-monolith with scope=all"
```

**Result:**
```
Production: 234 deps
Build/Dev: 412 deps
Optional extras: 201 deps

Top optional extras:
- testing frameworks (jest, mocha, chai, sinon, etc.)
- linting tools (eslint, prettier, tslint, etc.)
- documentation (typedoc, jsdoc, etc.)
```

### Action: Cleanup Initiative

Sarah works with the team to:
1. Remove unused optional extras (saves 201 deps)
2. Consolidate testing frameworks (saves 50 deps)
3. Move dev dependencies to separate package (cleaner prod builds)

**Result:** Monolith goes from 847 → 234 production deps (72% reduction)

---

## Month 1: Compliance Audit

### The Problem

TechCorp needs SOC2 compliance. Auditors ask:

> "How do you track and manage third-party software dependencies?"

### Traditional Approach:
- Generate SBOMs for each repo manually
- Create spreadsheets
- Hope nothing changes before the audit

### With Supply Chain Intelligence:

**Query 1: Generate portfolio report**
```
"Show me dataset statistics"
```

**Result:**
```json
{
  "total_repos": 200,
  "total_dependencies": 15,234,
  "unique_packages": 3,421,
  "resolution_rate": 85.2%,
  "repos_with_vulnerabilities": 47
}
```

**Query 2: Unresolved dependencies (blind spots)**
```
"List unresolved dependencies"
```

**Result:**
```
2,254 unresolved dependencies across 89 repos

Top unresolved:
- @internal/shared-utils (internal package, expected)
- legacy-db-driver (unmaintained, no GitHub repo)
- custom-auth-lib (internal, expected)
```

**Query 3: High-risk patterns**
```
"Which repos depend on unmaintained packages?"
```

Sarah can now answer auditor questions with data:
- ✅ "We track 15,234 dependencies across 200 repos"
- ✅ "85% are resolved to source repos for monitoring"
- ✅ "We have 47 repos with known vulnerabilities (remediation in progress)"
- ✅ "We can identify blast radius of any vulnerability in under 5 minutes"

**Audit passes.** ✅

---

## Month 3: Strategic Planning

### The Problem

Engineering leadership wants to standardize on fewer dependencies to reduce maintenance burden.

### Query: Dependency Overlap Analysis

**Query 1: Most common dependencies**
```
"Which packages are used by the most repos?"
```

**Result:**
```
1. express: 87 repos (HTTP framework)
2. lodash: 76 repos (utilities)
3. axios: 65 repos (HTTP client)
4. moment: 54 repos (dates - DEPRECATED!)
5. winston: 52 repos (logging)
```

**Query 2: Deprecated package usage**
```
"Which repos still use moment?"
```

**Result:**
```
54 repos using moment (deprecated in favor of date-fns)

Oldest usage:
- legacy-monolith (added 2018)
- user-service (added 2019)
- payment-service (added 2019)
```

### Action: Standardization Initiative

Engineering creates a "blessed dependencies" list:
- ✅ express (standard HTTP framework)
- ✅ date-fns (replace moment)
- ✅ axios (standard HTTP client)
- ❌ moment (deprecated)
- ❌ request (deprecated)

Sarah can track migration progress:
```
"How many repos still use moment?"
→ 54 repos (Week 1)
→ 41 repos (Week 4)
→ 28 repos (Week 8)
→ 12 repos (Week 12)
```

---

## Month 6: Proactive Monitoring

### The Setup

Sarah sets up automated alerts (future feature):

```yaml
alerts:
  - name: "New critical CVE"
    trigger: "CVE severity = CRITICAL"
    action: "Slack #security-alerts"
  
  - name: "Dependency bloat"
    trigger: "repo dependencies > 300"
    action: "Email tech-leads"
  
  - name: "Unmaintained dependency"
    trigger: "package last_commit > 2 years"
    action: "Create Jira ticket"
```

### The Payoff

**Before:** Reactive firefighting, manual tracking, spreadsheet hell

**After:** 
- ✅ 5-minute impact assessment for any vulnerability
- ✅ Proactive dependency hygiene
- ✅ Compliance-ready reporting
- ✅ Data-driven technical debt reduction
- ✅ Strategic planning with real data

**Time saved:** ~10 hours/week for security team

---

## ROI Calculation

### Time Savings

**Per vulnerability incident:**
- Before: 2-3 hours (manual search + spreadsheets)
- After: 5 minutes (instant query)
- Savings: ~2.5 hours per incident
- Incidents per month: ~8
- **Monthly savings: 20 hours**

**Compliance audits:**
- Before: 40 hours (manual SBOM generation + documentation)
- After: 4 hours (automated reports)
- **Annual savings: 36 hours**

**Dependency hygiene:**
- Before: Ad-hoc, reactive
- After: Continuous monitoring
- **Value: Reduced attack surface, faster builds**

### Cost Avoidance

**Security incidents prevented:**
- Faster patching = reduced exposure window
- Better prioritization = critical issues fixed first
- **Estimated value: $50K-$500K per prevented breach**

**Compliance:**
- Failed audit = delayed sales, customer churn
- **Estimated value: $100K+ in avoided delays**

### Total Value

**Conservative estimate:**
- Time savings: $30K/year (20 hrs/month × $150/hr)
- Risk reduction: $50K/year (prevented incidents)
- Compliance: $100K/year (avoided delays)
- **Total: $180K/year**

**Product cost:** $20K/year (hypothetical)

**ROI: 9x**

---

## Key Differentiators

### vs. Dependabot
- ❌ Dependabot: One repo at a time, no cross-repo analysis
- ✅ This product: Portfolio-wide intelligence, impact analysis

### vs. Snyk
- ❌ Snyk: Vulnerability scanning, limited dependency intelligence
- ✅ This product: Full dependency graph, natural language queries, strategic insights

### vs. Manual Tracking
- ❌ Manual: Spreadsheets, stale data, hours of work
- ✅ This product: Real-time queries, always up-to-date, seconds to answer

---

## Customer Testimonial (Hypothetical)

> "Before, every CVE alert was a 3-hour fire drill. Now I can assess impact in 5 minutes and focus on what actually matters. This tool paid for itself in the first month."
> 
> — Sarah Chen, Security Lead @ TechCorp

---

## Expansion Opportunities

After 6 months, TechCorp wants:
1. **GitHub App integration** - Auto-ingest new repos
2. **Slack bot** - Query from Slack
3. **Custom risk scoring** - TechCorp-specific risk policies
4. **Automated remediation** - Auto-create PRs for updates
5. **Executive dashboards** - Risk metrics for leadership

**Upsell potential: $50K/year → $100K/year**

---

## Summary

This product transforms supply chain security from:
- **Reactive** → Proactive
- **Manual** → Automated
- **Siloed** → Portfolio-wide
- **Opaque** → Transparent

The value isn't just in answering questions faster - it's in enabling questions that were previously impossible to answer.
