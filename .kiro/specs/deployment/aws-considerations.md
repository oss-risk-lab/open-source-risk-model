# AWS Deployment Considerations

## Overview

This document tracks architectural decisions and considerations for future AWS deployment. While we're currently developing locally with SQLite, we're designing with AWS scalability in mind.

## Current Architecture (Local Development)

```
FastAPI (uvicorn) → SQLite → Local filesystem
Background Worker (asyncio polling)
```

## Target AWS Architecture (Future)

```
┌─────────────────────────────────────────────────────────────┐
│                         AWS Cloud                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │   Route 53   │────────▶│  CloudFront  │                 │
│  │     DNS      │         │     CDN      │                 │
│  └──────────────┘         └──────┬───────┘                 │
│                                   │                          │
│                          ┌────────▼────────┐                │
│                          │   ALB / API GW  │                │
│                          └────────┬────────┘                │
│                                   │                          │
│  ┌───────────────────────────────┼──────────────────────┐  │
│  │              ECS / Lambda     │                      │  │
│  │  ┌────────────────────────────▼─────────────────┐   │  │
│  │  │  FastAPI Containers / Lambda Functions       │   │  │
│  │  │  - API endpoints                              │   │  │
│  │  │  - Graph generation                           │   │  │
│  │  │  - Auto-scaling based on load                │   │  │
│  │  └───────────────────┬──────────────────────────┘   │  │
│  └────────────────────────┼──────────────────────────────┘  │
│                            │                                 │
│  ┌─────────────────────────┼──────────────────────────────┐ │
│  │  Background Processing  │                              │ │
│  │  ┌─────────────────────▼──────────────────┐           │ │
│  │  │  SQS Queue                              │           │ │
│  │  │  - Ingestion jobs                       │           │ │
│  │  │  - Dependency resolution                │           │ │
│  │  └─────────────────────┬──────────────────┘           │ │
│  │                        │                                │ │
│  │  ┌─────────────────────▼──────────────────┐           │ │
│  │  │  ECS Tasks / Lambda Workers             │           │ │
│  │  │  - Process jobs from queue              │           │ │
│  │  │  - Auto-scaling based on queue depth    │           │ │
│  │  └─────────────────────┬──────────────────┘           │ │
│  └────────────────────────┼──────────────────────────────┘ │
│                            │                                 │
│  ┌─────────────────────────┼──────────────────────────────┐ │
│  │  Data Layer             │                              │ │
│  │  ┌─────────────────────▼──────────────────┐           │ │
│  │  │  RDS PostgreSQL / Aurora                │           │ │
│  │  │  - Graph data                           │           │ │
│  │  │  - Job state                            │           │ │
│  │  │  - Indexes                              │           │ │
│  │  │  - Multi-AZ for HA                      │           │ │
│  │  └─────────────────────┬──────────────────┘           │ │
│  │                        │                                │ │
│  │  ┌─────────────────────▼──────────────────┐           │ │
│  │  │  ElastiCache Redis                      │           │ │
│  │  │  - API response caching                 │           │ │
│  │  │  - Session management                   │           │ │
│  │  └─────────────────────────────────────────┘           │ │
│  │                                                         │ │
│  │  ┌──────────────────────────────────────────┐          │ │
│  │  │  S3                                       │          │ │
│  │  │  - Static assets (UI)                    │          │ │
│  │  │  - Database backups                      │          │ │
│  │  │  - Large graph exports                   │          │ │
│  │  └──────────────────────────────────────────┘          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Monitoring & Logging                                   │ │
│  │  - CloudWatch Logs                                      │ │
│  │  - CloudWatch Metrics                                   │ │
│  │  - X-Ray Tracing                                        │ │
│  │  - CloudWatch Alarms                                    │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Migration Path: SQLite → PostgreSQL

### Current Design (SQLite-friendly)
✅ All database access through repository interfaces
✅ No SQLite-specific features used
✅ Transactional operations
✅ JSON storage for flexibility

### Migration Strategy
1. **Phase 1: Add PostgreSQL support**
   - Implement PostgreSQL versions of repositories
   - Use environment variable to switch: `DB_TYPE=postgresql`
   - Keep SQLite for local development

2. **Phase 2: Data migration**
   - Export from SQLite
   - Import to PostgreSQL
   - Validate data integrity

3. **Phase 3: Optimize for PostgreSQL**
   - Use JSONB instead of JSON text
   - Add PostgreSQL-specific indexes
   - Optimize queries for PostgreSQL

## AWS Service Recommendations

### Compute Options

#### Option A: ECS Fargate (Recommended)
**Pros:**
- Serverless containers (no EC2 management)
- Auto-scaling
- Good for long-running API servers
- Cost-effective for steady traffic

**Cons:**
- Slightly more expensive than EC2
- Cold start for scaling up

**Use for:**
- FastAPI API server
- Background worker tasks

#### Option B: Lambda
**Pros:**
- True serverless (pay per request)
- Auto-scaling
- No infrastructure management
- Very cost-effective for low/variable traffic

**Cons:**
- 15-minute timeout (may not work for long ingestion jobs)
- Cold starts
- More complex for stateful operations

**Use for:**
- API endpoints (via API Gateway)
- Short background tasks
- Scheduled jobs (via EventBridge)

#### Option C: ECS on EC2
**Pros:**
- Most cost-effective for high, steady traffic
- Full control

**Cons:**
- Must manage EC2 instances
- More operational overhead

**Use for:**
- High-traffic production (if needed)

### Database Options

#### Option A: RDS PostgreSQL (Recommended)
**Pros:**
- Managed service (automated backups, patching)
- Multi-AZ for high availability
- Read replicas for scaling
- Compatible with our current design

**Cons:**
- More expensive than self-managed
- Some PostgreSQL features restricted

**Configuration:**
- Instance: db.t3.medium (start small, scale up)
- Storage: 100GB GP3 (auto-scaling enabled)
- Multi-AZ: Yes (for production)
- Backups: 7-day retention

#### Option B: Aurora PostgreSQL
**Pros:**
- Better performance than RDS
- Auto-scaling storage
- Fast failover
- Serverless option available

**Cons:**
- More expensive than RDS
- Overkill for initial deployment

**Use when:**
- Need high performance
- Need frequent read scaling
- Budget allows

#### Option C: DynamoDB
**Pros:**
- Fully serverless
- Unlimited scaling
- Pay per request

**Cons:**
- Would require complete rewrite
- Not graph-friendly
- Complex queries difficult

**Verdict:** Not recommended for this use case

### Queue Options

#### Option A: SQS (Recommended)
**Pros:**
- Fully managed
- Unlimited scaling
- Dead letter queues
- Simple to use

**Cons:**
- Not real-time (eventual consistency)
- No priority queues

**Use for:**
- Ingestion job queue
- Background task queue

#### Option B: EventBridge
**Pros:**
- Event-driven architecture
- Rule-based routing
- Integrates with many AWS services

**Cons:**
- More complex than SQS
- Overkill for simple queuing

**Use for:**
- Scheduled jobs (cron-like)
- Event-driven workflows

### Caching Options

#### Option A: ElastiCache Redis (Recommended)
**Pros:**
- Managed Redis
- Fast in-memory caching
- Supports complex data structures

**Cons:**
- Costs money even when idle
- Requires VPC setup

**Use for:**
- API response caching
- Session management
- Rate limiting

#### Option B: CloudFront
**Pros:**
- CDN caching at edge locations
- Very fast for static content
- Reduces origin load

**Cons:**
- Not suitable for dynamic API responses
- Cache invalidation can be slow

**Use for:**
- Static UI assets
- Public API responses (with short TTL)

## Architecture Decisions for AWS Compatibility

### ✅ Already AWS-Ready

1. **Stateless API Design**
   - No local file storage (except SQLite, which will migrate)
   - All state in database
   - Can run multiple instances

2. **Environment-Based Configuration**
   - All config via environment variables
   - Easy to use AWS Parameter Store / Secrets Manager

3. **Background Job System**
   - Database-backed queue (can migrate to SQS)
   - Idempotent job processing
   - Graceful shutdown handling

4. **Repository Pattern**
   - Database abstraction layer
   - Easy to swap SQLite → PostgreSQL

### 🔄 Needs Adjustment for AWS

1. **Database Connection Pooling**
   - Current: Single connection per request
   - AWS: Need connection pooling (pgbouncer or SQLAlchemy pool)

2. **File Storage**
   - Current: Local filesystem for cache
   - AWS: Migrate to S3 for large files

3. **Logging**
   - Current: Local logs
   - AWS: CloudWatch Logs integration

4. **Health Checks**
   - Current: Basic /api/health
   - AWS: Need detailed health checks for ALB/ECS

5. **Secrets Management**
   - Current: .env file
   - AWS: AWS Secrets Manager or Parameter Store

## Cost Estimates (Monthly)

### Small Deployment (MVP)
- **ECS Fargate (2 tasks)**: $30-50
- **RDS PostgreSQL (db.t3.small)**: $30-40
- **ElastiCache Redis (cache.t3.micro)**: $15-20
- **ALB**: $20-25
- **S3 + CloudFront**: $5-10
- **CloudWatch**: $5-10
- **Total**: ~$105-155/month

### Medium Deployment (Production)
- **ECS Fargate (4-8 tasks)**: $100-200
- **RDS PostgreSQL (db.t3.medium, Multi-AZ)**: $150-200
- **ElastiCache Redis (cache.t3.small)**: $40-50
- **ALB**: $25-30
- **S3 + CloudFront**: $20-30
- **CloudWatch**: $20-30
- **Total**: ~$355-540/month

### Large Deployment (Scale)
- **ECS Fargate (10-20 tasks)**: $300-600
- **Aurora PostgreSQL (db.r5.large)**: $400-500
- **ElastiCache Redis (cache.r5.large)**: $150-200
- **ALB**: $30-40
- **S3 + CloudFront**: $50-100
- **CloudWatch**: $50-100
- **Total**: ~$980-1540/month

## Implementation Checklist (Future)

### Phase 1: Prepare for AWS
- [ ] Add PostgreSQL support to repositories
- [ ] Implement connection pooling
- [ ] Add CloudWatch logging integration
- [ ] Add detailed health checks
- [ ] Migrate secrets to AWS Secrets Manager
- [ ] Add S3 support for file storage
- [ ] Create Dockerfile for ECS
- [ ] Add infrastructure as code (Terraform/CDK)

### Phase 2: Deploy to AWS
- [ ] Set up VPC and networking
- [ ] Deploy RDS PostgreSQL
- [ ] Deploy ElastiCache Redis
- [ ] Deploy ECS cluster
- [ ] Deploy ALB
- [ ] Set up CloudFront
- [ ] Configure Route 53
- [ ] Set up CloudWatch monitoring

### Phase 3: Migrate Data
- [ ] Export from local SQLite
- [ ] Import to RDS PostgreSQL
- [ ] Validate data integrity
- [ ] Update DNS to point to AWS

### Phase 4: Optimize
- [ ] Tune database performance
- [ ] Optimize cache hit rates
- [ ] Set up auto-scaling policies
- [ ] Configure CloudWatch alarms
- [ ] Implement cost optimization

## Key Takeaways

1. **Current architecture is AWS-ready** - Repository pattern makes database migration easy
2. **Start with ECS Fargate + RDS PostgreSQL** - Good balance of simplicity and scalability
3. **Use SQS for background jobs** - Replace database polling with proper queue
4. **Estimated cost: $100-200/month** for initial deployment
5. **Migration path is clear** - SQLite → PostgreSQL, local → AWS

## Next Steps

For now, continue building features with SQLite locally. When ready to deploy:
1. Implement PostgreSQL support (1-2 days)
2. Create AWS infrastructure (Terraform/CDK) (2-3 days)
3. Deploy and test (1-2 days)
4. Migrate data (1 day)

Total deployment effort: ~1 week
