"""
Main FastAPI application with all endpoints
Handles predictions, alerts, stations, and real-time data
"""

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from datetime import datetime, timedelta
import logging
import json
from typing import List, Optional
import asyncio

from db import init_db, get_db, Station, Reading, Alert, Prediction, FloodEvent
from auth import (
    verify_token, create_access_token, authenticate_user, create_user,
    TokenData, UserCreate, is_operator, is_admin
)
from schemas import (
    StationResponse, StationCreate, ReadingResponse, AlertResponse,
    PredictionResponse, DashboardMetrics, LoginRequest, TokenResponse,
    PredictionRequest, RiskMapResponse, FloodEventResponse
)
from models import get_model
from alert_engine import get_alert_dispatcher, get_alert_level
from data_pipeline import get_pipeline

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="FloodGuard - Flash Flood Prediction System",
    description="Multi-source flood prediction for hilly Indian regions",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
init_db()

# Start data pipeline
pipeline = get_pipeline()
pipeline.start_scheduler()


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.post("/api/auth/register", response_model=TokenResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    existing_user = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    user = create_user(
        db, user_data.username, user_data.email, user_data.password, user_data.role
    )
    
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )
    
    return TokenResponse(
        access_token=access_token,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
    )


@app.post("/api/auth/login", response_model=TokenResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token"""
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}
    )
    
    return TokenResponse(
        access_token=access_token,
        user={
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
    )


def get_current_user(token: str = None, db: Session = Depends(get_db)) -> TokenData:
    """Validate JWT token and return user data"""
    if token is None:
        # Allow public access for some endpoints
        return TokenData(username="public", role="viewer")
    
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token_data


# ============================================================================
# Station Endpoints
# ============================================================================

@app.post("/api/stations", response_model=StationResponse, status_code=201)
def create_station(station: StationCreate, db: Session = Depends(get_db)):
    """Create a new monitoring station"""
    existing = db.query(Station).filter(Station.station_id == station.station_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Station already exists")
    
    from geoalchemy2.elements import WKTElement
    location = WKTElement(f"POINT({station.longitude} {station.latitude})", srid=4326)
    
    new_station = Station(
        station_id=station.station_id,
        name=station.name,
        state=station.state,
        latitude=station.latitude,
        longitude=station.longitude,
        region=station.region,
        data_source=station.data_source,
        danger_level=station.danger_level,
        warning_level=station.warning_level,
        location=location,
    )
    db.add(new_station)
    db.commit()
    db.refresh(new_station)
    return new_station


@app.get("/api/stations", response_model=List[StationResponse])
def list_stations(db: Session = Depends(get_db)):
    """List all monitoring stations"""
    stations = db.query(Station).all()
    return stations


@app.get("/api/stations/{station_id}", response_model=StationResponse)
def get_station(station_id: str, db: Session = Depends(get_db)):
    """Get details for a specific station"""
    station = db.query(Station).filter(Station.station_id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    return station


# ============================================================================
# Readings & Live Data Endpoints
# ============================================================================

@app.get("/api/stations/{station_id}/readings", response_model=List[ReadingResponse])
def get_station_readings(
    station_id: str,
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db)
):
    """Get recent readings for a station"""
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)
    readings = db.query(Reading).filter(
        and_(
            Reading.station_id == station_id,
            Reading.reading_time >= cutoff_time
        )
    ).order_by(desc(Reading.reading_time)).all()
    return readings


@app.get("/api/stations/{station_id}/latest")
def get_latest_reading(station_id: str, db: Session = Depends(get_db)):
    """Get most recent reading for a station"""
    reading = db.query(Reading).filter(
        Reading.station_id == station_id
    ).order_by(desc(Reading.reading_time)).first()
    
    if not reading:
        raise HTTPException(status_code=404, detail="No readings found")
    
    station = db.query(Station).filter(Station.station_id == station_id).first()
    
    return {
        "station_id": station_id,
        "station_name": station.name if station else "Unknown",
        "water_level": reading.water_level,
        "rainfall": reading.rainfall,
        "soil_moisture": reading.soil_moisture,
        "reading_time": reading.reading_time,
    }


# ============================================================================
# Prediction Endpoints
# ============================================================================

@app.post("/api/predict", response_model=PredictionResponse)
def predict_flood_risk(request: PredictionRequest, db: Session = Depends(get_db)):
    """Get flood risk prediction for a station"""
    station = db.query(Station).filter(Station.station_id == request.station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    
    # Prepare features for model
    model = get_model()
    features = {
        "recent_rainfall_mm": request.rainfall_mm,
        "water_level_change_m_per_hour": 0.1,  # TODO: calculate from recent readings
        "soil_saturation_percent": request.soil_saturation_percent,
    }
    
    severity_ratio, risk_score, confidence = model.predict(features)
    
    # Store prediction in DB
    prediction = Prediction(
        station_id=request.station_id,
        prediction_time=datetime.utcnow(),
        horizon_hours=request.hours_ahead,
        severity_ratio=severity_ratio,
        risk_score=risk_score,
        confidence=confidence,
        model_version=model.model_version,
        features_used=json.dumps(features),
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    
    # Check if alert should be triggered
    if risk_score >= 50:  # MEDIUM or higher
        dispatcher = get_alert_dispatcher()
        dispatcher.dispatch_alert(
            db, station, risk_score, severity_ratio,
            channels=["email", "dashboard"]
        )
    
    return prediction


@app.get("/api/stations/{station_id}/forecast")
def get_flood_forecast(station_id: str, hours: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """Get flood risk forecast for next N hours"""
    station = db.query(Station).filter(Station.station_id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    
    # Get recent readings to estimate trend
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_readings = db.query(Reading).filter(
        and_(
            Reading.station_id == station_id,
            Reading.reading_time >= cutoff
        )
    ).order_by(Reading.reading_time).all()
    
    if not recent_readings:
        raise HTTPException(status_code=404, detail="No readings available")
    
    # Build forecast by calculating risk for each hour
    model = get_model()
    forecast_points = []
    
    latest_reading = recent_readings[-1]
    water_level_trend = 0.05  # TODO: calculate from readings
    
    for i in range(1, hours + 1):
        # Simple projection: assume trend continues
        projected_level = (latest_reading.water_level or 0) + (water_level_trend * i)
        
        features = {
            "recent_rainfall_mm": latest_reading.rainfall or 0,
            "water_level_change_m_per_hour": water_level_trend,
            "soil_saturation_percent": latest_reading.soil_moisture or 50,
        }
        
        _, risk_score, _ = model.predict(features)
        
        forecast_points.append({
            "hour": i,
            "time": (datetime.utcnow() + timedelta(hours=i)).isoformat(),
            "risk_score": risk_score,
            "risk_level": get_alert_level(risk_score).value,
        })
    
    return {"station_id": station_id, "forecast": forecast_points}


# ============================================================================
# Alert Endpoints
# ============================================================================

@app.get("/api/alerts", response_model=List[AlertResponse])
def get_alerts(
    active_only: bool = True,
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """List alerts (optionally filter to active only)"""
    query = db.query(Alert)
    if active_only:
        query = query.filter(Alert.is_active == True)
    
    alerts = query.order_by(desc(Alert.created_at)).limit(limit).all()
    return alerts


@app.get("/api/alerts/{station_id}", response_model=List[AlertResponse])
def get_station_alerts(station_id: str, db: Session = Depends(get_db)):
    """Get alerts for a specific station"""
    alerts = db.query(Alert).filter(
        Alert.station_id == station_id
    ).order_by(desc(Alert.created_at)).all()
    return alerts


@app.put("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, operator_id: str, db: Session = Depends(get_db)):
    """Mark an alert as acknowledged"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = True
    alert.acknowledged_by = operator_id
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    
    return {"status": "acknowledged", "alert_id": alert_id}


@app.put("/api/alerts/{alert_id}/dismiss")
def dismiss_alert(alert_id: str, db: Session = Depends(get_db)):
    """Dismiss an alert"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_active = False
    alert.dismissed_at = datetime.utcnow()
    db.commit()
    
    return {"status": "dismissed", "alert_id": alert_id}


# ============================================================================
# Geospatial Endpoints
# ============================================================================

@app.get("/api/nearby-risk")
def get_nearby_risk(
    latitude: float,
    longitude: float,
    radius_km: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Find all at-risk stations within radius"""
    from geoalchemy2.functions import ST_DWithin, ST_Point
    
    # Use PostGIS to find stations within radius
    stations = db.query(Station).filter(
        ST_DWithin(Station.location, ST_Point(longitude, latitude, srid=4326), radius_km * 1000)
    ).all()
    
    result = []
    for station in stations:
        latest_reading = db.query(Reading).filter(
            Reading.station_id == station.station_id
        ).order_by(desc(Reading.reading_time)).first()
        
        latest_prediction = db.query(Prediction).filter(
            Prediction.station_id == station.station_id
        ).order_by(desc(Prediction.prediction_time)).first()
        
        risk_score = latest_prediction.risk_score if latest_prediction else 0
        
        result.append({
            "station_id": station.station_id,
            "name": station.name,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "distance_km": (((latitude - station.latitude)**2 + (longitude - station.longitude)**2)**0.5) * 111,  # Rough approximation
            "risk_score": risk_score,
            "risk_level": get_alert_level(risk_score).value,
        })
    
    return sorted(result, key=lambda x: x["risk_score"], reverse=True)


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/api/dashboard/metrics", response_model=DashboardMetrics)
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """Get high-level dashboard metrics"""
    total_stations = db.query(Station).count()
    
    # Stations with recent predictions showing risk >= 50
    cutoff = datetime.utcnow() - timedelta(hours=1)
    at_risk = db.query(Station).join(Prediction).filter(
        and_(
            Prediction.prediction_time >= cutoff,
            Prediction.risk_score >= 50
        )
    ).distinct().count()
    
    active_alerts = db.query(Alert).filter(Alert.is_active == True).count()
    critical_alerts = db.query(Alert).filter(
        and_(Alert.is_active == True, Alert.alert_level == "CRITICAL")
    ).count()
    high_alerts = db.query(Alert).filter(
        and_(Alert.is_active == True, Alert.alert_level == "HIGH")
    ).count()
    
    return DashboardMetrics(
        total_stations=total_stations,
        stations_at_risk=at_risk,
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        high_alerts=high_alerts,
        last_updated=datetime.utcnow(),
    )


@app.get("/api/dashboard/risk-map", response_model=List[RiskMapResponse])
def get_risk_map(db: Session = Depends(get_db)):
    """Get risk scores for all stations (for map visualization)"""
    stations = db.query(Station).all()
    result = []
    
    for station in stations:
        latest_prediction = db.query(Prediction).filter(
            Prediction.station_id == station.station_id
        ).order_by(desc(Prediction.prediction_time)).first()
        
        latest_reading = db.query(Reading).filter(
            Reading.station_id == station.station_id
        ).order_by(desc(Reading.reading_time)).first()
        
        risk_score = latest_prediction.risk_score if latest_prediction else 0
        last_update = latest_prediction.prediction_time if latest_prediction else datetime.utcnow()
        
        result.append(RiskMapResponse(
            station_id=station.station_id,
            name=station.name,
            latitude=station.latitude,
            longitude=station.longitude,
            risk_level=get_alert_level(risk_score).value,
            risk_score=risk_score,
            water_level=latest_reading.water_level if latest_reading else None,
            rainfall=latest_reading.rainfall if latest_reading else None,
            last_update=last_update,
        ))
    
    return result


# ============================================================================
# Historical Data Endpoints
# ============================================================================

@app.get("/api/flood-events", response_model=List[FloodEventResponse])
def get_flood_events(
    station_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get historical flood events"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = db.query(FloodEvent).filter(FloodEvent.event_start >= cutoff)
    
    if station_id:
        query = query.filter(FloodEvent.station_id == station_id)
    
    events = query.order_by(desc(FloodEvent.event_start)).all()
    return events


# ============================================================================
# WebSocket Endpoints (Real-time Updates)
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"WebSocket broadcast error: {e}")


manager = ConnectionManager()


@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time flood updates"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo received data to all connected clients
            await manager.broadcast({"type": "update", "data": json.loads(data)})
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)


# ============================================================================
# Health & Info Endpoints
# ============================================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/info")
def api_info():
    """API information and metadata"""
    return {
        "name": "FloodGuard API",
        "version": "1.0.0",
        "description": "Multi-source flash flood prediction for hilly Indian regions",
        "data_sources": ["CWC", "OpenWeatherMap", "SMAP"],
        "documentation": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
