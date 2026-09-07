"""
Data ingestion and preprocessing pipeline
Schedules and manages fetches from multiple data sources
"""

import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
import os

from db import SessionLocal, Station, Reading

logger = logging.getLogger(__name__)

# Data source configurations
CWC_API_URL = "https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted"
CWC_DATATYPE_CODE = "HHS"  # Hourly water level
IMD_API_BASE = "https://api.openweathermap.org/data/2.5"
SMAP_API_BASE = "https://lis4.modaps.eosdis.nasa.gov/services/SMAP_L4_SM_gph_E/api"


class CWCDataFetcher:
    """Fetch water level data from India's Central Water Commission"""

    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        self.url = CWC_API_URL
        self.datatype_code = CWC_DATATYPE_CODE

    def fetch_station_data(
        self, station_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        Fetch water level readings for a station over date range.
        
        Args:
            station_code: CWC station code
            start_date: "YYYY-MM-DD"
            end_date: "YYYY-MM-DD"
            
        Returns:
            DataFrame with columns: station_code, datetime, water_level
        """
        specification = (
            '%7B%22where%22:%7B%22where%22:%7B%22where%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.stationCode%22,'
            f'%22operator%22:%22eq%22,%22value%22:%22{station_code}%22%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.datatypeCode%22,'
            f'%22operator%22:%22eq%22,%22value%22:%22{self.datatype_code}%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22dataValue%22,'
            '%22operator%22:%22null%22,%22value%22:%22false%22%7D%7D%7D,%22and%22:%7B%22expression%22:'
            '%7B%22valueIsRelationField%22:false,%22fieldName%22:%22id.dataTime%22,'
            f'%22operator%22:%22btn%22,%22value%22:%22{start_date}T00:00:00.000,{end_date}T00:00:00.000%22%7D%7D%7D'
        )
        params = {
            "sort-criteria": "%7B%22sortOrderDtos%22:%5B%7B%22sortDirection%22:%22ASC%22,%22field%22:%22id.dataTime%22%7D%5D%7D",
            "specification": specification,
        }

        try:
            r = requests.get(self.url, params=params, headers=self.headers, timeout=30)
            r.raise_for_status()
            data = r.json()

            rows = []
            for item in data:
                try:
                    rows.append({
                        "station_code": item["stationCode"],
                        "datetime": item["id"]["dataTime"],
                        "water_level": float(item["dataValue"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue

            return pd.DataFrame(rows)
        except Exception as e:
            logger.error(f"CWC fetch error for {station_code}: {e}")
            return pd.DataFrame()

    def store_readings(self, db: Session, readings_df: pd.DataFrame):
        """Store fetched readings in database"""
        for _, row in readings_df.iterrows():
            reading = Reading(
                station_id=row["station_code"],
                reading_time=pd.to_datetime(row["datetime"]),
                water_level=row["water_level"],
            )
            db.add(reading)
        db.commit()
        logger.info(f"Stored {len(readings_df)} readings")


class RainfallDataFetcher:
    """Fetch rainfall data from OpenWeatherMap or IMD"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")

    def fetch_rainfall(
        self, latitude: float, longitude: float, hours: int = 24
    ) -> Optional[float]:
        """
        Fetch recent rainfall in mm for a location.
        Falls back to OpenWeatherMap if IMD unavailable.
        """
        if not self.api_key:
            logger.warning("OpenWeatherMap API key not configured")
            return None

        try:
            url = f"{IMD_API_BASE}/weather?lat={latitude}&lon={longitude}&appid={self.api_key}"
            r = requests.get(url, timeout=10)
            data = r.json()
            
            # OpenWeatherMap returns 'rain' object with rainfall in last hour
            rainfall = data.get("rain", {}).get("1h", 0.0)
            return rainfall
        except Exception as e:
            logger.error(f"Rainfall fetch error: {e}")
            return None

    def store_rainfall(self, db: Session, station_id: str, rainfall_mm: float):
        """Store rainfall measurement"""
        if rainfall_mm is None:
            return

        reading = (
            db.query(Reading)
            .filter(
                Reading.station_id == station_id,
                Reading.reading_time >= datetime.utcnow() - timedelta(minutes=5),
            )
            .order_by(Reading.reading_time.desc())
            .first()
        )
        if reading:
            reading.rainfall = rainfall_mm
        else:
            reading = Reading(
                station_id=station_id,
                reading_time=datetime.utcnow(),
                rainfall=rainfall_mm,
            )
            db.add(reading)
        db.commit()


class SoilMoistureFetcher:
    """Fetch soil moisture data from SMAP or GLDAS"""

    def __init__(self, api_token: str = None):
        self.api_token = api_token or os.getenv("SMAP_API_TOKEN")

    def fetch_soil_moisture(
        self, latitude: float, longitude: float
    ) -> Optional[float]:
        """
        Fetch soil moisture saturation (%) for a location.
        Returns None if unavailable.
        """
        if not self.api_token:
            logger.warning("SMAP API token not configured")
            return None

        try:
            params = {
                "token": self.api_token,
                "latitude": latitude,
                "longitude": longitude,
                "startDate": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
                "endDate": datetime.utcnow().strftime("%Y-%m-%d"),
            }
            r = requests.get(SMAP_API_BASE, params=params, timeout=10)
            data = r.json()
            
            if data and len(data) > 0:
                # Return most recent soil moisture reading
                return float(data[-1].get("soil_moisture_percent", 50.0))
            return None
        except Exception as e:
            logger.error(f"Soil moisture fetch error: {e}")
            return None

    def store_soil_moisture(self, db: Session, station_id: str, soil_moisture_percent: float):
        """Store soil moisture measurement"""
        if soil_moisture_percent is None:
            return

        reading = (
            db.query(Reading)
            .filter(
                Reading.station_id == station_id,
                Reading.reading_time >= datetime.utcnow() - timedelta(minutes=5),
            )
            .order_by(Reading.reading_time.desc())
            .first()
        )
        if reading:
            reading.soil_moisture = soil_moisture_percent
        else:
            reading = Reading(
                station_id=station_id,
                reading_time=datetime.utcnow(),
                soil_moisture=soil_moisture_percent,
            )
            db.add(reading)
        db.commit()


class DataPipeline:
    """Orchestrates data fetching and storage"""

    def __init__(self):
        self.cwc_fetcher = CWCDataFetcher()
        self.rainfall_fetcher = RainfallDataFetcher()
        self.soil_moisture_fetcher = SoilMoistureFetcher()
        self.scheduler = BackgroundScheduler()

    def fetch_all_stations_cwc(self, db: Session):
        """Fetch latest data for all CWC stations"""
        stations = db.query(Station).filter(Station.data_source == "CWC").all()
        
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        for station in stations:
            try:
                readings_df = self.cwc_fetcher.fetch_station_data(
                    station.station_id, today, today
                )
                if not readings_df.empty:
                    self.cwc_fetcher.store_readings(db, readings_df)
                    logger.info(f"Updated station {station.name}")
            except Exception as e:
                logger.error(f"Error fetching {station.name}: {e}")

    def fetch_all_stations_rainfall(self, db: Session):
        """Fetch rainfall for all stations"""
        stations = db.query(Station).all()
        for station in stations:
            try:
                rainfall = self.rainfall_fetcher.fetch_rainfall(
                    station.latitude, station.longitude
                )
                if rainfall is not None:
                    self.rainfall_fetcher.store_rainfall(db, station.station_id, rainfall)
            except Exception as e:
                logger.error(f"Error fetching rainfall for {station.name}: {e}")

    def fetch_all_stations_soil_moisture(self, db: Session):
        """Fetch soil moisture for all stations"""
        stations = db.query(Station).all()
        for station in stations:
            try:
                soil_moisture = self.soil_moisture_fetcher.fetch_soil_moisture(
                    station.latitude, station.longitude
                )
                if soil_moisture is not None:
                    self.soil_moisture_fetcher.store_soil_moisture(
                        db, station.station_id, soil_moisture
                    )
            except Exception as e:
                logger.error(f"Error fetching soil moisture for {station.name}: {e}")

    def start_scheduler(self):
        """Start background data fetching jobs"""
        # Fetch CWC water levels every hour
        self.scheduler.add_job(
            lambda: self.fetch_all_stations_cwc(SessionLocal()),
            trigger=IntervalTrigger(hours=1),
            id="fetch_cwc",
        )

        # Fetch rainfall every 30 minutes
        self.scheduler.add_job(
            lambda: self.fetch_all_stations_rainfall(SessionLocal()),
            trigger=IntervalTrigger(minutes=30),
            id="fetch_rainfall",
        )

        # Fetch soil moisture every 6 hours (less frequent, data changes slower)
        self.scheduler.add_job(
            lambda: self.fetch_all_stations_soil_moisture(SessionLocal()),
            trigger=IntervalTrigger(hours=6),
            id="fetch_soil_moisture",
        )

        self.scheduler.start()
        logger.info("Data pipeline scheduler started")

    def stop_scheduler(self):
        """Stop background jobs"""
        self.scheduler.shutdown()
        logger.info("Data pipeline scheduler stopped")


# Global pipeline instance
_pipeline: Optional[DataPipeline] = None


def get_pipeline() -> DataPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = DataPipeline()
    return _pipeline
