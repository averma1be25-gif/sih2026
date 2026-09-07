"""
Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class StationBase(BaseModel):
    name: str
    state: str
    latitude: float
    longitude: float
    region: Optional[str] = None
    data_source: str = "CWC"


class StationCreate(StationBase):
    station_id: str
    danger_level: Optional[float] = None
    warning_level: Optional[float] = None


class StationResponse(StationBase):
    station_id: str
    danger_level: Optional[float]
    warning_level: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReadingResponse(BaseModel):
    id: int
    station_id: str
    reading_time: datetime
    water_level: Optional[float]
    rainfall: Optional[float]
    soil_moisture: Optional[float]
    temperature: Optional[float]
    quality_flag: str

    class Config:
        from_attributes = True


class PredictionResponse(BaseModel):
    id: str
    station_id: str
    prediction_time: datetime
    severity_ratio: float
    risk_score: float
    confidence: float
    model_version: str

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    id: str
    station_id: str
    alert_level: str
    risk_score: float
    predicted_peak: Optional[float]
    trigger_reason: str
    is_active: bool
    acknowledged: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FloodEventResponse(BaseModel):
    id: int
    station_id: str
    event_start: datetime
    event_end: Optional[datetime]
    peak_level: float
    danger_level: float
    severity_ratio: float
    severity_label: str
    source_dataset: str
    confirmed: bool

    class Config:
        from_attributes = True


class PredictionRequest(BaseModel):
    station_id: str
    rainfall_mm: float = Field(default=0, ge=0)
    water_level_m: float = Field(ge=0)
    soil_saturation_percent: float = Field(ge=0, le=100, default=50)
    hours_ahead: int = Field(default=6, ge=1, le=24)


class RiskMapResponse(BaseModel):
    station_id: str
    name: str
    latitude: float
    longitude: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    risk_score: float
    water_level: Optional[float]
    rainfall: Optional[float]
    last_update: datetime

    class Config:
        from_attributes = True


class DashboardMetrics(BaseModel):
    total_stations: int
    stations_at_risk: int
    active_alerts: int
    critical_alerts: int
    high_alerts: int
    last_updated: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
