# Product Roadmap: From Demo to Customer Value

## Current State (What You Have)

✅ **Core Infrastructure**
- SQLite database with dependency data
- Query API with 11 intents
- Natural language query interface
- 47 repos ingested with 3,313 dependencies
- Dependency scope filtering (prod/build/all)

✅ **Basic UI**
- Query interface (ui/query.html)
- Dependency explorer
- Graph visualization

---

## Gap Analysis: Demo → Production

### What's Missing for TechCorp Use Case

| Use Case | Current State | Gap | Priority |
|----------|--------------|-----|----------|
| **Crisis Response** | Can query "who uses X" | No CVE integration, no alerts | HIGH |
| **Impact Assessment** | Can show dependents | No severity/priority scoring | HIGH |
| **Compliance Reporting** | Can query stats | No export/reports, no audit trail | MEDIUM |
| **Dependency Hygiene** | Can list deps | No trend tracking, no recommendations | MEDIUM |
| **Automated Ingestion** | Manual CLI | No GitHub App, no auto-sync | HIGH |
| **Team Collaboration** | Single-user | No auth, no sharing, no notifications | MEDIUM |

---

## Phased Roadmap

### Phase 1: MVP for Single Customer (4-6 weeks)

**Goal:** Get TechCorp from "interested" to "paying customer"

#### Week 1-2: Crisis Response Essentials

**1.1 CVE Integration (Backend)**
```python
# New intent: search_cves
{
  "intent": "search_cves",
  "parameters": {
    "package_name": "axios",
    "severity": "CRITICAL"
  }
}

# Returns:
{
  "cves": [
    {
      "id": "CVE-2024-XXXX",
      "severity": "CRITICAL",
      "affected_versions": "< 1.6.0",
      "fixed_version": "1.6.0",
      "published": "2024-01-15"
    }
  ],
  "affected_repos": [
    {"repo": "payment-service", "version": "1.5.2", "vulnerable": true},
    {"repo": "api-gateway", "version": "1.6.1", "vulnerable": false}
  ]
}
```

**Infrastructure:**
- Add `repo_cves` table (already exists ✅)
- Add CVE → package mapping
- Integrate with OSV.dev API (already have CVE fetcher ✅)
- Add version comparison logic

**UI Changes:**
- Add "CVE Impact" view
- Show vulnerable repos in red
- Add "Export to CSV" button

**1.2 Priority Scoring**
```python
# Add risk_score to repos
risk_score = (
  dependency_count * 0.3 +
  cve_count * 0.4 +
  unresolved_deps * 0.2 +
  age_of_deps * 0.1
)
```

**UI Changes:**
- Add risk badges (🔴 Critical, 🟡 High, 🟢 Low)
- Sort results by risk score
- Add "Priority" column to tables

#### Week 3-4: Automated Ingestion

**2.1 GitHub App**
```yaml
# GitHub App permissions:
- repos: read
- metadata: read
- webhooks: repo push, repo created

# Webhook handlers:
- on_push: Re-ingest if manifest changed
- on_repo_created: Auto-ingest new repo
```

**Infrastructure:**
- Create GitHub App
- Add webhook endpoint to API
- Add background job queue (Celery or similar)
- Add ingestion status tracking

**UI Changes:**
- Add "Connected Repos" dashboard
- Show last sync time
- Add "Sync Now" button

**2.2 Incremental Updates**
```python
# Instead of full re-ingestion:
- Check manifest file hash
- Only re-parse if changed
- Update only changed dependencies
```

**Infrastructure:**
- Add `manifest_hash` column
- Add `last_synced_at` column
- Optimize ingestion for speed

#### Week 5-6: Compliance & Reporting

**3.1 Export Capabilities**
```python
# New endpoints:
GET /api/reports/sbom/{repo}  # SBOM export
GET /api/reports/portfolio    # Portfolio summary
GET /api/reports/audit-trail  # Change history
```

**Infrastructure:**
- Add SBOM generation (CycloneDX format)
- Add audit log table
- Add report templates

**UI Changes:**
- Add "Reports" section
- Add "Download SBOM" button
- Add "Audit Trail" view

**3.2 Saved Queries & Dashboards**
```python
# Save common queries:
saved_queries = [
  {
    "name": "Critical CVEs",
    "query": "search_cves",
    "params": {"severity": "CRITICAL"},
    "schedule": "daily"
  }
]
```

**Infrastructure:**
- Add `saved_queries` table
- Add query scheduler
- Add email notifications

---

### Phase 2: Multi-Tenant SaaS (8-12 weeks)

**Goal:** Scale from 1 customer to 10 customers

#### Week 7-10: Multi-Tenancy

**4.1 Authentication & Authorization**
```python
# Add user management:
- Organizations (TechCorp, AcmeCo, etc.)
- Users (sarah@techcorp.com)
- Roles (admin, viewer, security-lead)
- API keys (for CI/CD integration)
```

**Infrastructure:**
- Migrate SQLite → PostgreSQL
- Add `organizations` table
- Add `users` table
- Add `api_keys` table
- Add row-level security (RLS)

**UI Changes:**
- Add login page
- Add org switcher
- Add user management
- Add API key management

**4.2 Data Isolation**
```sql
-- Every query becomes:
SELECT * FROM repo_dependencies 
WHERE org_id = current_user.org_id
  AND repo_full_name = ?
```

**Infrastructure:**
- Add `org_id` to all tables
- Add database indexes on `org_id`
- Add query middleware for RLS

#### Week 11-14: Collaboration Features

**5.1 Team Features**
```python
# Add collaboration:
- Comments on repos/dependencies
- @mentions in comments
- Shared dashboards
- Team notifications
```

**Infrastructure:**
- Add `comments` table
- Add `notifications` table
- Add WebSocket support for real-time updates

**UI Changes:**
- Add comment threads
- Add notification bell
- Add shared dashboard view

**5.2 Slack Integration**
```python
# Slack bot:
/supply-chain who-uses axios
/supply-chain cve-impact CVE-2024-XXXX
/supply-chain repo-risk payment-service
```

**Infrastructure:**
- Create Slack app
- Add Slack webhook handlers
- Add Slack OAuth flow

---

### Phase 3: Enterprise Features (12-16 weeks)

**Goal:** Land enterprise customers ($100K+ ARR)

#### Week 15-18: Advanced Analytics

**6.1 Trend Analysis**
```python
# Track changes over time:
- Dependency count trends
- CVE exposure trends
- Resolution rate trends
- Risk score trends
```

**Infrastructure:**
- Add time-series tables
- Add daily snapshots
- Add trend calculation queries

**UI Changes:**
- Add trend charts (Chart.js or D3)
- Add "Compare dates" feature
- Add "Export trends" button

**6.2 Custom Risk Policies**
```yaml
# Customer-defined policies:
policies:
  - name: "No deprecated packages"
    rule: "package.deprecated == true"
    severity: "HIGH"
    action: "block_deploy"
  
  - name: "Max dependency count"
    rule: "repo.dependency_count > 300"
    severity: "MEDIUM"
    action: "notify_team"
```

**Infrastructure:**
- Add policy engine
- Add policy evaluation
- Add policy violation tracking

#### Week 19-20: CI/CD Integration

**7.1 GitHub Actions Integration**
```yaml
# .github/workflows/supply-chain-check.yml
- uses: supply-chain-intel/action@v1
  with:
    api-key: ${{ secrets.SUPPLY_CHAIN_KEY }}
    fail-on: critical-cve
    report: true
```

**Infrastructure:**
- Create GitHub Action
- Add CI/CD API endpoints
- Add status check integration

**7.2 Pre-commit Hooks**
```bash
# Block commits with vulnerable deps
git commit -m "Add feature"
→ ❌ Blocked: axios@1.5.2 has critical CVE
→ Run: npm update axios
```

**Infrastructure:**
- Create CLI tool
- Add local scanning
- Add policy enforcement

---

## UI/UX Optimization

### Current UI Issues

1. **Too generic** - Looks like a database query tool, not a security product
2. **No context** - Results are just tables, no insights
3. **No workflows** - User has to know what to query
4. **No persistence** - Can't save queries or results

### Optimized UI Architecture

```
┌─────────────────────────────────────────────────────┐
│ Top Nav: [Dashboard] [Repos] [CVEs] [Reports]      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Dashboard (Landing Page)                           │
│  ┌─────────────────┐  ┌─────────────────┐         │
│  │ 🔴 Critical     │  │ 📊 Portfolio    │         │
│  │ 3 CVEs          │  │ 200 repos       │         │
│  │ 23 repos        │  │ 15K deps        │         │
│  └─────────────────┘  └─────────────────┘         │
│                                                     │
│  Recent Alerts                                      │
│  🔴 axios CVE-2024-XXXX (23 repos affected)        │
│  🟡 moment deprecated (54 repos using)             │
│                                                     │
│  Quick Actions                                      │
│  [Check CVE Impact] [View High-Risk Repos]         │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Repos View (List of all repos)                    │
│  ┌──────────────────────────────────────────────┐  │
│  │ Repo              Risk  Deps  CVEs  Updated  │  │
│  │ payment-service   🔴    156   3     2h ago   │  │
│  │ api-gateway       🟡    342   1     5h ago   │  │
│  │ user-service      🟢    134   0     1d ago   │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  [Filter by Risk] [Filter by Team] [Export]        │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  CVE View (Active vulnerabilities)                  │
│  ┌──────────────────────────────────────────────┐  │
│  │ CVE-2024-XXXX (axios)                        │  │
│  │ Severity: CRITICAL | Affected: 23 repos      │  │
│  │                                              │  │
│  │ Affected Repos:                              │  │
│  │ • payment-service (v1.5.2) → Update to 1.6.0│  │
│  │ • api-gateway (v1.5.2) → Update to 1.6.0    │  │
│  │                                              │  │
│  │ [Create Remediation Plan] [Export List]     │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### Key UI Improvements

**1. Dashboard-First Design**
- Show critical info immediately
- No need to query for common questions
- Proactive alerts, not reactive queries

**2. Contextual Actions**
- "Create Jira ticket" button on CVE view
- "Email team leads" button on affected repos
- "Export remediation plan" button

**3. Guided Workflows**
```
CVE Alert → Impact Assessment → Prioritization → Remediation → Verification
```

**4. Smart Defaults**
- Auto-sort by risk score
- Auto-filter to critical/high
- Auto-refresh every 5 minutes

**5. Visual Hierarchy**
```
🔴 Critical (immediate action)
🟡 High (this week)
🟢 Medium (this month)
⚪ Low (backlog)
```

---

## Infrastructure Requirements

### Current: Single-User Demo
```
┌──────────┐
│ SQLite   │
│ (local)  │
└──────────┘
     ↑
┌──────────┐
│ FastAPI  │
│ (local)  │
└──────────┘
     ↑
┌──────────┐
│ Browser  │
└──────────┘
```

### Phase 1: Single Customer (MVP)
```
┌──────────────┐
│ PostgreSQL   │
│ (AWS RDS)    │
└──────────────┘
       ↑
┌──────────────┐     ┌──────────────┐
│ FastAPI      │────→│ Redis        │
│ (AWS ECS)    │     │ (cache)      │
└──────────────┘     └──────────────┘
       ↑
┌──────────────┐
│ CloudFront   │
│ (CDN)        │
└──────────────┘
       ↑
┌──────────────┐
│ React App    │
│ (S3 + CF)    │
└──────────────┘
```

**Cost:** ~$200/month

### Phase 2: Multi-Tenant SaaS
```
┌──────────────┐     ┌──────────────┐
│ PostgreSQL   │     │ S3           │
│ (RDS Multi-AZ│     │ (backups)    │
└──────────────┘     └──────────────┘
       ↑                    ↑
┌──────────────┐     ┌──────────────┐
│ FastAPI      │────→│ Redis        │
│ (ECS Fargate)│     │ (ElastiCache)│
│ Auto-scaling │     └──────────────┘
└──────────────┘            ↑
       ↑             ┌──────────────┐
┌──────────────┐    │ Celery       │
│ ALB          │    │ (background) │
│ (load bal)   │    └──────────────┘
└──────────────┘
       ↑
┌──────────────┐
│ CloudFront   │
└──────────────┘
       ↑
┌──────────────┐
│ React App    │
└──────────────┘
```

**Cost:** ~$1,000/month

### Phase 3: Enterprise
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ PostgreSQL   │     │ S3           │     │ CloudWatch   │
│ (RDS Multi-AZ│     │ (backups)    │     │ (monitoring) │
│ Read replicas│     └──────────────┘     └──────────────┘
└──────────────┘            ↑                    ↑
       ↑             ┌──────────────┐     ┌──────────────┐
┌──────────────┐    │ Redis        │     │ DataDog      │
│ FastAPI      │────→│ (ElastiCache)│────→│ (APM)        │
│ (ECS Fargate)│    └──────────────┘     └──────────────┘
│ Multi-region │           ↑
└──────────────┘    ┌──────────────┐
       ↑            │ Celery       │
┌──────────────┐    │ (SQS-backed) │
│ ALB + WAF    │    └──────────────┘
└──────────────┘
       ↑
┌──────────────┐
│ CloudFront   │
│ (multi-region│
└──────────────┘
       ↑
┌──────────────┐
│ React App    │
│ (S3 + CF)    │
└──────────────┘
```

**Cost:** ~$3,000-5,000/month

---

## Development Priorities

### Must-Have (Phase 1)
1. ✅ CVE integration (backend exists, need UI)
2. ✅ Risk scoring
3. ✅ GitHub App for auto-ingestion
4. ✅ Export/reporting

### Should-Have (Phase 2)
5. ✅ Multi-tenancy
6. ✅ Authentication
7. ✅ Slack integration
8. ✅ Saved queries

### Nice-to-Have (Phase 3)
9. ✅ Trend analysis
10. ✅ Custom policies
11. ✅ CI/CD integration
12. ✅ Advanced visualizations

---

## Summary

**Current State:** Demo-ready prototype with solid foundation

**Phase 1 (MVP):** 4-6 weeks to first paying customer
- Focus: Crisis response + automated ingestion
- Investment: ~$10K (dev time)
- Revenue: $20K/year (first customer)

**Phase 2 (SaaS):** 8-12 weeks to scale
- Focus: Multi-tenancy + collaboration
- Investment: ~$30K (dev time + infrastructure)
- Revenue: $200K/year (10 customers)

**Phase 3 (Enterprise):** 12-16 weeks to enterprise-ready
- Focus: Advanced features + compliance
- Investment: ~$50K (dev time + infrastructure)
- Revenue: $500K+/year (5 enterprise customers)

**Total Time to Enterprise-Ready:** 6-9 months
**Total Investment:** ~$90K
**Potential Revenue:** $500K+/year

**ROI:** 5-6x in first year
