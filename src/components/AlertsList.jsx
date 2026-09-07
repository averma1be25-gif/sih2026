import { useState, useEffect } from 'react';
import api from '../api/client';

export function AlertsList({ stationId }) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        setLoading(true);
        const url = stationId ? `/alerts/${stationId}` : '/alerts?active_only=true';
        const response = await api.get(url);
        setAlerts(response.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch alerts:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchAlerts();
    // Refresh every 30 seconds
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, [stationId]);

  const handleAcknowledge = async (alertId) => {
    try {
      await api.put(`/alerts/${alertId}/acknowledge`, { operator_id: 'current_user' });
      // Refresh alerts
      const url = stationId ? `/alerts/${stationId}` : '/alerts?active_only=true';
      const response = await api.get(url);
      setAlerts(response.data);
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  const handleDismiss = async (alertId) => {
    try {
      await api.put(`/alerts/${alertId}/dismiss`);
      // Remove from list
      setAlerts(alerts.filter(a => a.id !== alertId));
    } catch (err) {
      console.error('Failed to dismiss alert:', err);
    }
  };

  if (loading) return <div><p>Loading alerts...</p></div>;
  if (error) return <div><p style={{color: 'red'}}>Error: {error}</p></div>;
  if (alerts.length === 0) return <div><p>No active alerts</p></div>;

  return (
    <div>
      {alerts.map((alert) => (
        <div key={alert.id} className="alert-card" style={{
          borderLeft: `4px solid ${alert.alert_level === 'CRITICAL' ? '#dc2626' : alert.alert_level === 'HIGH' ? '#f97316' : '#eab308'}`
        }}>
          <div className="alert-icon">
            {alert.alert_level === 'CRITICAL' ? '🔴' : alert.alert_level === 'HIGH' ? '🟠' : '🟡'}
          </div>
          <div className="alert-content">
            <div className="alert-top">
              <span className="alert-tag" style={{
                background: alert.alert_level === 'CRITICAL' ? '#dc2626' : alert.alert_level === 'HIGH' ? '#f97316' : '#eab308',
                color: 'white'
              }}>
                {alert.alert_level}
              </span>
              <span className="alert-time">
                {new Date(alert.created_at).toLocaleTimeString()}
              </span>
            </div>
            <h3>Risk Score: {alert.risk_score.toFixed(1)}%</h3>
            <p>Reason: {alert.trigger_reason}</p>
            {alert.predicted_peak && <p>Predicted Peak: {alert.predicted_peak.toFixed(2)} m</p>}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {!alert.acknowledged && (
              <button onClick={() => handleAcknowledge(alert.id)} style={{
                padding: '6px 12px',
                background: '#2563eb',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}>
                Acknowledge
              </button>
            )}
            <button onClick={() => handleDismiss(alert.id)} style={{
              padding: '6px 12px',
              background: '#6b7280',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer'
            }}>
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
