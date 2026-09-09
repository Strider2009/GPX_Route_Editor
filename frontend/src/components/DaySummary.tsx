import { useState } from "react";
import type { DayDetail } from "../api/types";
import { useDayWeather } from "../api/hooks";

interface Props {
  day: DayDetail;
  dayNumber: number;
}

const MILES = 1609.344;

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function DaySummary({ day, dayNumber }: Props) {
  const [when, setWhen] = useState(today());
  const [wantWeather, setWantWeather] = useState(false);
  const weather = useDayWeather(day.id, when, wantWeather);

  const km = day.stats.distance_m / 1000;
  const w = weather.data;

  return (
    <div className="panel">
      <h3 className="panel-title">Day {dayNumber} summary</h3>

      <div className="grid grid-cols-2 gap-1 text-xs">
        <div className="bg-page rounded px-2 py-1">
          <div className="text-ink-muted">Distance</div>
          <div className="font-medium">
            {km.toFixed(1)} km <span className="text-ink-faint">/ {(km / 1.609344).toFixed(1)} mi</span>
          </div>
        </div>
        <div className="bg-page rounded px-2 py-1">
          <div className="text-ink-muted">Climb</div>
          <div className="font-medium">
            +{Math.round(day.stats.ascent_m)} m
            <span className="text-ink-faint"> / -{Math.round(day.stats.descent_m)} m</span>
          </div>
        </div>
        <div className="bg-page rounded px-2 py-1">
          <div className="text-ink-muted">Points</div>
          <div className="font-medium">{day.stats.point_count.toLocaleString()}</div>
        </div>
        <div className="bg-page rounded px-2 py-1">
          <div className="text-ink-muted">Connectors</div>
          <div className="font-medium">{day.connectors.length}</div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="date"
          className="border border-line rounded-md px-1 py-0.5 text-xs"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
        />
        <button className="btn text-xs" onClick={() => setWantWeather(true)} disabled={weather.isFetching}>
          {weather.isFetching ? "Loading..." : "Weather"}
        </button>
      </div>

      {weather.isError && (
        <p className="text-xs text-amber-700">{(weather.error as Error).message}</p>
      )}

      {wantWeather && w && (
        <div className="border border-line rounded-md p-2 flex flex-col gap-1 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-medium">{w.summary}</span>
            <span>
              {Math.round(w.temp_min_c)}-{Math.round(w.temp_max_c)}&deg;C
            </span>
          </div>
          <div className="text-ink-muted">
            Rain {w.precip_mm.toFixed(1)} mm ({w.precip_chance_pct ?? "?"}% chance) · daylight{" "}
            {(w.sunrise ?? "").slice(11, 16)}-{(w.sunset ?? "").slice(11, 16)}
          </div>
          <div className="text-ink-muted">
            Wind {Math.round(w.wind_kmh)} km/h from {w.wind_from}
            {w.gust_kmh ? ` (gusts ${Math.round(w.gust_kmh)})` : ""}
          </div>
          {w.overall_wind && (
            <div
              className={
                w.overall_wind.label === "headwind"
                  ? "text-red-700"
                  : w.overall_wind.label === "tailwind"
                    ? "text-green-700"
                    : "text-ink-muted"
              }
            >
              Route heads {w.route_heading} &rarr; mostly {w.overall_wind.label} (
              {w.overall_wind.along_kmh > 0 ? "+" : ""}
              {w.overall_wind.along_kmh} km/h along)
            </div>
          )}
          {w.legs.length > 1 && (
            <div className="flex flex-col gap-0.5 border-t border-line pt-1">
              <div className="text-ink-muted">By leg:</div>
              {w.legs.map((leg, i) => (
                <div key={i} className="flex items-center justify-between">
                  <span className="text-ink-muted">heading {leg.heading}</span>
                  <span
                    className={
                      leg.wind?.label === "headwind"
                        ? "text-red-700"
                        : leg.wind?.label === "tailwind"
                          ? "text-green-700"
                          : "text-ink-muted"
                    }
                  >
                    {leg.wind?.label} {leg.wind ? `${leg.wind.along_kmh > 0 ? "+" : ""}${leg.wind.along_kmh}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
