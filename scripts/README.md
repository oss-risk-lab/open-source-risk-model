# Database Maintenance Scripts

This directory contains utility scripts for maintaining the multi-repo persistent graph database.

## Available Scripts

### 1. backup_database.py

Creates backups of the SQLite database with optional compression and cloud storage upload.

**Features:**
- Consistent backups using SQLite's backup API
- Integrity verification
- Optional gzip compression
- Automatic cleanup of old backups
- AWS S3 upload support

**Usage:**

```bash
# Basic backup
python scripts/backup_database.py

# Backup with compression
python scripts/backup_database.py --compress

# Backup to specific directory
python scripts/backup_database.py --output /var/backups/graphs

# Backup and upload to S3
python scripts/backup_database.py --compress --s3-bucket my-backups

# Show database statistics before backup
python scripts/backup_database.py --stats

# Keep backups for 60 days
python scripts/backup_database.py --keep-days 60
```

**Options:**
- `--db-path PATH` - Path to source database (default: data/graphs.db)
- `--output DIR` - Output directory for backups (default: backups)
- `--compress` - Compress backup with gzip
- `--keep-days N` - Number of days to keep old backups (default: 30)
- `--s3-bucket BUCKET` - Upload backup to S3 bucket
- `--s3-prefix PREFIX` - S3 key prefix (default: open-source-risk-model)
- `--stats` - Show database statistics before backup

**Automated Backups:**

Add to crontab for daily backups:

```bash
# Daily backup at 2 AM
0 2 * * * cd /opt/open-source-risk-model && python scripts/backup_database.py --compress >> logs/backup.log 2>&1
```

---

### 2. restore_database.py

Restores the SQLite database from a backup file.

**Features:**
- Automatic decompression of gzipped backups
- Integrity verification before and after restore
- Automatic backup of current database before restore
- Interactive confirmation
- List available backups

**Usage:**

```bash
# List available backups
python scripts/restore_database.py --list

# Basic restore
python scripts/restore_database.py backups/graphs_20260220_120000.db

# Restore from compressed backup
python scripts/restore_database.py backups/graphs_20260220_120000.db.gz

# Restore to custom location
python scripts/restore_database.py backups/graphs_20260220_120000.db --db-path /var/lib/graphs.db

# Restore without backing up current database
python scripts/restore_database.py backups/graphs_20260220_120000.db --no-backup

# Skip integrity verification (not recommended)
python scripts/restore_database.py backups/graphs_20260220_120000.db --no-verify
```

**Options:**
- `--db-path PATH` - Path to target database (default: data/graphs.db)
- `--no-backup` - Don't backup current database before restore
- `--no-verify` - Skip integrity verification
- `--list` - List available backups in backups/ directory
- `--backup-dir DIR` - Directory to search for backups (default: backups)

**Important:**
- Always stop the API server before restoring
- The script will create a backup of the current database by default
- Verify the application works correctly after restore

---

### 3. cleanup_stale_data.py

Removes stale data from the database to free up space and improve performance.

**Features:**
- Remove repositories older than specified days
- Remove old completed/failed jobs
- Remove interrupted jobs
- Vacuum database to reclaim space
- Dry-run mode for safe testing
- Database statistics

**Usage:**

```bash
# Show current database statistics
python scripts/cleanup_stale_data.py --stats

# Remove repos older than 90 days (dry run)
python scripts/cleanup_stale_data.py --days 90 --dry-run

# Actually remove stale repos
python scripts/cleanup_stale_data.py --days 90

# Remove completed jobs older than 30 days
python scripts/cleanup_stale_data.py --cleanup-jobs --job-days 30

# Remove all interrupted jobs
python scripts/cleanup_stale_data.py --cleanup-interrupted-jobs

# Full cleanup with vacuum
python scripts/cleanup_stale_data.py --days 90 --cleanup-jobs --job-days 30 --cleanup-interrupted-jobs --vacuum
```

**Options:**
- `--db-path PATH` - Path to database (default: data/graphs.db)
- `--days N` - Remove repositories older than N days
- `--cleanup-jobs` - Remove old completed/failed jobs
- `--job-days N` - Remove jobs older than N days (default: 30)
- `--cleanup-interrupted-jobs` - Remove all interrupted jobs
- `--vacuum` - Vacuum database after cleanup to reclaim space
- `--dry-run` - Show what would be deleted without actually deleting
- `--stats` - Show database statistics only

**Recommended Schedule:**

```bash
# Weekly cleanup (crontab)
0 3 * * 0 cd /opt/open-source-risk-model && python scripts/cleanup_stale_data.py --days 90 --cleanup-jobs --job-days 30 --vacuum >> logs/cleanup.log 2>&1
```

---

### 4. rebuild_indexes.py

Rebuilds database indexes to improve query performance and fix inconsistencies.

**Features:**
- Verify index consistency with graph data
- Rebuild indexes for all or specific repositories
- Optimize database for better query performance
- Index statistics

**Usage:**

```bash
# Show index statistics
python scripts/rebuild_indexes.py --stats

# Verify indexes without rebuilding
python scripts/rebuild_indexes.py --verify-only

# Rebuild all indexes
python scripts/rebuild_indexes.py

# Rebuild indexes for specific repository
python scripts/rebuild_indexes.py --repo numpy/numpy

# Rebuild with optimization
python scripts/rebuild_indexes.py --optimize
```

**Options:**
- `--db-path PATH` - Path to database (default: data/graphs.db)
- `--repo REPO` - Rebuild indexes for specific repository (owner/repo)
- `--verify-only` - Only verify indexes without rebuilding
- `--optimize` - Optimize database after rebuilding
- `--stats` - Show index statistics only

**When to Use:**
- After bulk data imports
- If cross-repo queries are slow
- If you suspect index corruption
- After database recovery

**Recommended Schedule:**

```bash
# Monthly index rebuild (crontab)
0 4 1 * * cd /opt/open-source-risk-model && python scripts/rebuild_indexes.py --optimize >> logs/rebuild.log 2>&1
```

---

## Common Workflows

### Daily Maintenance

```bash
# Automated daily backup
0 2 * * * cd /opt/open-source-risk-model && python scripts/backup_database.py --compress >> logs/backup.log 2>&1
```

### Weekly Maintenance

```bash
# Cleanup stale data
python scripts/cleanup_stale_data.py --days 90 --cleanup-jobs --job-days 30 --vacuum

# Verify indexes
python scripts/rebuild_indexes.py --verify-only
```

### Monthly Maintenance

```bash
# Rebuild indexes and optimize
python scripts/rebuild_indexes.py --optimize

# Review backup retention
ls -lh backups/
```

### Disaster Recovery

```bash
# 1. Stop the API server
sudo systemctl stop open-source-risk-model

# 2. List available backups
python scripts/restore_database.py --list

# 3. Restore from backup
python scripts/restore_database.py backups/graphs_20260220_020000.db.gz

# 4. Verify database integrity
python scripts/rebuild_indexes.py --verify-only

# 5. Start the API server
sudo systemctl start open-source-risk-model

# 6. Check logs
sudo journalctl -u open-source-risk-model -f
```

### Performance Tuning

```bash
# 1. Check database statistics
python scripts/cleanup_stale_data.py --stats

# 2. Clean up stale data
python scripts/cleanup_stale_data.py --days 90 --vacuum

# 3. Rebuild and optimize indexes
python scripts/rebuild_indexes.py --optimize

# 4. Verify improvements
python scripts/rebuild_indexes.py --stats
```

---

## Requirements

All scripts require Python 3.10+ and the following standard library modules:
- `sqlite3`
- `argparse`
- `json`
- `gzip`
- `shutil`
- `datetime`

Optional dependencies:
- `boto3` - For S3 upload support (install with: `pip install boto3`)

---

## Environment Variables

Scripts respect the following environment variables:

- `GRAPH_DB_PATH` - Default database path (default: data/graphs.db)

Example:

```bash
export GRAPH_DB_PATH=/var/lib/open-source-risk-model/graphs.db
python scripts/backup_database.py
```

---

## Best Practices

1. **Backups:**
   - Run daily automated backups
   - Keep at least 7 daily backups
   - Store backups on separate disk/server
   - Test restore procedure monthly

2. **Cleanup:**
   - Remove stale data regularly (weekly or monthly)
   - Vacuum database after cleanup
   - Monitor database size growth

3. **Indexes:**
   - Verify indexes monthly
   - Rebuild if inconsistencies found
   - Optimize after bulk operations

4. **Monitoring:**
   - Check script logs regularly
   - Monitor database size
   - Track backup success/failure
   - Alert on script failures

---

## Troubleshooting

### Backup fails with "database is locked"

**Solution:** Stop the API server before backup, or use the backup script which handles locks automatically.

### Restore fails with integrity check error

**Solution:** The backup file may be corrupted. Try a different backup file.

### Cleanup removes too much data

**Solution:** Always use `--dry-run` first to preview what will be deleted.

### Index rebuild is slow

**Solution:** This is normal for large databases. Run during low-traffic periods.

---

## Support

For issues or questions:
- Check the main documentation in `docs/`
- Review script help: `python scripts/<script>.py --help`
- Check logs for error details
- Report bugs on GitHub

---

## License

These scripts are part of the Open Source Risk Model project and follow the same license.
