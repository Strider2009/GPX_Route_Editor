import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import type { DayDetail, DayGeometry, Point, PotholeMatch, RoadworkMatch } from "../api/types";
import { useUIStore } from "../state/uiStore";
import { haversine } from "../lib/geo";
import { RELEVANCE_COLORS } from "./RoadworksPanel";
import { POTHOLE_COLOR } from "./PotholePanel";

const MAX_VERTEX_MARKERS = 400;

const CONNECTOR_COLORS: Record<string, string> = {
  start_access: "#f59e0b",
  end_access: "#a855f7",
  spur: "#6b7280",
};

function toLatLng(p: Point): [number, number] {
  return [p.lat, p.lon];
}

export type Pick = {
  /** Set when the click landed on another day rather than the one being edited. */
  otherDayId: number | null;
  index: number;
  distance: number;
  lat: number;
  lon: number;
};

/** Nearest point across the day being edited and the other days shown behind it.
 *  Ties go to the current day so ordinary editing isn't hijacked by the shadow. */
function pickNearest(
  points: Point[],
  others: DayGeometry[],
  lat: number,
  lon: number
): Pick | null {
  let best: Pick | null = null;

  for (let i = 0; i < points.length; i++) {
    const d = haversine(points[i], { lat, lon });
    if (!best || d < best.distance)
      best = { otherDayId: null, index: i, distance: d, lat: points[i].lat, lon: points[i].lon };
  }

  for (const other of others) {
    for (const [plat, plon, realIndex] of other.points) {
      const d = haversine({ lat: plat, lon: plon }, { lat, lon });
      // Needs to be clearly closer, or the current day keeps it.
      if (!best || d < best.distance - 1) {
        best = { otherDayId: other.day_id, index: realIndex, distance: d, lat: plat, lon: plon };
      }
    }
  }
  return best;
}

function nearestPointIndex(points: Point[], lat: number, lon: number): number | null {
  if (points.length === 0) return null;
  let bestIndex = 0;
  let bestDist = Infinity;
  for (let i = 0; i < points.length; i++) {
    const d = haversine(points[i], { lat, lon });
    if (d < bestDist) {
      bestDist = d;
      bestIndex = i;
    }
  }
  return bestIndex;
}

function FitToPoints({ points, dayId }: { points: Point[]; dayId: number | undefined }) {
  const map = useMap();
  // Switching day renders once with no points while the day is still loading, so
  // fit when the points actually arrive rather than when the id changes - but only
  // once per day, or editing the route would keep yanking the view back.
  const fittedFor = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (dayId == null || points.length === 0) return;
    if (fittedFor.current === dayId) return;
    fittedFor.current = dayId;
    // The container may have just changed size (the elevation profile mounting
    // under it); fitting against stale dimensions gives the wrong zoom.
    map.invalidateSize();
    map.fitBounds(points.map(toLatLng) as [number, number][], { padding: [24, 24] });
  }, [dayId, points.length, map]);
  return null;
}

/** Re-frames the whole route on demand: auto-fit stays quiet after edits. */
function FitButton({ points }: { points: Point[] }) {
  const map = useMap();
  if (points.length < 2) return null;
  return (
    <button
      className="absolute top-2 right-2 z-[1000] bg-surface border border-line rounded-md shadow-card px-2.5 py-1.5 text-xs font-medium hover:bg-page"
      title="Zoom to fit the whole route"
      onClick={(e) => {
        e.stopPropagation();
        map.invalidateSize();
        map.fitBounds(points.map(toLatLng) as [number, number][], { padding: [24, 24] });
      }}
    >
      Fit route
    </button>
  );
}

/** Leaflet caches the container size, so tell it when the layout changes. */
function ResizeWatcher() {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);
  return null;
}

function PanToSelected({ point, panRequestId }: { point: Point | null; panRequestId: number }) {
  const map = useMap();
  // Keyed off the pan request rather than the coordinates: a route edit that renumbers points
  // must not move the frame, even though the selected index changes underneath us.
  useEffect(() => {
    if (point) map.panTo([point.lat, point.lon], { animate: true, duration: 0.4 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panRequestId]);
  return null;
}

function MapInteractions({
  onClick,
  onContextMenu,
}: {
  onClick: (lat: number, lon: number) => void;
  onContextMenu: (lat: number, lon: number, screenX: number, screenY: number) => void;
}) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
    contextmenu(e) {
      e.originalEvent.preventDefault();
      onContextMenu(e.latlng.lat, e.latlng.lng, e.originalEvent.clientX, e.originalEvent.clientY);
    },
  });
  return null;
}

interface Props {
  day: DayDetail | undefined;
  drawMode: boolean;
  draftPoints: Point[];
  roadworks: RoadworkMatch[];
  potholes: PotholeMatch[];
  otherDays: DayGeometry[];
  onMapClick: (lat: number, lon: number) => void;
  onPointContextMenu: (pick: Pick, screenX: number, screenY: number) => void;
}

export default function MapView({
  day,
  drawMode,
  draftPoints,
  roadworks,
  potholes,
  otherDays,
  onMapClick,
  onPointContextMenu,
}: Props) {
  const selectedPointIndex = useUIStore((s) => s.selectedPointIndex);
  const setSelectedPoint = useUIStore((s) => s.setSelectedPoint);
  const setShadowPoint = useUIStore((s) => s.setShadowPoint);
  const selectPointQuietly = useUIStore((s) => s.selectPointQuietly);
  const shadowPoint = useUIStore((s) => s.shadowPoint);
  const panRequestId = useUIStore((s) => s.panRequestId);
  const hoveredPointIndex = useUIStore((s) => s.hoveredPointIndex);

  const points = day?.points ?? [];
  const selectedPoint = selectedPointIndex != null ? points[selectedPointIndex] ?? null : null;
  const hoveredPoint = hoveredPointIndex != null ? points[hoveredPointIndex] ?? null : null;
  const showVertices = points.length > 0 && points.length <= MAX_VERTEX_MARKERS;

  return (
    <MapContainer center={[51.5, 0.5]} zoom={9} className="h-full w-full">
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {/* The rest of the trip, drawn first so the day being edited sits on top.
          A pale casing underneath lifts it off the busier parts of the map. */}
      {otherDays.map((other) => {
        const line = other.points.map((p) => [p[0], p[1]] as [number, number]);
        return (
          <Polyline
            key={`shadow-casing-${other.day_id}`}
            positions={line}
            pathOptions={{ color: "#ffffff", weight: 9, opacity: 0.7 }}
            interactive={false}
          />
        );
      })}
      {otherDays.map((other) => (
        <Polyline
          key={`shadow-${other.day_id}`}
          positions={other.points.map((p) => [p[0], p[1]] as [number, number])}
          pathOptions={{ color: "#475569", weight: 4, opacity: 0.85, dashArray: "9 6" }}
          interactive={false}
        />
      ))}

      {points.length > 1 && (
        <Polyline positions={points.map(toLatLng)} pathOptions={{ color: "#2563eb", weight: 4 }} />
      )}
      <ResizeWatcher />
      <FitButton points={points} />
      <FitToPoints points={points} dayId={day?.id} />
      <PanToSelected point={selectedPoint} panRequestId={panRequestId} />

      {showVertices &&
        points.map((p, i) =>
          i === selectedPointIndex ? null : (
            <CircleMarker
              key={i}
              center={toLatLng(p)}
              radius={3}
              pathOptions={{ color: "#1e40af", fillOpacity: 0.8 }}
              interactive={false}
            />
          )
        )}

      {/* Previewed from the elevation profile: shown, but the view never moves for it. */}
      {hoveredPoint && hoveredPointIndex !== selectedPointIndex && (
        <CircleMarker
          center={toLatLng(hoveredPoint)}
          radius={7}
          pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#6b7280", fillOpacity: 0.85 }}
          interactive={false}
        />
      )}

      {shadowPoint && (
        <CircleMarker
          center={[shadowPoint.lat, shadowPoint.lon]}
          radius={8}
          pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#475569", fillOpacity: 1 }}
          interactive={false}
        />
      )}

      {selectedPoint && (
        <CircleMarker
          center={toLatLng(selectedPoint)}
          radius={9}
          pathOptions={{ color: "#ffffff", weight: 2, fillColor: "#facc15", fillOpacity: 1 }}
        />
      )}

      {points.length > 0 && (
        <CircleMarker center={toLatLng(points[0])} radius={8} pathOptions={{ color: "#16a34a", fillOpacity: 1 }} />
      )}
      {points.length > 1 && !day?.is_circular && (
        <CircleMarker
          center={toLatLng(points[points.length - 1])}
          radius={8}
          pathOptions={{ color: "#dc2626", fillOpacity: 1 }}
        />
      )}

      {day?.connectors.map((c) =>
        c.points.length > 0 ? (
          <Polyline
            key={c.id}
            positions={c.points.map(toLatLng)}
            pathOptions={{ color: CONNECTOR_COLORS[c.type] ?? "#6b7280", dashArray: "6 6", weight: 3 }}
          />
        ) : null
      )}

      {roadworks.map((w) => (
        <CircleMarker
          key={`rw-${w.external_id}`}
          center={[w.lat, w.lon]}
          radius={7}
          pathOptions={{
            color: "#ffffff",
            weight: 2,
            fillColor: RELEVANCE_COLORS[w.cycling_relevance],
            fillOpacity: 0.9,
          }}
          eventHandlers={{ click: () => setSelectedPoint(w.nearest_point_index) }}
        >
          <Tooltip>
            <div className="text-xs">
              <div className="font-semibold">{w.road_name || "(unnamed road)"}</div>
              <div>{w.traffic_management}</div>
              <div>
                {(w.start_date || "").slice(0, 10)} &rarr; {(w.end_date || "").slice(0, 10)}
              </div>
              <div>{Math.round(w.distance_m)} m from route</div>
            </div>
          </Tooltip>
        </CircleMarker>
      ))}

      {potholes.map((p) => (
        <CircleMarker
          key={`ph-${p.report_id}`}
          center={[p.lat, p.lon]}
          radius={5}
          pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: POTHOLE_COLOR, fillOpacity: 0.9 }}
          eventHandlers={{ click: () => setSelectedPoint(p.nearest_point_index) }}
        >
          <Tooltip>
            <div className="text-xs">
              <div className="font-semibold">{p.title || "Pothole"}</div>
              <div>reported ~{p.reported_approx ?? "unknown"}</div>
              <div>{Math.round(p.distance_m)} m from route</div>
            </div>
          </Tooltip>
        </CircleMarker>
      ))}

      {draftPoints.length > 0 && (
        <Polyline positions={draftPoints.map(toLatLng)} pathOptions={{ color: "#ef4444", dashArray: "2 6", weight: 3 }} />
      )}
      {draftPoints.map((p, i) => (
        <CircleMarker key={`draft-${i}`} center={toLatLng(p)} radius={4} pathOptions={{ color: "#ef4444", fillOpacity: 1 }} />
      ))}

      <MapInteractions
        onClick={(lat, lon) => {
          if (drawMode) {
            onMapClick(lat, lon);
            return;
          }
          const pick = pickNearest(points, otherDays, lat, lon);
          if (!pick) return;
          if (pick.otherDayId == null) {
            setSelectedPoint(pick.index);
          } else {
            // Picked on a shadow day: mark it without disturbing the current
            // day's own selection machinery.
            setShadowPoint({
              dayId: pick.otherDayId,
              index: pick.index,
              lat: pick.lat,
              lon: pick.lon,
            });
          }
        }}
        onContextMenu={(lat, lon, screenX, screenY) => {
          if (drawMode) return;
          const pick = pickNearest(points, otherDays, lat, lon);
          if (!pick) return;
          // Highlight without panning: the menu is pinned to the cursor, so
          // sliding the map underneath it would leave it pointing at nothing.
          if (pick.otherDayId == null) {
            selectPointQuietly(pick.index);
          } else {
            setShadowPoint({
              dayId: pick.otherDayId,
              index: pick.index,
              lat: pick.lat,
              lon: pick.lon,
            });
          }
          onPointContextMenu(pick, screenX, screenY);
        }}
      />
    </MapContainer>
  );
}
