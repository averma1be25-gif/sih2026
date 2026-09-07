import { useState, useEffect } from 'react';
import api from '../api/client';

export function DataCard({ icon, title, value, unit, status }) {
  return (
    <div className="data-card">
      <div className="data-card-top">
        <div className="data-icon">{icon}</div>
        <span className="live-dot">LIVE</span>
      </div>
      <p className="data-title">{title}</p>
      <div className="data-value">
        {value !== undefined && value !== null ? value : 'N/A'}
        {unit && <span>{unit}</span>}
      </div>
      <p className="data-status">{status}</p>
    </div>
  );
}

export function StationDataCards({ stationId }) {
  const [reading, setReading] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!stationId) return;

    const fetchReading = async () => {
      try {
        setLoading(true);
        const response = await api.get(`/stations/${stationId}/latest`);
        setReading(response.data);
      } catch (err) {
        console.error('Failed to fetch reading:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchReading();
    // Refresh every 60 seconds
    const interval = setInterval(fetchReading, 60000);
    return () => clearInterval(interval);
  }, [stationId]);

  if (!reading) return null;

  return (
    <div className="data-grid">
      <DataCard
        icon="🌧️"
        title="Rainfall"
        value={reading.rainfall?.toFixed(1)}
        unit="mm"
        status={reading.rainfall > 50 ? 'Heavy rainfall' : 'Moderate rainfall'}
      />
      <DataCard
        icon="🌊"
        title="River Level"
        value={reading.water_level?.toFixed(2)}
        unit="m"
        status={reading.water_level > 2 ? 'Rising' : 'Stable'}
      />
      <DataCard
        icon="🌱"
        title="Soil Moisture"
        value={reading.soil_moisture?.toFixed(0)}
        unit="%"
        status={reading.soil_moisture > 70 ? 'Saturated' : 'Moderate'}
      />
      <DataCard
        icon="🌡️"
        title="Temperature"
        value={reading.temperature?.toFixed(1)}
        unit="°C"
        status="Current"
      />
    </div>
  );
}
