import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../api/client';

export function ForecastChart({ stationId }) {
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!stationId) return;

    const fetchForecast = async () => {
      try {
        setLoading(true);
        const response = await api.get(`/stations/${stationId}/forecast?hours=6`);
        setForecast(response.data.forecast);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch forecast:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchForecast();
  }, [stationId]);

  if (loading) return <div className="chart-card"><p>Loading forecast...</p></div>;
  if (error) return <div className="chart-card"><p style={{color: 'red'}}>Error: {error}</p></div>;
  if (forecast.length === 0) return null;

  return (
    <div className="chart-card">
      <div className="card-header">
        <div>
          <span className="section-label">AI PREDICTION</span>
          <h2>6-Hour Flood Forecast</h2>
        </div>
        <span className="forecast-badge">NEXT 6 HOURS</span>
      </div>

      <div className="chart-container">
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={forecast} margin={{ top: 15, right: 20, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="4 4" />
            <XAxis dataKey="hour" label={{ value: 'Hours Ahead', position: 'insideBottomRight', offset: -5 }} />
            <YAxis domain={[0, 100]} label={{ value: 'Risk %', angle: -90, position: 'insideLeft' }} />
            <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
            <Line type="monotone" dataKey="risk_score" stroke="#f97316" strokeWidth={3} dot={{ r: 5 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
