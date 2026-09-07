# System Architecture & Design

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  - Interactive Leaflet Map                                  │
│  - Real-time Dashboard                                      │
│  - Alert Management UI                                      │
│  - Forecast Charts (Recharts)                               │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/WebSocket
                     │
┌────────────────────▼────────────────────────────────────────┐
│              Backend API (FastAPI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐   │
│  │ Auth Module  │  │ API Handlers │  │ WebSocket Mgr  │   │
│  │ (JWT, RBAC)  │  │ (30+ routes) │  │ (Real-time)    │   │
│  └──────────────┘  └──────────────┘  └────────────────┘   │
│         │                  │                   │            │
│         └──────────┬───────┴────────────────┬──┘            │
│                    │                        │               │
└────────────────────┼────────────────────────┼───────────────┘
                     │                        │
         ┌───────────▼──────────┐   ┌────────▼──────────┐
         │  Data Pipeline       │   │  ML Model         │
         │  ┌────────────────┐  │   │  ┌────────────┐   │
         │  │CWC Fetcher     │  │   │  │XGBoost     │   │
         │  │Rainfall Fetcher│  │   │  │Predictions │   │
         │  │Soil Moisture   │  │   │  │Inference   │   │
         │  │Scheduler       │  │   │  └────────────┘   │
         │  └────────────────┘  │   └───────────────────┘
         └──────────┬───────────┘           │
                    │                       │
         ┌──────────▼──────────┐   ┌────────▼──────────┐
         │ Alert Engine        │   │  Feature Engineer │
         │ ┌────────────────┐  │   │  ┌────────────┐   │
         │ │Thresholding    │  │   │  │Rainfall    │   │
         │ │Deduplication   │  │   │  │Water Level │   │
         │ │Email/SMS       │  │   │  │Soil Moist  │   │
         │ │Persistence     │  │   │  └────────────┘   │
         │ └────────────────┘  │   └───────────────────┘
         └──────────┬───────────┘           │
                    │                       │
         ┌──────────▼───────────────────────▼────────┐
         │      PostgreSQL + PostGIS Database        │
         │  ┌──────────┐  ┌──────────┐  ┌────────┐  │
         │  │ Stations │  │ Readings │  │ Alerts │  │
         │  │ (spatial)│  │(time-   │  │(      │  │
         │  │          │  │ series) │  │active) │  │
         │  └──────────┘  └──────────┘  └────────┘  │
         │  ┌──────────┐  ┌──────────┐              │
         │  │ Floods   │  │ Users    │              │
         │  │ Events   │  │ (RBAC)   │              │
         │  └──────────┘  └──────────┘              │
         └───────────────────────────────────────────┘
```

## Data Flow Diagram

```
1. DATA INGESTION
   ┌─────────────────────────────────────────────────┐
   │ CWC Server  OpenWeatherMap  NASA SMAP  Sensors │
   └────────────────┬──────────────┬─────────────────┘
                    │              │
                    ▼              ▼
            Data Pipeline (Scheduler)
            - Fetches every 1h/30m/6h
            - Parses & validates
            - Stores in DB
                    │
                    ▼
            PostgreSQL Readings Table

2. PREDICTION
   ┌─────────────────────────────────┐
   │ New Reading Arrives             │
   └────────────────┬────────────────┘
                    │
                    ▼
           Feature Engineering
           - Recent rainfall (T1d-T10d)
           - Water level trend
           - Soil saturation
           - Catchment features
                    │
                    ▼
           ML Model (XGBoost)
           ├─ Input: features dict
           ├─ Model: flood_model.joblib
           └─ Output: severity_ratio
                    │
                    ▼
        Convert to Risk Score (0-100%)
        └─ Severity Ratio × 20 + 50 = Risk%
                    │
                    ▼
        Store Prediction in DB

3. ALERT GENERATION
   ┌──────────────────────────────────┐
   │ Risk Score >= 50%?               │
   └────────┬──────────────────────────┘
            │
       Yes  ├─► Check for recent duplicate
            │   (within 30 min)
            │
            ├─► Determine alert level
            │   ├─ 30-50: LOW (not alerted)
            │   ├─ 50-75: MEDIUM
            │   ├─ 75-90: HIGH
            │   └─ 90+: CRITICAL
            │
            ├─► Create Alert record in DB
            │
            └─► Dispatch via channels
                ├─ Email to operators
                ├─ SMS via Twilio
                └─ Dashboard WebSocket

4. OPERATOR RESPONSE
   ┌────────────────────────────────┐
   │ Alert appears on dashboard     │
   └────────┬───────────────────────┘
            │
            ├─► Operator views details
            ├─► Acknowledges alert
            ├─► Views 6-hour forecast
            ├─► Finds nearby stations (50km radius)
            └─► Dismisses or escalates
                    │
                    ▼
           Alert Status logged in DB
```

## Component Details

### 1. Frontend (React 19 + Vite)

**Key Components:**
- `RiskMap.jsx`: Leaflet map with station markers, fetches from `/dashboard/risk-map`
- `ForecastChart.jsx`: 6-hour prediction line chart via `/stations/{id}/forecast`
- `AlertsList.jsx`: Real-time alert management, acknowledge/dismiss via PUT endpoints
- `DataCards.jsx`: Live readings (rainfall, water level, soil moisture)
- `App.jsx`: Main container, page routing

**Communication:**
- REST API via axios (see `api/client.js`)
- WebSocket for real-time updates (`useWebSocket.js` hook)
- Local storage for JWT token persistence

**Styling:**
- CSS Grid/Flexbox responsive layout
- Color scheme: Red (critical) → Orange (high) → Yellow (medium) → Green (low)

### 2. Backend (FastAPI)

**Core Modules:**

**main.py (480+ lines)**
- FastAPI app initialization
- 30+ endpoints (auth, stations, readings, predictions, alerts, dashboard, geospatial)
- CORS middleware, health checks
- WebSocket connection manager

**db.py (360+ lines)**
- SQLAlchemy ORM models:
  - `Station`: Gauge locations with PostGIS geometry
  - `Reading`: Time-series water levels, rainfall, soil moisture
  - `Prediction`: ML model outputs
  - `Alert`: Generated alerts with acknowledgment tracking
  - `FloodEvent`: Historical flood events
  - `CatchmentFeature`: Terrain-derived features
  - `User`: Authentication & RBAC
- Indexes on `(station_id, reading_time)`, `(location)`, etc.
- Cascade delete relationships

**models.py (180+ lines)**
- `FloodModel` class: Loads `flood_model.joblib` at startup
- `predict()`: Converts features dict → (severity_ratio, risk_score, confidence)
- `_baseline_prediction()`: Fallback when model unavailable
- Singleton pattern for global model instance

**alert_engine.py (320+ lines)**
- `AlertDebouncer`: Suppresses repeat alerts within 30-min window
- `AlertDispatcher`: Coordinates alert creation & delivery
- `EmailNotifier`: SMTP integration (Gmail, Office365)
- `SMSNotifier`: Twilio integration
- Database persistence (no alerts lost on restart)

**data_pipeline.py (380+ lines)**
- `CWCDataFetcher`: Queries CWC API, stores readings
- `RainfallDataFetcher`: OpenWeatherMap API
- `SoilMoistureFetcher`: NASA SMAP API
- `DataPipeline`: APScheduler jobs
  - CWC water levels: every 1 hour
  - Rainfall: every 30 minutes
  - Soil moisture: every 6 hours
- Graceful error handling (logs, continues)

**auth.py (160+ lines)**
- JWT token generation & validation (24-hour expiry)
- Password hashing with bcrypt
- Role-based access control: admin, operator, viewer
- `verify_token()`, `create_access_token()`, `authenticate_user()`

**schemas.py (180+ lines)**
- Pydantic models for request/response validation
- Nested models for complex objects
- `from_attributes=True` for ORM compatibility

### 3. Database (PostgreSQL 15 + PostGIS)

**Schema Highlights:**

```sql
-- Spatial index for fast "find nearby stations"
CREATE INDEX idx_station_location ON stations USING GIST(location);

-- Time-series index for readings
CREATE INDEX idx_readings_station_time ON readings(station_id, reading_time DESC);

-- Full-text search on alert reasons (future)
ALTER TABLE alerts ADD COLUMN search_vector tsvector;
```

**Table Relationships:**
```
Stations (1) ──────────────► (M) Readings
    │                             │
    ├──────────────────────────────┤
    │                              ▼
    │                         Predictions
    │                              │
    ├──────────────────────────────┤
    │                              ▼
    │                           Alerts
    │
    ├──────────────────────────► CatchmentFeatures
    │
    └──────────────────────────► FloodEvents

Users (1) ────────────────► (M) Alerts (acknowledged_by)
```

### 4. ML Model Training

**Data Source:** INDOFLOODS + CWC historical data
**Features:**
- Recent rainfall: T1d, T2d, ..., T10d (daily totals)
- Catchment shape: Area, length, drainage density, form factor
- Land/soil: Type, forest cover, urban %, road density
- Climate: Annual precip, mean temperature

**Target:** Severity Ratio = Peak Level / Danger Level
- < 1.0: No flood (non-event)
- ≥ 1.0: Severe flood (event)

**Model:** XGBoost with group-aware 5-fold CV
- Groups by `station_id` (no data leakage)
- Metrics: MAE, RMSE, R², classification report

**Output:** `flood_model.joblib` (joblib serialized)

### 5. Alert Workflow

```
Reading Received
    │
    ▼
Check if recent prediction exists
    │
    ├─► No  ─────────────┐
    │                   │
    └─► Yes ────────────┼────► Extract features
                        │        from reading & history
                        │              │
                        └──────────────┤
                                       ▼
                            ML Model Prediction
                            (severity_ratio)
                                       │
                                       ▼
                            Convert to Risk Score
                            (0-100 scale)
                                       │
                                       ▼
                            Risk >= 50%?
                                       │
                        ┌──────Yes─────┴─────No──────┐
                        │                             │
                        ▼                             ▼
                   Continue                      Exit
                        │
                        ▼
                   Get Alert Level
                   ├─ MEDIUM (50-75%)
                   ├─ HIGH (75-90%)
                   └─ CRITICAL (90%+)
                        │
                        ▼
                   Check Dedup
                   (recent alert?)
                        │
                   ┌────┴────┐
                   │          │
                 Yes         No
                   │          │
                   ▼          ▼
                Skip      Create Alert
                        in Database
                        │
                        ▼
                   Dispatch
                   ├─ Email to ops
                   ├─ SMS to ops
                   └─ WebSocket broadcast
                        │
                        ▼
                   Operator Response
                   ├─ Acknowledge
                   ├─ Dismiss
                   └─ View Forecast
```

## Scalability Considerations

### Current Limits
- Single FastAPI instance (8 workers)
- PostgreSQL connection pool (20 connections)
- 274 monitoring stations
- ~1000 readings/day per station

### Production Scaling
1. **Horizontal**: Run multiple FastAPI instances behind load balancer (Nginx)
2. **Database**: Read replicas for queries, write to primary
3. **Caching**: Redis for frequent queries (dashboard metrics)
4. **Message Queue**: Celery for heavy tasks (ML training, batch alerts)
5. **CDN**: CloudFront for static frontend assets

## Security Considerations

1. **Authentication**: JWT with 24-hour expiry, refresh tokens (future)
2. **Authorization**: Role-based access control (admin/operator/viewer)
3. **Data**: Passwords hashed with bcrypt, API keys in env vars
4. **Communication**: HTTPS enforced in production
5. **SQL Injection**: SQLAlchemy ORM prevents (parameterized queries)
6. **CORS**: Restricted in production to trusted origins

## Monitoring & Observability

**Logging:**
- All data fetches logged to file
- Prediction requests logged with features + output
- Alert dispatch logged with recipient, channel, status

**Metrics (Future):**
- Prometheus metrics: request latency, error rates, model accuracy
- Grafana dashboards for ops team

**Health Checks:**
- `/api/health` endpoint
- Docker healthchecks on containers
- Database connection validation

---

For deployment details, see `SETUP.md` and `RUNBOOK.md`.
