"""
Database layer using SQLAlchemy ORM for PostgreSQL + PostGIS
Handles all station, readings, flood events, and alerts persistence
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Numeric, Boolean, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from datetime import datetime
import os
import uuid

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/floodguard"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Station(Base):
    """Gauge station representing a monitoring location"""
    __tablename__ = "stations"

    station_id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    state = Column(String)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location = Column(Geometry('POINT', srid=4326), nullable=False)  # PostGIS geography
    threshold_source = Column(String, default="percentile_proxy")  # 'official' or 'percentile_proxy'
    danger_level = Column(Numeric, nullable=True)  # Known danger threshold for this station
    warning_level = Column(Numeric, nullable=True)  # Known warning threshold
    region = Column(String)  # e.g., 'Uttarakhand', 'Himachal Pradesh'
    data_source = Column(String)  # 'CWC' or 'INDOFLOODS'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    readings = relationship("Reading", back_populates="station", cascade="all, delete-orphan")
    flood_events = relationship("FloodEvent", back_populates="station", cascade="all, delete-orphan")
    catchment_features = relationship("CatchmentFeature", back_populates="station", uselist=False)
    alerts = relationship("Alert", back_populates="station", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="station", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_station_location', 'location'),
        Index('idx_station_state', 'state'),
        Index('idx_station_region', 'region'),
    )


class Reading(Base):
    """Hourly water level reading from a gauge station"""
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, ForeignKey("stations.station_id"), nullable=False, index=True)
    reading_time = Column(DateTime, nullable=False, index=True)
    water_level = Column(Numeric, nullable=True)  # meters or appropriate unit
    rainfall = Column(Numeric, nullable=True)  # mm
    soil_moisture = Column(Numeric, nullable=True)  # % saturation
    temperature = Column(Numeric, nullable=True)  # Celsius
    quality_flag = Column(String, default="good")  # 'good', 'suspicious', 'bad'
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationship
    station = relationship("Station", back_populates="readings")

    __table_args__ = (
        Index('idx_readings_station_time', 'station_id', 'reading_time'),
        Index('idx_readings_time', 'reading_time'),
    )


class FloodEvent(Base):
    """Recorded or detected flood event at a station"""
    __tablename__ = "flood_events"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, ForeignKey("stations.station_id"), nullable=False, index=True)
    event_start = Column(DateTime, nullable=False, index=True)
    event_end = Column(DateTime, nullable=True)
    peak_level = Column(Numeric, nullable=False)
    danger_level = Column(Numeric, nullable=False)
    severity_ratio = Column(Numeric)  # peak_level / danger_level
    severity_label = Column(String)  # 'Moderate', 'Severe', 'Extreme'
    threshold_source = Column(String)  # 'official' or 'percentile_proxy'
    source_dataset = Column(String)  # 'INDOFLOODS', 'CWC_derived', or 'real_time'
    confirmed = Column(Boolean, default=False)  # Manually verified
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    station = relationship("Station", back_populates="flood_events")

    __table_args__ = (
        Index('idx_events_station', 'station_id'),
        Index('idx_events_time', 'event_start', 'event_end'),
    )


class CatchmentFeature(Base):
    """Terrain and hydrological features for a catchment (hilly regions)"""
    __tablename__ = "catchment_features"

    station_id = Column(String, ForeignKey("stations.station_id"), primary_key=True)
    catchment_area = Column(Numeric)  # km2
    drainage_density = Column(Numeric)  # km/km2
    form_factor = Column(Numeric)
    elongation_ratio = Column(Numeric)
    compactness_coefficient = Column(Numeric)
    relief_ratio = Column(Numeric)
    drainage_texture = Column(Numeric)
    catchment_length = Column(Numeric)  # km
    land_cover = Column(String)  # e.g., 'forest', 'agriculture', 'urban'
    soil_type = Column(String)  # e.g., 'loam', 'clay', 'sandy'
    lithology = Column(String)  # rock type
    slope_mean = Column(Numeric)  # degrees or %
    elevation_mean = Column(Numeric)  # meters
    aspect = Column(String)  # 'N', 'E', 'S', 'W', 'NE', etc.
    forest_cover_percent = Column(Numeric)  # %
    impervious_percent = Column(Numeric)  # % urban/paved
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    station = relationship("Station", back_populates="catchment_features")


class Alert(Base):
    """Generated flood alert for a station"""
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    station_id = Column(String, ForeignKey("stations.station_id"), nullable=False, index=True)
    alert_level = Column(String, nullable=False)  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    risk_score = Column(Numeric, nullable=False)  # 0-100
    predicted_peak = Column(Numeric, nullable=True)  # predicted peak level
    trigger_reason = Column(String)  # e.g., 'water_level_rising', 'heavy_rainfall', 'soil_saturated'
    is_active = Column(Boolean, default=True, index=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String, nullable=True)  # username/operator ID
    acknowledged_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    station = relationship("Station", back_populates="alerts")

    __table_args__ = (
        Index('idx_alerts_station_active', 'station_id', 'is_active'),
        Index('idx_alerts_level', 'alert_level'),
        Index('idx_alerts_created', 'created_at'),
    )


class Prediction(Base):
    """ML model prediction for flood risk at a station"""
    __tablename__ = "predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    station_id = Column(String, ForeignKey("stations.station_id"), nullable=False, index=True)
    prediction_time = Column(DateTime, nullable=False, index=True)  # When prediction was made
    horizon_hours = Column(Integer)  # Forecast horizon (e.g., 6, 12, 24)
    severity_ratio = Column(Numeric, nullable=False)  # Model output: predicted peak / danger
    risk_score = Column(Numeric, nullable=False)  # 0-100 for UI display
    confidence = Column(Numeric)  # 0-1, model confidence
    model_version = Column(String)  # e.g., 'xgboost_v1.0'
    features_used = Column(Text)  # JSON: list of features and their values
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationship
    station = relationship("Station", back_populates="predictions")

    __table_args__ = (
        Index('idx_predictions_station_time', 'station_id', 'prediction_time'),
        Index('idx_predictions_time', 'prediction_time'),
    )


class User(Base):
    """System user for authentication and authorization"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="operator")  # 'admin', 'operator', 'viewer'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    """Initialize database with all tables"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI: yields a database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
