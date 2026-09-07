# Operations Runbook

## Daily Operations

### Morning Briefing
1. Check dashboard metrics: `GET /api/dashboard/metrics`
2. Review active alerts: `GET /api/alerts?active_only=true`
3. Check data freshness: Most recent reading should be < 1 hour old
4. Verify all stations online (green dot on map)

### Monitoring Checks (Every 4 hours)
```bash
# Check backend health
curl http://localhost:8000/api/health

# Check database connection
psql -h localhost -U postgres -d floodguard -c "SELECT 1;"

# Check data pipeline jobs
docker-compose logs backend | grep "Fetched"
```

### Alert Response Workflow
1. Alert triggered on dashboard
2. Operator reviews station details
3. Click "Acknowledge" to confirm awareness
4. Take action (notify downstream, increase monitoring, etc.)
5. Click "Dismiss" to close alert
6. Document action in external system

---

## Troubleshooting

### No Data Updates
```bash
# Check data pipeline status
docker-compose logs backend | tail -50 | grep -i "fetch"

# Manually trigger data fetch
docker-compose exec backend python -c "
from backend.data_pipeline import get_pipeline
from backend.db import SessionLocal
db = SessionLocal()
get_pipeline().fetch_all_stations_cwc(db)
print('Done')
"

# Check CWC API accessibility
curl -X GET 'https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted' \
  -H 'User-Agent: Mozilla/5.0' -w '\n%{http_code}'
```

### Alerts Not Sending
```bash
# Check email configuration
docker-compose exec backend python -c "
from backend.alert_engine import EmailNotifier
notif = EmailNotifier()
status = notif.send_alert_email(
    'test@example.com',
    'Test Station',
    'HIGH',
    75.5
)
print(f'Email sent: {status}')
"

# Check Twilio configuration
docker-compose exec backend python -c "
from backend.alert_engine import SMSNotifier
notif = SMSNotifier()
status = notif.send_alert_sms(
    '+911234567890',
    'Test Station',
    'HIGH',
    75.5
)
print(f'SMS sent: {status}')
"

# Check SMTP logs
docker-compose logs backend | grep -i "smtp\|email"
```

### Model Not Loading
```bash
# Verify model file exists
ls -lh flood_model.joblib

# Check model info
docker-compose exec backend python -c "
from backend.models import get_model
model = get_model()
print(f'Model loaded: {model.model is not None}')
print(f'Features: {model.features}')
print(f'Version: {model.model_version}')
"

# Retrain model
docker-compose exec backend python train_flood_model.py
```

### Database Issues
```bash
# Check database size
psql -U postgres -d floodguard -c "SELECT pg_size_pretty(pg_database_size('floodguard'));"

# Check table sizes
psql -U postgres -d floodguard -c "
SELECT 
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Check connection count
psql -U postgres -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"

# Check slow queries
psql -U postgres -d floodguard -c "
SELECT 
  query,
  mean_exec_time,
  calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
"
```

### Memory/CPU Issues
```bash
# Check container resource usage
docker stats --no-stream

# Check Python memory
docker-compose exec backend python -c "
import psutil
proc = psutil.Process()
mem = proc.memory_info()
print(f'Memory: {mem.rss / 1024 / 1024:.1f} MB')
print(f'CPU percent: {proc.cpu_percent(interval=1):.1f}%')
"

# Increase container resources
# Edit docker-compose.yml:
# services:
#   backend:
#     deploy:
#       resources:
#         limits:
#           memory: 2G
#           cpus: '2'
```

---

## Maintenance Tasks

### Weekly
1. **Review alert patterns**
   ```sql
   SELECT 
     station_id,
     alert_level,
     COUNT(*) as count,
     AVG(risk_score) as avg_risk
   FROM alerts
   WHERE created_at > NOW() - INTERVAL '7 days'
   GROUP BY station_id, alert_level
   ORDER BY count DESC;
   ```

2. **Check prediction accuracy**
   ```sql
   SELECT 
     AVG(ABS(predicted_peak - actual_peak)) as mae
   FROM (
     SELECT 
       p.predicted_peak,
       f.peak_level as actual_peak
     FROM predictions p
     JOIN flood_events f ON p.station_id = f.station_id
       AND ABS(EXTRACT(EPOCH FROM (p.prediction_time - f.event_start))) < 3600
     WHERE p.prediction_time > NOW() - INTERVAL '7 days'
   ) subquery;
   ```

3. **Backup database**
   ```bash
   pg_dump -U postgres floodguard | gzip > backup_$(date +%Y%m%d).sql.gz
   ```

### Monthly
1. **Retrain model** on latest data
2. **Update CWC station list** (new gauges added)
3. **Review & optimize slow queries**
4. **Test disaster recovery** (restore from backup)
5. **Update dependencies** (security patches)

### Quarterly
1. **Major version upgrades** (Python, Node, DB)
2. **Security audit** (dependencies, API tokens)
3. **Performance tuning** (indexes, caching)
4. **Capacity planning** (disk, memory, CPU)

---

## Deployment

### Staging Deployment
```bash
git checkout feature/complete-system
git pull origin feature/complete-system

# Test locally
docker-compose up -d
curl http://localhost:8000/api/health

# Push to staging cloud
docker build -f Dockerfile.backend -t registry/backend:staging .
docker build -f Dockerfile.frontend -t registry/frontend:staging .
docker push registry/backend:staging
docker push registry/frontend:staging

# Deploy to staging
kubectl set image deployment/backend \
  backend=registry/backend:staging --record
```

### Production Deployment
```bash
git checkout main
git tag v1.0.1  # Semantic versioning

# Build production images
docker build -f Dockerfile.backend -t registry/backend:1.0.1 .
docker build -f Dockerfile.frontend -t registry/frontend:1.0.1 .

# Push to production registry
docker push registry/backend:1.0.1
docker push registry/frontend:1.0.1

# Blue-green deployment
kubectl apply -f k8s/production-green.yml
kubectl set image deployment/backend-green \
  backend=registry/backend:1.0.1

# Wait for health checks, then switch
kubectl patch service backend -p '{"spec":{"selector":{"version":"green"}}}'
```

### Rollback
```bash
# If issues detected
kubectl rollout undo deployment/backend
kubectl rollout undo deployment/frontend

# Verify
curl http://production-api.example.com/api/health
```

---

## Incident Response

### Alert Storm (100+ alerts in 5 min)
1. Check if legitimate (extreme weather event)
2. If false alarms:
   - Increase alert threshold temporarily
   - Check model prediction anomalies
   - Verify data quality (no sensor malfunction)
3. Notify ops team
4. Post-incident: Investigate root cause

### Database Down
1. Check PostgreSQL service: `systemctl status postgresql`
2. Check disk space: `df -h /var/lib/postgresql`
3. Check connections: `psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"`
4. Restart if needed: `systemctl restart postgresql`
5. If corrupted: Restore from latest backup
6. Alert ops team, escalate

### API Hanging
1. Check CPU/memory: `top`, `docker stats`
2. Check database connections
3. Check for long-running queries
4. Graceful restart: `docker-compose restart backend`
5. If persists: Scale horizontally (add more instances)

### Data Quality Issues
1. Check latest readings: `SELECT * FROM readings ORDER BY reading_time DESC LIMIT 5;`
2. Verify CWC data hasn't changed format
3. Validate readings against historical ranges
4. Investigate sensor malfunction
5. Mark bad data: `UPDATE readings SET quality_flag = 'bad' WHERE ...`

---

## Performance Tuning

### Database
```sql
-- Analyze query plans
EXPLAIN ANALYZE
SELECT * FROM readings
WHERE station_id = 'CWC_001'
AND reading_time > NOW() - INTERVAL '7 days';

-- Add missing indexes
CREATE INDEX idx_readings_quality ON readings(quality_flag)
WHERE quality_flag != 'bad';

-- Vacuum & analyze
VACUUM ANALYZE readings;

-- Check slow queries
EXPLAIN (ANALYZE, BUFFERS) <query>;
```

### Backend
```bash
# Profile with cProfile
python -m cProfile -s cumtime backend/main.py

# Monitor with memory_profiler
pip install memory-profiler
python -m memory_profiler backend/main.py

# Use asyncpg for faster database queries
# (upgrade from psycopg2 in future)
```

### Frontend
```bash
# Bundle analysis
npm install -g webpack-bundle-analyzer
npm run build:analyze

# Lazy load components
const RiskMap = lazy(() => import('./RiskMap'));

# Optimize images (Leaflet map tiles)
# Use WebP format where supported
```

---

## Documentation & Knowledge Base

- **Architecture**: `docs/ARCHITECTURE.md`
- **API Reference**: `docs/API.md`
- **Setup Guide**: `docs/SETUP.md`
- **Code Comments**: Throughout codebase
- **Wiki**: https://github.com/helina379/sih2026/wiki (future)

---

## Contact & Escalation

- **Ops Team Lead**: ops@example.com
- **On-Call Rotation**: Pagerduty link
- **Executive Escalation**: manager@example.com
- **GitHub Issues**: https://github.com/helina379/sih2026/issues

---

**Last Updated**: September 2026  
**Status**: Production Ready ✅
