# Multi-Repo Persistent Graph - Deployment Guide

This guide covers deploying and operating the multi-repo persistent graph system in production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Database Setup](#database-setup)
3. [Environment Configuration](#environment-configuration)
4. [Deployment Options](#deployment-options)
5. [Backup and Restore](#backup-and-restore)
6. [Monitoring and Maintenance](#monitoring-and-maintenance)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher
- **Memory**: Minimum 2GB RAM (4GB+ recommended for production)
- **Disk Space**: 
  - Application: ~500MB
  - Database: ~100MB per 1000 repositories (estimate)
  - Logs: Plan for 1-5GB depending on retention policy
- **Operating System**: Linux (recommended), macOS, or Windows

### Required Dependencies

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Key dependencies:
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `sqlite3` - Database (included in Python standard library)
- `httpx` - HTTP client for external APIs
- `pydantic` - Data validation

### External API Access

The system requires access to:
- **GitHub API**: For repository data
  - Rate limit: 5,000 requests/hour (authenticated)
  - Required: GitHub personal access token
- **OSV.dev API**: For CVE data
  - No authentication required
  - Rate limit: Generous, no strict limits

---

## Database Setup

### Initial Database Creation

The database is automatically created on first startup. The system will:

1. Create the database file at the configured path (default: `data/graphs.db`)
2. Initialize the schema with all required tables
3. Set up indexes for query performance
4. Configure SQLite pragmas for optimal performance

**Manual initialization** (optional):

```bash
# Create data directory
mkdir -p data

# The database will be created automatically on first API startup
# Or you can pre-create it using Python:
python -c "from src.open_source_risk_model.persistence.db import init_database; init_database('data/graphs.db')"
```

### Database Location

**Development:**
```bash
# Default location
data/graphs.db
```

**Production:**
```bash
# Recommended: Use absolute path on persistent volume
/var/lib/open-source-risk-model/graphs.db

# Or use environment variable
export GRAPH_DB_PATH=/var/lib/open-source-risk-model/graphs.db
```

### Database Permissions

Ensure the application has read/write permissions:

```bash
# Set ownership (Linux)
sudo chown app-user:app-group /var/lib/open-source-risk-model/graphs.db

# Set permissions
chmod 644 /var/lib/open-source-risk-model/graphs.db

# Ensure directory is writable (for WAL files)
chmod 755 /var/lib/open-source-risk-model/
```

### SQLite Configuration

The system automatically configures SQLite with optimal settings:

```sql
PRAGMA journal_mode=WAL;        -- Write-Ahead Logging for better concurrency
PRAGMA synchronous=NORMAL;      -- Balance between safety and performance
PRAGMA busy_timeout=5000;       -- Wait up to 5 seconds for locks
```

**WAL Mode Benefits:**
- Readers don't block writers
- Writers don't block readers
- Better concurrency for multi-process deployments

**WAL Mode Files:**
- `graphs.db` - Main database file
- `graphs.db-wal` - Write-ahead log
- `graphs.db-shm` - Shared memory file

**Important:** Backup all three files together for consistency.

---

## Environment Configuration

### Required Environment Variables

Create a `.env` file or set environment variables:

```bash
# GitHub API Authentication (REQUIRED)
GITHUB_TOKEN=ghp_your_personal_access_token_here

# Database Configuration
GRAPH_DB_PATH=data/graphs.db              # Path to SQLite database
GRAPH_DB_ENABLED=true                     # Enable persistence layer
GRAPH_TTL_HOURS=24                        # Cache TTL in hours
GRAPH_AUTO_REFRESH_STALE=false            # Auto-regenerate stale data

# Worker Configuration
GRAPH_WORKER_ENABLED=true                 # Enable background worker
GRAPH_WORKER_POLL_INTERVAL=5              # Seconds between job polls

# API Configuration (optional)
API_HOST=0.0.0.0                          # Bind address
API_PORT=8000                             # Port number
API_WORKERS=4                             # Number of worker processes

# Logging (optional)
LOG_LEVEL=INFO                            # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/app.log                     # Log file path
```

### GitHub Token Setup

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Required scopes:
   - `public_repo` - Access public repository data
   - `read:org` - Read organization data (optional, for org repos)
4. Copy token and set as `GITHUB_TOKEN` environment variable

**Security Best Practices:**
- Never commit tokens to version control
- Use environment variables or secret management systems
- Rotate tokens periodically
- Use minimal required scopes

### Configuration Profiles

**Development:**
```bash
GRAPH_DB_PATH=data/graphs.db
GRAPH_DB_ENABLED=true
GRAPH_TTL_HOURS=1
GRAPH_AUTO_REFRESH_STALE=true
GRAPH_WORKER_ENABLED=true
LOG_LEVEL=DEBUG
```

**Production:**
```bash
GRAPH_DB_PATH=/var/lib/open-source-risk-model/graphs.db
GRAPH_DB_ENABLED=true
GRAPH_TTL_HOURS=24
GRAPH_AUTO_REFRESH_STALE=false
GRAPH_WORKER_ENABLED=true
GRAPH_WORKER_POLL_INTERVAL=10
LOG_LEVEL=INFO
LOG_FILE=/var/log/open-source-risk-model/app.log
API_WORKERS=4
```

**High-Availability:**
```bash
# Use longer TTL to reduce external API load
GRAPH_TTL_HOURS=168  # 7 days

# Disable auto-refresh to prevent unexpected latency
GRAPH_AUTO_REFRESH_STALE=false

# Multiple workers for better throughput
API_WORKERS=8
GRAPH_WORKER_POLL_INTERVAL=5
```

---

## Deployment Options

### Option 1: Single Server Deployment

**Architecture:**
```
┌─────────────────────────────────┐
│     Single Server               │
│                                 │
│  ┌──────────────────────────┐  │
│  │   Uvicorn (API Server)   │  │
│  │   - Multiple workers     │  │
│  │   - Background worker    │  │
│  └──────────────────────────┘  │
│              │                  │
│              ▼                  │
│  ┌──────────────────────────┐  │
│  │   SQLite Database        │  │
│  │   - WAL mode enabled     │  │
│  └──────────────────────────┘  │
└─────────────────────────────────┘
```

**Setup:**

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Create directories
mkdir -p data logs

# 4. Start the server
uvicorn api.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-config logging.conf
```

**Pros:**
- Simple setup
- Low operational complexity
- Suitable for small to medium workloads

**Cons:**
- Single point of failure
- Limited horizontal scalability
- SQLite concurrency limits

### Option 2: Systemd Service (Linux)

Create a systemd service for automatic startup and management.

**Service File:** `/etc/systemd/system/open-source-risk-model.service`

```ini
[Unit]
Description=Open Source Risk Model API
After=network.target

[Service]
Type=notify
User=app-user
Group=app-group
WorkingDirectory=/opt/open-source-risk-model
Environment="PATH=/opt/open-source-risk-model/venv/bin"
EnvironmentFile=/opt/open-source-risk-model/.env
ExecStart=/opt/open-source-risk-model/venv/bin/uvicorn api.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Setup:**

```bash
# 1. Copy application to /opt
sudo cp -r . /opt/open-source-risk-model/

# 2. Create virtual environment
cd /opt/open-source-risk-model
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Create app user
sudo useradd -r -s /bin/false app-user

# 4. Set permissions
sudo chown -R app-user:app-group /opt/open-source-risk-model
sudo chmod 755 /opt/open-source-risk-model

# 5. Install and start service
sudo systemctl daemon-reload
sudo systemctl enable open-source-risk-model
sudo systemctl start open-source-risk-model

# 6. Check status
sudo systemctl status open-source-risk-model
```

**Management Commands:**

```bash
# Start service
sudo systemctl start open-source-risk-model

# Stop service
sudo systemctl stop open-source-risk-model

# Restart service
sudo systemctl restart open-source-risk-model

# View logs
sudo journalctl -u open-source-risk-model -f

# Enable auto-start on boot
sudo systemctl enable open-source-risk-model
```

### Option 3: Docker Deployment

**Dockerfile:**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data directory
RUN mkdir -p /app/data /app/logs

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**docker-compose.yml:**

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - GRAPH_DB_PATH=/app/data/graphs.db
      - GRAPH_DB_ENABLED=true
      - GRAPH_TTL_HOURS=24
      - GRAPH_WORKER_ENABLED=true
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Deployment:**

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

### Option 4: Reverse Proxy with Nginx

For production deployments, use Nginx as a reverse proxy.

**Nginx Configuration:** `/etc/nginx/sites-available/open-source-risk-model`

```nginx
upstream api_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name api.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/api.access.log;
    error_log /var/log/nginx/api.error.log;

    # Proxy settings
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files (if any)
    location /ui/ {
        alias /opt/open-source-risk-model/ui/;
        expires 1d;
    }
}
```

**Setup:**

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/open-source-risk-model /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## Backup and Restore

### Backup Procedures

#### Manual Backup

```bash
#!/bin/bash
# backup.sh - Manual database backup script

BACKUP_DIR="/var/backups/open-source-risk-model"
DB_PATH="/var/lib/open-source-risk-model/graphs.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/graphs_$TIMESTAMP.db"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database (includes WAL files)
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# Compress backup
gzip "$BACKUP_FILE"

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "graphs_*.db.gz" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE.gz"
```

**Usage:**

```bash
chmod +x backup.sh
./backup.sh
```

#### Automated Backup with Cron

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/open-source-risk-model/scripts/backup.sh >> /var/log/backup.log 2>&1
```

#### Backup to Cloud Storage

**AWS S3 Example:**

```bash
#!/bin/bash
# backup-to-s3.sh

BACKUP_DIR="/var/backups/open-source-risk-model"
DB_PATH="/var/lib/open-source-risk-model/graphs.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/graphs_$TIMESTAMP.db"
S3_BUCKET="s3://my-backups/open-source-risk-model/"

# Create backup
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
gzip "$BACKUP_FILE"

# Upload to S3
aws s3 cp "$BACKUP_FILE.gz" "$S3_BUCKET"

# Clean up local backup
rm "$BACKUP_FILE.gz"

echo "Backup uploaded to S3: $S3_BUCKET"
```

### Restore Procedures

#### Restore from Backup

```bash
#!/bin/bash
# restore.sh - Restore database from backup

BACKUP_FILE="$1"
DB_PATH="/var/lib/open-source-risk-model/graphs.db"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file.db.gz>"
    exit 1
fi

# Stop the service
sudo systemctl stop open-source-risk-model

# Backup current database (just in case)
cp "$DB_PATH" "$DB_PATH.before_restore"

# Decompress and restore
gunzip -c "$BACKUP_FILE" > "$DB_PATH"

# Verify database integrity
sqlite3 "$DB_PATH" "PRAGMA integrity_check;"

# Start the service
sudo systemctl start open-source-risk-model

echo "Restore completed from: $BACKUP_FILE"
```

**Usage:**

```bash
chmod +x restore.sh
./restore.sh /var/backups/open-source-risk-model/graphs_20260220_020000.db.gz
```

#### Verify Backup Integrity

```bash
# Check database integrity
sqlite3 graphs.db "PRAGMA integrity_check;"

# Expected output: "ok"

# Check schema version
sqlite3 graphs.db "SELECT version FROM schema_version;"

# Count repositories
sqlite3 graphs.db "SELECT COUNT(*) FROM repo_graphs;"
```

### Backup Best Practices

1. **Frequency:**
   - Daily backups for production
   - Hourly backups for high-activity systems
   - Before major operations (migrations, bulk deletes)

2. **Retention:**
   - Keep 7 daily backups
   - Keep 4 weekly backups
   - Keep 12 monthly backups

3. **Storage:**
   - Store backups on separate disk/server
   - Use cloud storage for off-site backups
   - Encrypt backups containing sensitive data

4. **Testing:**
   - Test restore procedure monthly
   - Verify backup integrity automatically
   - Document restore time (RTO)

---

## Monitoring and Maintenance

### Health Checks

**API Health Endpoint:**

```bash
# Check API health
curl http://localhost:8000/api/health

# Expected response
{"status": "ok"}
```

**Database Health:**

```bash
# Check database size
du -h /var/lib/open-source-risk-model/graphs.db

# Check database integrity
sqlite3 /var/lib/open-source-risk-model/graphs.db "PRAGMA integrity_check;"

# Check table sizes
sqlite3 /var/lib/open-source-risk-model/graphs.db "
SELECT 
    name,
    (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as count
FROM sqlite_master m
WHERE type='table';
"
```

### Monitoring Metrics

**Key Metrics to Monitor:**

1. **API Performance:**
   - Request rate (requests/second)
   - Response time (p50, p95, p99)
   - Error rate (4xx, 5xx)
   - Active connections

2. **Database:**
   - Database size (MB)
   - Number of repositories stored
   - Query performance
   - Lock contention

3. **Background Worker:**
   - Job queue length
   - Job processing rate
   - Job success/failure rate
   - Average job duration

4. **System Resources:**
   - CPU usage
   - Memory usage
   - Disk I/O
   - Network I/O

**Monitoring Script Example:**

```bash
#!/bin/bash
# monitor.sh - Basic monitoring script

DB_PATH="/var/lib/open-source-risk-model/graphs.db"

echo "=== Database Statistics ==="
echo "Database size: $(du -h $DB_PATH | cut -f1)"
echo "Total repositories: $(sqlite3 $DB_PATH 'SELECT COUNT(*) FROM repo_graphs;')"
echo "Pending jobs: $(sqlite3 $DB_PATH "SELECT COUNT(*) FROM ingestion_jobs WHERE status='pending';")"
echo "Running jobs: $(sqlite3 $DB_PATH "SELECT COUNT(*) FROM ingestion_jobs WHERE status='running';")"

echo ""
echo "=== API Health ==="
curl -s http://localhost:8000/api/health | jq .

echo ""
echo "=== System Resources ==="
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')%"
echo "Memory: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "Disk: $(df -h /var/lib/open-source-risk-model | awk 'NR==2 {print $3 "/" $2 " (" $5 " used)"}')"
```

### Maintenance Tasks

#### Clean Up Stale Data

```bash
# Remove repositories older than 90 days
curl -X DELETE "http://localhost:8000/api/repos?older_than=$(date -d '90 days ago' -Iseconds)"
```

#### Rebuild Indexes

```bash
#!/bin/bash
# rebuild_indexes.sh - Rebuild database indexes

DB_PATH="/var/lib/open-source-risk-model/graphs.db"

sqlite3 "$DB_PATH" <<EOF
-- Rebuild indexes
REINDEX;

-- Analyze tables for query optimization
ANALYZE;

-- Vacuum to reclaim space
VACUUM;
EOF

echo "Indexes rebuilt and database optimized"
```

#### Database Optimization

```bash
# Run weekly
sqlite3 /var/lib/open-source-risk-model/graphs.db "VACUUM;"
sqlite3 /var/lib/open-source-risk-model/graphs.db "ANALYZE;"

# Check fragmentation
sqlite3 /var/lib/open-source-risk-model/graphs.db "PRAGMA freelist_count;"
```

### Log Management

**Log Rotation Configuration:** `/etc/logrotate.d/open-source-risk-model`

```
/var/log/open-source-risk-model/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 app-user app-group
    sharedscripts
    postrotate
        systemctl reload open-source-risk-model > /dev/null 2>&1 || true
    endscript
}
```

---

## Troubleshooting

### Common Issues

#### Issue: Database Locked

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Causes:**
- Multiple processes accessing database without WAL mode
- Long-running transaction
- Disk I/O issues

**Solutions:**

```bash
# 1. Check WAL mode is enabled
sqlite3 /var/lib/open-source-risk-model/graphs.db "PRAGMA journal_mode;"
# Should return: wal

# 2. Check for long-running transactions
sqlite3 /var/lib/open-source-risk-model/graphs.db "PRAGMA wal_checkpoint(FULL);"

# 3. Increase busy_timeout
# Already set to 5000ms in code, but can be increased if needed
```

#### Issue: High Memory Usage

**Symptoms:**
- API server consuming excessive memory
- OOM (Out of Memory) errors

**Solutions:**

```bash
# 1. Reduce number of workers
# In .env or command line:
API_WORKERS=2

# 2. Limit graph size
# In .env:
MAX_RELEASES=5
MAX_MAINTAINERS=3

# 3. Monitor memory usage
ps aux | grep uvicorn
```

#### Issue: Slow Query Performance

**Symptoms:**
- API responses taking > 1 second
- Database queries timing out

**Solutions:**

```bash
# 1. Rebuild indexes
sqlite3 /var/lib/open-source-risk-model/graphs.db "REINDEX; ANALYZE;"

# 2. Check database size
du -h /var/lib/open-source-risk-model/graphs.db

# 3. Vacuum database
sqlite3 /var/lib/open-source-risk-model/graphs.db "VACUUM;"

# 4. Check for missing indexes
sqlite3 /var/lib/open-source-risk-model/graphs.db ".schema"
```

#### Issue: Worker Not Processing Jobs

**Symptoms:**
- Jobs stuck in "pending" status
- No job progress

**Solutions:**

```bash
# 1. Check worker is enabled
grep GRAPH_WORKER_ENABLED .env
# Should be: true

# 2. Check logs for errors
tail -f /var/log/open-source-risk-model/app.log

# 3. Restart service
sudo systemctl restart open-source-risk-model

# 4. Check for interrupted jobs
sqlite3 /var/lib/open-source-risk-model/graphs.db \
  "SELECT * FROM ingestion_jobs WHERE status='interrupted';"
```

#### Issue: GitHub API Rate Limit

**Symptoms:**
```
GitHub API rate limit exceeded
```

**Solutions:**

```bash
# 1. Check current rate limit
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/rate_limit

# 2. Use longer TTL to reduce API calls
# In .env:
GRAPH_TTL_HOURS=168  # 7 days

# 3. Disable auto-refresh
GRAPH_AUTO_REFRESH_STALE=false

# 4. Use multiple GitHub tokens (round-robin)
# Requires code modification
```

### Debug Mode

Enable debug logging for troubleshooting:

```bash
# In .env
LOG_LEVEL=DEBUG

# Restart service
sudo systemctl restart open-source-risk-model

# View debug logs
tail -f /var/log/open-source-risk-model/app.log
```

### Support and Resources

- **Documentation:** See `docs/` directory
- **Issues:** Report bugs on GitHub
- **Logs:** Check `/var/log/open-source-risk-model/app.log`
- **Database:** Inspect with `sqlite3` command-line tool

---

## Security Considerations

### API Security

1. **Authentication:**
   - Implement API key authentication for production
   - Use HTTPS for all external access
   - Rate limit API endpoints

2. **GitHub Token:**
   - Store securely (environment variables, secrets manager)
   - Never log or expose in responses
   - Rotate periodically

3. **Database:**
   - Restrict file permissions (644 for database, 755 for directory)
   - No sensitive data in database (tokens, passwords)
   - Regular backups with encryption

### Network Security

1. **Firewall:**
   ```bash
   # Allow only necessary ports
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # HTTP
   sudo ufw allow 443/tcp  # HTTPS
   sudo ufw enable
   ```

2. **Reverse Proxy:**
   - Use Nginx or similar for SSL termination
   - Hide internal service details
   - Add security headers

3. **Access Control:**
   - Limit API access to trusted networks
   - Use VPN for administrative access
   - Implement IP whitelisting if needed

---

## Performance Tuning

### Database Tuning

```sql
-- Increase cache size (default: 2MB, increase to 64MB)
PRAGMA cache_size = -64000;

-- Enable memory-mapped I/O (faster reads)
PRAGMA mmap_size = 268435456;  -- 256MB

-- Optimize for read-heavy workload
PRAGMA temp_store = MEMORY;
```

### API Tuning

```bash
# Increase worker count for high traffic
API_WORKERS=8

# Adjust worker timeout
--timeout 120

# Use Gunicorn for better process management
gunicorn api.app:app \
  --workers 8 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120
```

### System Tuning

```bash
# Increase file descriptors
ulimit -n 65536

# Increase network buffer sizes
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216
```

---

## Scaling Considerations

### Current Limitations

- **SQLite Concurrency:** Limited write concurrency
- **Single Server:** No horizontal scaling
- **No Replication:** No built-in redundancy

### Future Migration Path

For larger scale deployments, consider migrating to:

1. **PostgreSQL:**
   - Better write concurrency
   - Replication support
   - Connection pooling

2. **Neo4j:**
   - Native graph database
   - Advanced graph queries
   - Clustering support

The persistence layer is abstracted to support future migration without application changes.

---

## Conclusion

This deployment guide covers the essential aspects of deploying and operating the multi-repo persistent graph system. For additional help, consult the API documentation and other guides in the `docs/` directory.
