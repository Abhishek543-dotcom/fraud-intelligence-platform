import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet';
import { formatCurrency, severityColor } from '../utils/formatters';
import type { FraudAlert } from '../types';

interface GeoHeatmapProps {
  alerts: FraudAlert[];
}

function MapUpdater({ alerts }: { alerts: FraudAlert[] }) {
  const map = useMap();
  const initialized = useRef(false);

  useEffect(() => {
    if (alerts.length > 0 && !initialized.current) {
      const bounds = L.latLngBounds(
        alerts.map((a) => [a.location_lat, a.location_lon] as [number, number])
      );
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 6 });
      initialized.current = true;
    }
  }, [alerts, map]);

  return null;
}

function severityColorHex(severity: string): string {
  switch (severity) {
    case 'critical': return '#f87171';
    case 'high': return '#fb923c';
    case 'medium': return '#facc15';
    case 'low': return '#4ade80';
    default: return '#9ca3af';
  }
}

function severityRadius(severity: string): number {
  switch (severity) {
    case 'critical': return 10;
    case 'high': return 8;
    case 'medium': return 6;
    case 'low': return 4;
    default: return 4;
  }
}

export default function GeoHeatmap({ alerts }: GeoHeatmapProps) {
  const validAlerts = alerts.filter(
    (a) => a.location_lat && a.location_lon && !isNaN(a.location_lat) && !isNaN(a.location_lon)
  );

  return (
    <div className="card h-[420px] flex flex-col">
      <span className="card-header">Fraud Geo Distribution</span>
      <div className="flex-1 rounded-lg overflow-hidden border border-gray-800">
        <MapContainer
          center={[39.8283, -98.5795]}
          zoom={4}
          className="h-full w-full"
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <MapUpdater alerts={validAlerts} />
          {validAlerts.map((alert) => (
            <CircleMarker
              key={alert.alert_id}
              center={[alert.location_lat, alert.location_lon]}
              radius={severityRadius(alert.severity)}
              pathOptions={{
                color: severityColorHex(alert.severity),
                fillColor: severityColorHex(alert.severity),
                fillOpacity: 0.6,
                weight: 1,
              }}
            >
              <Popup>
                <div className="text-xs space-y-1 min-w-[160px]">
                  <div className="font-bold text-sm">{alert.merchant_name}</div>
                  <div>Amount: {formatCurrency(alert.amount)}</div>
                  <div>Score: {(alert.fraud_score * 100).toFixed(0)}%</div>
                  <div className={severityColor(alert.severity)}>
                    Severity: {alert.severity}
                  </div>
                  <div className="text-gray-500 font-mono">{alert.transaction_id.slice(0, 16)}</div>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400" /> Critical</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-400" /> High</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-400" /> Medium</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-400" /> Low</span>
      </div>
    </div>
  );
}
