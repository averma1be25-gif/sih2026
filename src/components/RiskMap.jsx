import { useState, useEffect } from 'react';
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
} from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import api from '../api/client';

function getRiskColor(riskLevel) {
  if (riskLevel === 'CRITICAL') return '#dc2626';
  if (riskLevel === 'HIGH') return '#f97316';
  if (riskLevel === 'MEDIUM') return '#eab308';
  return '#22c55e';
}

export function RiskMap({ onLocationSelect }) {
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchRiskMap = async () => {
      try {
        setLoading(true);
        const response = await api.get('/dashboard/risk-map');
        setStations(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch risk map:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchRiskMap();
    // Refresh every 60 seconds
    const interval = setInterval(fetchRiskMap, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="map-card"><p>Loading map...</p></div>;
  if (error) return <div className="map-card"><p style={{color: 'red'}}>Error: {error}</p></div>;

  return (
    <div className="map-card">
      <div className="card-header">
        <div>
          <span className="section-label">GEOSPATIAL MONITORING</span>
          <h2>Live Flood Risk Map</h2>
        </div>
        <div className="map-live">
          <span></span>
          LIVE
        </div>
      </div>

      <div className="map-wrapper">
        <MapContainer
          center={[30.2, 78.1]}
          zoom={9}
          scrollWheelZoom={true}
          className="flood-map"
          style={{ height: '400px', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {stations.map((station) => (
            <CircleMarker
              key={station.station_id}
              center={[station.latitude, station.longitude]}
              radius={station.risk_score > 75 ? 18 : 14}
              pathOptions={{
                color: getRiskColor(station.risk_level),
                fillColor: getRiskColor(station.risk_level),
                fillOpacity: 0.65,
                weight: 3,
              }}
              eventHandlers={{
                click: () => onLocationSelect(station),
              }}
            >
              <Popup>
                <div className="popup">
                  <strong>{station.name}</strong>
                  <p>Risk Level: <b>{station.risk_level}</b></p>
                  <p>Risk Score: {station.risk_score.toFixed(1)}%</p>
                  {station.water_level && <p>Water Level: {station.water_level.toFixed(2)} m</p>}
                  {station.rainfall && <p>Rainfall: {station.rainfall.toFixed(1)} mm</p>}
                  <p>Updated: {new Date(station.last_update).toLocaleTimeString()}</p>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>

        <div className="map-legend">
          <strong>RISK LEVEL</strong>
          <div><i style={{background: '#22c55e', display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', marginRight: '8px'}}></i>Low</div>
          <div><i style={{background: '#eab308', display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', marginRight: '8px'}}></i>Medium</div>
          <div><i style={{background: '#f97316', display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', marginRight: '8px'}}></i>High</div>
          <div><i style={{background: '#dc2626', display: 'inline-block', width: '12px', height: '12px', borderRadius: '50%', marginRight: '8px'}}></i>Critical</div>
        </div>
      </div>
    </div>
  );
}
