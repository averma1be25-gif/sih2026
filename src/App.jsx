import { useState } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
} from "react-leaflet";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import "leaflet/dist/leaflet.css";
import "./index.css";


// =========================
// DUMMY DATA
// Later backend will replace this
// =========================

const locations = [
  {
    name: "Dehradun",
    lat: 30.3165,
    lon: 78.0322,
    risk: "HIGH",
    probability: 87,
    rainfall: 82,
    river: 4.8,
    soil: 82,
  },
  {
    name: "Rishikesh",
    lat: 30.0869,
    lon: 78.2676,
    risk: "MEDIUM",
    probability: 58,
    rainfall: 51,
    river: 3.2,
    soil: 67,
  },
  {
    name: "Mussoorie",
    lat: 30.4598,
    lon: 78.0644,
    risk: "CRITICAL",
    probability: 91,
    rainfall: 96,
    river: 5.4,
    soil: 91,
  },
  {
    name: "Haridwar",
    lat: 29.9457,
    lon: 78.1642,
    risk: "LOW",
    probability: 28,
    rainfall: 22,
    river: 2.1,
    soil: 41,
  },
];

const predictionData = [
  { time: "2 PM", probability: 24 },
  { time: "3 PM", probability: 32 },
  { time: "4 PM", probability: 45 },
  { time: "5 PM", probability: 61 },
  { time: "6 PM", probability: 74 },
  { time: "7 PM", probability: 87 },
];


// =========================
// RISK COLORS
// =========================

function getRiskColor(risk) {
  if (risk === "CRITICAL") return "#dc2626";
  if (risk === "HIGH") return "#f97316";
  if (risk === "MEDIUM") return "#eab308";
  return "#22c55e";
}


// =========================
// DATA CARD
// =========================

function DataCard({ icon, title, value, unit, status }) {
  return (
    <div className="data-card">

      <div className="data-card-top">
        <div className="data-icon">
          {icon}
        </div>

        <span className="live-dot">
          LIVE
        </span>
      </div>

      <p className="data-title">{title}</p>

      <div className="data-value">
        {value}
        <span>{unit}</span>
      </div>

      <p className="data-status">
        {status}
      </p>

    </div>
  );
}


// =========================
// SIDEBAR
// =========================

function Sidebar({ activePage, setActivePage }) {

  const menu = [
    ["dashboard", "⌂", "Dashboard"],
    ["map", "◉", "Risk Map"],
    ["forecast", "◷", "Forecast"],
    ["alerts", "⚠", "Alerts"],
    ["history", "↗", "History"],
  ];

  return (
    <aside className="sidebar">

      <div className="logo-area">

        <div className="logo-mark">
          FF
        </div>

        <div>
          <h2>FloodGuard</h2>
          <span>EARLY WARNING SYSTEM</span>
        </div>

      </div>


      <div className="sidebar-section">
        MONITORING
      </div>


      <nav>

        {menu.map(([id, icon, label]) => (

          <button
            key={id}
            className={`nav-item ${
              activePage === id ? "active" : ""
            }`}
            onClick={() => setActivePage(id)}
          >

            <span className="nav-icon">
              {icon}
            </span>

            {label}

          </button>

        ))}

      </nav>


      <div className="sidebar-bottom">

        <div className="system-status">

          <span className="status-dot"></span>

          <div>
            <strong>System Online</strong>
            <small>All services operational</small>
          </div>

        </div>

        <p className="version">
          FloodGuard v1.0
        </p>

      </div>

    </aside>
  );
}


// =========================
// HEADER
// =========================

function Header({ setActivePage }) {

  return (
    <header className="header">

      <div>

        <p className="breadcrumb">
          MONITORING / LIVE
        </p>

        <h1>
          Flash Flood Intelligence
        </h1>

      </div>


      <div className="header-actions">

        <div className="connection">
          <span></span>
          Data streams connected
        </div>

        <button
          className="notification"
          onClick={() => setActivePage("alerts")}
        >
          🔔
          <b>3</b>
        </button>

        <div className="profile">
          <div className="avatar">
            A
          </div>

          <div>
            <strong>Control Center</strong>
            <small>Administrator</small>
          </div>
        </div>

      </div>

    </header>
  );
}


// =========================
// RISK OVERVIEW
// =========================

function RiskOverview({ selectedLocation }) {

  return (
    <section className="risk-overview">

      <div>

        <div className="section-label">
          CURRENT THREAT LEVEL
        </div>

        <div className="risk-heading">

          <span
            className="risk-indicator"
            style={{
              background: getRiskColor(
                selectedLocation.risk
              ),
            }}
          ></span>

          <h2>
            {selectedLocation.risk}
          </h2>

        </div>

        <p>
          {selectedLocation.name} is currently
          experiencing elevated flood conditions.
        </p>

      </div>


      <div className="probability">

        <span>FLOOD PROBABILITY</span>

        <strong>
          {selectedLocation.probability}%
        </strong>

      </div>

    </section>
  );
}


// =========================
// MAP
// =========================

function RiskMap({ onLocationSelect }) {

  return (

    <div className="map-card">

      <div className="card-header">

        <div>
          <span className="section-label">
            GEOSPATIAL MONITORING
          </span>

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
        >

          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />


          {locations.map((location) => (

            <CircleMarker
              key={location.name}
              center={[
                location.lat,
                location.lon,
              ]}
              radius={
                location.risk === "CRITICAL"
                  ? 18
                  : 14
              }
              pathOptions={{
                color: getRiskColor(
                  location.risk
                ),
                fillColor: getRiskColor(
                  location.risk
                ),
                fillOpacity: 0.65,
                weight: 3,
              }}
              eventHandlers={{
                click: () =>
                  onLocationSelect(location),
              }}
            >

              <Popup>

                <div className="popup">

                  <strong>
                    {location.name}
                  </strong>

                  <p>
                    Risk:
                    <b>
                      {" "}
                      {location.risk}
                    </b>
                  </p>

                  <p>
                    Probability:
                    {" "}
                    {location.probability}%
                  </p>

                  <p>
                    Rainfall:
                    {" "}
                    {location.rainfall} mm
                  </p>

                </div>

              </Popup>

            </CircleMarker>

          ))}

        </MapContainer>


        <div className="map-legend">

          <strong>RISK LEVEL</strong>

          <div>
            <i className="legend-low"></i>
            Low
          </div>

          <div>
            <i className="legend-medium"></i>
            Moderate
          </div>

          <div>
            <i className="legend-high"></i>
            High
          </div>

          <div>
            <i className="legend-critical"></i>
            Critical
          </div>

        </div>

      </div>

    </div>
  );
}


// =========================
// FORECAST CHART
// =========================

function ForecastChart() {

  return (

    <div className="chart-card">

      <div className="card-header">

        <div>

          <span className="section-label">
            AI PREDICTION
          </span>

          <h2>6-Hour Flood Forecast</h2>

        </div>

        <span className="forecast-badge">
          NEXT 6 HOURS
        </span>

      </div>


      <div className="chart-container">

        <ResponsiveContainer
          width="100%"
          height="100%"
        >

          <LineChart
            data={predictionData}
            margin={{
              top: 15,
              right: 20,
              left: 0,
              bottom: 5,
            }}
          >

            <CartesianGrid
              strokeDasharray="4 4"
            />

            <XAxis
              dataKey="time"
            />

            <YAxis
              domain={[0, 100]}
              tickFormatter={(value) =>
                `${value}%`
              }
            />

            <Tooltip
              formatter={(value) => [
                `${value}%`,
                "Flood Probability",
              ]}
            />

            <Line
              type="monotone"
              dataKey="probability"
              strokeWidth={3}
              dot={{
                r: 5,
              }}
              activeDot={{
                r: 7,
              }}
            />

          </LineChart>

        </ResponsiveContainer>

      </div>

    </div>
  );
}


// =========================
// ALERT BOX
// =========================

function AlertBox() {

  return (

    <div className="alert-card">

      <div className="alert-icon">
        ⚠
      </div>

      <div className="alert-content">

        <div className="alert-top">

          <span className="alert-tag">
            HIGH PRIORITY
          </span>

          <span className="alert-time">
            12 min ago
          </span>

        </div>

        <h3>
          Flash flood risk increasing
        </h3>

        <p>
          Heavy rainfall and rising water levels
          detected around the Dehradun region.
          Immediate monitoring recommended.
        </p>

      </div>

      <button className="alert-arrow">
        →
      </button>

    </div>
  );
}


// =========================
// DATA SOURCES
// =========================

function DataSources() {

  const sources = [
    ["🌧️", "Weather", "Connected"],
    ["🌊", "Hydrology", "Connected"],
    ["🌱", "Soil Moisture", "Connected"],
    ["⛰️", "Terrain / DEM", "Connected"],
    ["🛰️", "Satellite", "Connected"],
  ];

  return (

    <div className="sources-card">

      <div className="card-header">

        <div>
          <span className="section-label">
            MULTI-SOURCE DATA
          </span>

          <h2>Data Streams</h2>
        </div>

      </div>


      <div className="sources-list">

        {sources.map(
          ([icon, name, status]) => (

            <div
              className="source-item"
              key={name}
            >

              <div className="source-icon">
                {icon}
              </div>

              <div className="source-info">

                <strong>{name}</strong>

                <span>
                  <i></i>
                  {status}
                </span>

              </div>

            </div>

          )
        )}

      </div>

    </div>
  );
}


// =========================
// ALERTS PAGE
// =========================

function AlertsPage() {

  return (

    <div className="page-content">

      <div className="page-title">

        <span className="section-label">
          EARLY WARNING
        </span>

        <h2>Active Alerts</h2>

        <p>
          Real-time flood warnings generated
          by the prediction system.
        </p>

      </div>


      <AlertBox />

      <div className="alert-card medium-alert">

        <div className="alert-icon">
          !
        </div>

        <div className="alert-content">

          <div className="alert-top">

            <span className="alert-tag">
              MODERATE
            </span>

            <span className="alert-time">
              28 min ago
            </span>

          </div>

          <h3>
            Rising river levels detected
          </h3>

          <p>
            Water levels in the Rishikesh region
            are showing an upward trend.
          </p>

        </div>

      </div>

    </div>
  );
}


// =========================
// HISTORY PAGE
// =========================

function HistoryPage() {

  return (

    <div className="page-content">

      <div className="page-title">

        <span className="section-label">
          HISTORICAL ANALYSIS
        </span>

        <h2>Flood History</h2>

        <p>
          Historical flood events and environmental
          conditions.
        </p>

      </div>


      <div className="history-grid">

        <div className="history-stat">
          <span>Flood Events</span>
          <strong>24</strong>
          <small>Last 12 months</small>
        </div>

        <div className="history-stat">
          <span>Highest Rainfall</span>
          <strong>184 mm</strong>
          <small>August 2026</small>
        </div>

        <div className="history-stat">
          <span>Highest Risk</span>
          <strong>94%</strong>
          <small>Mussoorie</small>
        </div>

      </div>

    </div>
  );
}


// =========================
// MAIN DASHBOARD
// =========================

function Dashboard() {

  const [selectedLocation, setSelectedLocation] =
    useState(locations[0]);

  return (

    <main className="main-content">

      <RiskOverview
        selectedLocation={selectedLocation}
      />


      <div className="data-grid">

        <DataCard
          icon="🌧️"
          title="Rainfall"
          value={selectedLocation.rainfall}
          unit="mm"
          status="Heavy rainfall detected"
        />

        <DataCard
          icon="🌊"
          title="River Level"
          value={selectedLocation.river}
          unit="m"
          status="Water level rising"
        />

        <DataCard
          icon="🌱"
          title="Soil Moisture"
          value={selectedLocation.soil}
          unit="%"
          status="High saturation"
        />

        <DataCard
          icon="⛰️"
          title="Elevation"
          value="1,200"
          unit="m"
          status="Hilly terrain"
        />

      </div>


      <div className="main-grid">

        <RiskMap
          onLocationSelect={setSelectedLocation}
        />

        <DataSources />

      </div>


      <div className="bottom-grid">

        <ForecastChart />

        <div>

          <div className="small-heading">
            <span className="section-label">
              ALERT CENTER
            </span>

            <h2>Latest Warning</h2>
          </div>

          <AlertBox />

        </div>

      </div>

    </main>
  );
}


// =========================
// APP
// =========================

function App() {

  const [activePage, setActivePage] =
    useState("dashboard");

  return (

    <div className="app">

      <Sidebar
        activePage={activePage}
        setActivePage={setActivePage}
      />


      <div className="content-area">

        <Header
          setActivePage={setActivePage}
        />


        {activePage === "dashboard" && (
          <Dashboard />
        )}

        {activePage === "map" && (
          <main className="main-content">
            <RiskMap
              onLocationSelect={() => {}}
            />
          </main>
        )}

        {activePage === "forecast" && (
          <main className="main-content">
            <ForecastChart />
          </main>
        )}

        {activePage === "alerts" && (
          <AlertsPage />
        )}

        {activePage === "history" && (
          <HistoryPage />
        )}

      </div>

    </div>
  );
}

export default App;
