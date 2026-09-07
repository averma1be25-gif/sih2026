# SETUP GUIDE - Complete Installation Instructions

## Prerequisites

- **Docker & Docker Compose** (v20.10+) - Recommended for quickest setup
- **Python 3.11+** (for local development)
- **Node.js 20+** (for frontend development)
- **PostgreSQL 15** (if not using Docker)
- **Git**
- **8GB RAM** minimum
- **2GB disk space** minimum

## Step-by-Step Installation

### Method 1: Docker Compose (Recommended - 5 minutes)

**1. Clone Repository**
```bash
git clone https://github.com/helina379/sih2026.git
cd sih2026
```

**2. Setup Environment**
```bash
cp backend/.env.example .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

**3. Start Services**
```bash
# Build images (first time only)
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend
```

**4. Initialize Database**
```bash
# Run migrations (automatically on container start)
# Or manually:
docker-compose exec backend python -m alembic upgrade head
```

**5. Access Services**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- PostgreSQL: `psql -h localhost -U postgres -d floodguard` (password: `password`)

---

### Method 2: Local Development (20 minutes)

#### Backend Setup

**1. Create Virtual Environment**
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**2. Install Dependencies**
```bash
cd backend
pip install -r requirements.txt
```

**3. Setup Environment**
```bash
cp .env.example .env
# Edit .env with your database credentials
```

**4. Create PostgreSQL Database**
```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and extensions
CREATE DATABASE floodguard;
CREATE EXTENSION postgis;
\c floodguard
\i /path/to/schema.sql
```

**5. Run Migrations**
```bash
alembic upgrade head
```

**6. Start Backend Server**
```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup

**1. Install Dependencies**
```bash
cd ..
npm install
```

**2. Setup Environment**
```bash
# Create .env.local file
echo "VITE_API_BASE=http://localhost:8000/api" > .env.local
```

**3. Start Development Server**
```bash
npm run dev
```

**4. Access Application**
- Open http://localhost:5173 in browser

---

## Database Setup

### Using Docker Compose
Database automatically initializes with PostGIS extension and schema.

### Manual Setup

**1. Install PostGIS**
```bash
# macOS
brew install postgresql postgis

# Ubuntu
sudo apt-get install postgresql postgresql-contrib postgis

# Windows: Use installer from https://www.postgresql.org/download/windows/
```

**2. Create Database**
```bash
psql -U postgres

CREATE DATABASE floodguard;
CREATE EXTENSION postgis;

\c floodguard
\i schema.sql
```

**3. Verify Setup**
```bash
psql -U postgres -d floodguard -c "SELECT PostGIS_version();"
```

---

## API Key Configuration

### OpenWeatherMap (Rainfall Data)
1. Sign up at https://openweathermap.org/api
2. Get free API key
3. Add to `.env`:
   ```
   OPENWEATHER_API_KEY=your_key_here
   ```

### NASA SMAP (Soil Moisture)
1. Register at https://lis.gsfc.nasa.gov/
2. Get API token
3. Add to `.env`:
   ```
   SMAP_API_TOKEN=your_token_here
   ```

### Twilio (SMS Alerts)
1. Sign up at https://www.twilio.com/
2. Get Account SID and Auth Token
3. Add to `.env`:
   ```
   TWILIO_ACCOUNT_SID=your_sid
   TWILIO_AUTH_TOKEN=your_token
   TWILIO_PHONE_NUMBER=+1234567890
   ```

### Email Alerts (SMTP)
1. Use your email provider (Gmail, Office365, etc.)
2. Generate app-specific password
3. Add to `.env`:
   ```
   ALERT_EMAIL=your_email@gmail.com
   ALERT_EMAIL_PASSWORD=your_app_password
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   ```

---

## Initial Data Setup

### Load Training Data
```bash
# Download INDOFLOODS dataset
python build_hilly_indofloods.py

# Build training table
python build_training_table.py

# Load data into database
python load_data.py
```

### Train ML Model
```bash
# Train XGBoost model
python train_flood_model.py

# Output: flood_model.joblib (automatically loaded at startup)
```

### Create Test User
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "admin123",
    "role": "admin"
  }'
```

---

## Verification Checklist

- [ ] Backend running at http://localhost:8000
- [ ] Frontend running at http://localhost:5173
- [ ] PostgreSQL database created
- [ ] PostGIS extension loaded
- [ ] ML model loaded (`flood_model.joblib` exists)
- [ ] API health check: `curl http://localhost:8000/api/health`
- [ ] Can login at frontend
- [ ] Stations visible on map
- [ ] Alerts working

---

## Troubleshooting

### Backend won't start
```bash
# Check logs
docker-compose logs backend

# Verify database connection
psql -h localhost -U postgres -d floodguard -c "SELECT 1;"

# Reinstall dependencies
pip install --force-reinstall -r requirements.txt
```

### Frontend won't connect to backend
```bash
# Check VITE_API_BASE environment variable
echo $VITE_API_BASE

# Should be: http://localhost:8000/api
# Update in .env.local if needed

# Check backend is running
curl http://localhost:8000/api/health
```

### Database errors
```bash
# Reset database (WARNING: deletes all data)
dropdatabasedb floodguard
creatdb floodguard
psql -d floodguard -f schema.sql
```

### Port already in use
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

---

## Next Steps

1. **Add CWC Station Data**: Populate `stations` table with real CWC gauges
2. **Configure Alerts**: Update operator email/phone in alert settings
3. **Train Model**: Run `train_flood_model.py` on your data
4. **Set Thresholds**: Adjust alert thresholds in `alert_engine.py`
5. **Deploy**: Push to production using Docker

---

## Documentation

- **API Reference**: See `docs/API.md`
- **Architecture**: See `docs/ARCHITECTURE.md`
- **Operations**: See `docs/RUNBOOK.md`

---

## Support

- Check logs: `docker-compose logs -f`
- API docs: http://localhost:8000/docs
- GitHub Issues: https://github.com/helina379/sih2026/issues
