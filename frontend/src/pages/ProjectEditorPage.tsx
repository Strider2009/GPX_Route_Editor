import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useDay, useProject, useProjectGeometry } from "../api/hooks";
import { useUIStore } from "../state/uiStore";
import Toolbar from "../components/Toolbar";
import DayPanel from "../components/DayPanel";
import ConnectorPanel from "../components/ConnectorPanel";
import MapView from "../components/MapView";
import PointList from "../components/PointList";
import PointContextMenu, { type ContextTarget } from "../components/PointContextMenu";
import RoadworksPanel from "../components/RoadworksPanel";
import PotholePanel from "../components/PotholePanel";
import ElevationProfile from "../components/ElevationProfile";
import DaySummary from "../components/DaySummary";
import BoundaryPanel from "../components/BoundaryPanel";
import type { Point, PotholeMatch, RoadworkMatch } from "../api/types";

export default function ProjectEditorPage() {
  const { projectId } = useParams();
  const pid = Number(projectId);
  const { data: project, isLoading, error } = useProject(pid);

  const selectedDayId = useUIStore((s) => s.selectedDayId);
  const setSelectedDay = useUIStore((s) => s.setSelectedDay);

  useEffect(() => {
    if (
      project &&
      project.days.length > 0 &&
      (selectedDayId == null || !project.days.some((d) => d.id === selectedDayId))
    ) {
      setSelectedDay([...project.days].sort((a, b) => a.order_index - b.order_index)[0].id);
    }
  }, [project, selectedDayId, setSelectedDay]);

  const { data: day } = useDay(selectedDayId ?? undefined);
  const { data: geometry } = useProjectGeometry(pid);
  // Everything except the day being edited is drawn behind it as shadow.
  const otherDays = (geometry?.days ?? []).filter((d) => d.day_id !== selectedDayId);

  const orderedDays = [...(geometry?.days ?? [])].sort((a, b) => a.order_index - b.order_index);
  const myPos = orderedDays.findIndex((d) => d.day_id === selectedDayId);
  // A day's start or end is a shared boundary only where there's a day on that side.
  // On a loop the ends meet, so even the first and last day have a neighbour.
  const looped = geometry?.is_loop ?? false;
  const hasPrevious = myPos > 0 || (looped && myPos === 0 && orderedDays.length > 1);
  const hasNext =
    (myPos >= 0 && myPos < orderedDays.length - 1) ||
    (looped && myPos === orderedDays.length - 1 && orderedDays.length > 1);

  /** Only the days either side share a boundary with the one being edited. */
  const relationTo = (otherDayId: number | null): "previous" | "next" | "distant" | undefined => {
    if (otherDayId == null || !geometry) return undefined;
    const ordered = [...geometry.days].sort((a, b) => a.order_index - b.order_index);
    const here = ordered.findIndex((d) => d.day_id === selectedDayId);
    const there = ordered.findIndex((d) => d.day_id === otherDayId);
    if (here < 0 || there < 0) return undefined;
    if (there === here - 1) return "previous";
    if (there === here + 1) return "next";
    // Wrapping round the end of a loop counts as adjacent.
    if (looped && here === 0 && there === ordered.length - 1) return "previous";
    if (looped && here === ordered.length - 1 && there === 0) return "next";
    return "distant";
  };

  const [draftPoints, setDraftPoints] = useState<Point[]>([]);
  const [drawingConnectorId, setDrawingConnectorId] = useState<number | "new" | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextTarget | null>(null);
  const [roadworks, setRoadworks] = useState<RoadworkMatch[]>([]);
  const [potholes, setPotholes] = useState<PotholeMatch[]>([]);

  useEffect(() => {
    setContextMenu(null);
  }, [selectedDayId]);

  if (isLoading) return <div className="p-6 text-ink-muted">Loading...</div>;
  if (error || !project) return <div className="p-6 text-red-600">Failed to load project.</div>;

  const dayNumber = day
    ? [...project.days].sort((a, b) => a.order_index - b.order_index).findIndex((d) => d.id === day.id) + 1
    : 0;

  return (
    <div className="h-screen flex flex-col">
      <Toolbar project={project} selectedDayId={selectedDayId} />
      <div className="flex-1 flex overflow-hidden bg-page">
        <aside className="w-80 shrink-0 overflow-y-auto bg-page border-r border-line flex flex-col gap-3 p-3">
          {day && <DaySummary day={day} dayNumber={dayNumber} />}
          <DayPanel projectId={pid} days={project.days} />
          <BoundaryPanel projectId={pid} />
          {day && (
            <ConnectorPanel
              projectId={pid}
              day={day}
              draftPoints={draftPoints}
              setDraftPoints={setDraftPoints}
              drawingConnectorId={drawingConnectorId}
              setDrawingConnectorId={setDrawingConnectorId}
            />
          )}
          {day && <RoadworksPanel dayId={day.id} onMatchesChange={setRoadworks} />}
          {day && <PotholePanel dayId={day.id} onMatchesChange={setPotholes} />}
        </aside>
        <main className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 relative">
          <MapView
            day={day}
            drawMode={drawingConnectorId !== null}
            draftPoints={draftPoints}
            roadworks={roadworks}
            potholes={potholes}
            otherDays={otherDays}
            onMapClick={(lat, lon) => setDraftPoints([...draftPoints, { lat, lon, ele: null, time: null }])}
            onPointContextMenu={(pick, x, y) =>
              setContextMenu({
                otherDayId: pick.otherDayId,
                otherDayName: otherDays.find((d) => d.day_id === pick.otherDayId)?.name,
                otherDayRelation: relationTo(pick.otherDayId),
                index: pick.index,
                x,
                y,
                hasPrevious,
                hasNext,
              })
            }
          />
          </div>
          {day && day.points.length > 1 && (
            <div className="bg-surface border-t border-line">
              <ElevationProfile points={day.points} roadworks={roadworks} potholes={potholes} />
            </div>
          )}
        </main>
        <aside className="w-96 shrink-0 overflow-hidden bg-surface border-l border-line">
          {day ? (
            <PointList
              points={day.points}
              dayName={`Day ${dayNumber}: ${day.name}`}
              isCircular={day.is_circular}
              onContextMenu={(pointIndex, x, y) =>
                setContextMenu({
                  otherDayId: null,
                  index: pointIndex,
                  x,
                  y,
                  hasPrevious,
                  hasNext,
                })
              }
            />
          ) : (
            <div className="p-4 text-sm text-ink-muted">Select a day.</div>
          )}
        </aside>
      </div>
      {day && contextMenu && (
        <PointContextMenu
          projectId={pid}
          day={day}
          target={contextMenu}
          onClose={() => setContextMenu(null)}
        />
      )}
    </div>
  );
}
