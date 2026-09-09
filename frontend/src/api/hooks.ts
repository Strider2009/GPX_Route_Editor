import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ConnectorType, DayDetail, Point } from "./types";
import { useUIStore } from "../state/uiStore";

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
}

export function useProject(projectId: number | undefined) {
  return useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId!),
    enabled: projectId != null && !Number.isNaN(projectId),
  });
}

export function useDay(dayId: number | undefined) {
  return useQuery({
    queryKey: ["day", dayId],
    queryFn: () => api.getDay(dayId!),
    enabled: dayId != null,
  });
}

export function useImportProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { files: File[]; name?: string }) => api.importProject(vars.files, vars.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: number) => api.deleteProject(projectId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useUpdateDay(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; data: { name?: string; order_index?: number } }) =>
      api.updateDay(vars.dayId, vars.data),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["day", vars.dayId] });
      invalidateRouteData(qc, projectId);
    },
  });
}

export function useDeleteDay(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dayId: number) => api.deleteDay(dayId),
    onSuccess: (_d, dayId) => {
      qc.removeQueries({ queryKey: ["day", dayId] });
      invalidateRouteData(qc, projectId);
    },
  });
}

export function useSetCircular(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; value: boolean }) => api.setCircular(vars.dayId, vars.value),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["day", vars.dayId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useSetLocked(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; value: boolean }) => api.setLocked(vars.dayId, vars.value),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["day", vars.dayId] });
      // A lock decides whether the neighbouring boundaries can move at all.
      invalidateRouteData(qc, projectId);
    },
  });
}

// These reorder a day's points, so the selected index has to be remapped to wherever
// that same physical point ended up - otherwise the map jumps to an unrelated point.
export function useRotate(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; index: number }) => api.rotate(vars.dayId, vars.index),
    onSuccess: (data: DayDetail, vars) => {
      qc.setQueryData(["day", vars.dayId], data);
      invalidateRouteData(qc, projectId);
      useUIStore.getState().selectPointQuietly(0);
    },
  });
}

export function useTrim(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; start_index: number; end_index: number }) =>
      api.trim(vars.dayId, vars.start_index, vars.end_index),
    onSuccess: (data: DayDetail, vars) => {
      qc.setQueryData(["day", vars.dayId], data);
      invalidateRouteData(qc, projectId);

      const { start_index, end_index } = vars;
      const selected = useUIStore.getState().selectedPointIndex;
      if (selected == null) return;
      // The caller always trims relative to the point the user had selected, passing it
      // as either bound; track whichever bound it is to its position in the kept slice.
      if (selected !== start_index && selected !== end_index) return;
      const lo = Math.min(start_index, end_index);
      const hi = Math.max(start_index, end_index);
      const newIndex = start_index > end_index ? hi - selected : selected - lo;
      useUIStore.getState().selectPointQuietly(newIndex);
    },
  });
}

export function useReverse(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dayId: number) => api.reverse(dayId),
    onSuccess: (data: DayDetail, dayId) => {
      const selected = useUIStore.getState().selectedPointIndex;
      qc.setQueryData(["day", dayId], data);
      invalidateRouteData(qc, projectId);
      if (selected != null) {
        useUIStore.getState().selectPointQuietly(data.points.length - 1 - selected);
      }
    },
  });
}

export function useSplit(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; indices: number[] }) => api.split(vars.dayId, vars.indices),
    onSuccess: (data: DayDetail[]) => {
      for (const d of data) {
        qc.setQueryData(["day", d.id], d);
      }
      invalidateRouteData(qc, projectId);
    },
  });
}

export function useMergeDays(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayIdA: number; dayIdB: number }) => api.merge(vars.dayIdA, vars.dayIdB),
    onSuccess: (data: DayDetail, vars) => {
      qc.setQueryData(["day", data.id], data);
      const otherId = vars.dayIdA === data.id ? vars.dayIdB : vars.dayIdA;
      qc.removeQueries({ queryKey: ["day", otherId] });
      invalidateRouteData(qc, projectId);
    },
  });
}

export function useAddConnector(projectId: number, dayId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { name: string; type: ConnectorType; points: Point[] }) => api.addConnector(dayId, vars),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["day", dayId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function useUpdateConnector(dayId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { connectorId: number; name?: string; points?: Point[] }) =>
      api.updateConnector(vars.connectorId, { name: vars.name, points: vars.points }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["day", dayId] }),
  });
}

export function useDeleteConnector(dayId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (connectorId: number) => api.deleteConnector(connectorId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["day", dayId] }),
  });
}

export function useDayRoadworks(
  dayId: number | undefined,
  opts: { targetDate?: string; bufferM?: number; minRelevance?: string; includeInactive?: boolean },
  enabled: boolean
) {
  return useQuery({
    queryKey: ["roadworks", dayId, opts.targetDate, opts.bufferM, opts.minRelevance, opts.includeInactive],
    queryFn: () => api.getDayRoadworks(dayId!, opts),
    enabled: enabled && dayId != null,
  });
}

export function useTilesForDay(dayId: number | undefined, z: number, enabled: boolean) {
  return useQuery({
    queryKey: ["roadworks-tiles", dayId, z],
    queryFn: () => api.tilesForDay(dayId!, z),
    enabled: enabled && dayId != null,
  });
}

export function useRoadworksStatus() {
  return useQuery({ queryKey: ["roadworks-status"], queryFn: api.roadworksStatus });
}

export function useClearRoadworks() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.clearRoadworks(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roadworks"] });
      qc.invalidateQueries({ queryKey: ["roadworks-status"] });
    },
  });
}

export function useFetchRoadworks() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; z: number; targetDate?: string }) =>
      api.fetchRoadworks(vars.dayId, vars.z, vars.targetDate),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["roadworks"] });
      qc.invalidateQueries({ queryKey: ["roadworks-status"] });
    },
  });
}


export function useStravaStatus() {
  return useQuery({ queryKey: ["strava-status"], queryFn: api.stravaStatus });
}

export function useStravaRoutes(enabled: boolean) {
  return useQuery({ queryKey: ["strava-routes"], queryFn: api.stravaRoutes, enabled });
}

export function useImportStravaRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { routeId: string; name?: string }) =>
      api.importStravaRoute(vars.routeId, vars.name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useDisconnectStrava() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.disconnectStrava(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strava-status"] }),
  });
}

export function usePotholeStatus() {
  return useQuery({ queryKey: ["pothole-status"], queryFn: api.potholeStatus });
}

export function useDayPotholes(
  dayId: number | undefined,
  opts: { bufferM: number; maxAgeYears: number },
  enabled: boolean
) {
  return useQuery({
    queryKey: ["potholes", dayId, opts.bufferM, opts.maxAgeYears],
    queryFn: () => api.getDayPotholes(dayId!, opts),
    enabled: enabled && dayId != null,
  });
}

export function useFetchPotholes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; z: number }) => api.fetchPotholes(vars.dayId, vars.z),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["potholes"] });
      qc.invalidateQueries({ queryKey: ["pothole-status"] });
    },
  });
}

export function useClearPotholes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.clearPotholes(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["potholes"] });
      qc.invalidateQueries({ queryKey: ["pothole-status"] });
    },
  });
}

export function useSplitEven(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; parts: number; climbWeight: number }) =>
      api.splitEven(vars.dayId, vars.parts, vars.climbWeight),
    onSuccess: (data: DayDetail[]) => {
      for (const d of data) qc.setQueryData(["day", d.id], d);
      invalidateRouteData(qc, projectId);
    },
  });
}

export function useDayWeather(dayId: number | undefined, date: string, enabled: boolean) {
  return useQuery({
    queryKey: ["weather", dayId, date],
    queryFn: () => api.dayWeather(dayId!, date),
    enabled: enabled && dayId != null,
    retry: false,
  });
}

export function useAddRoutesToProject(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.addRoutesToProject(projectId, files),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}

export function useBoundaries(projectId: number) {
  return useQuery({
    queryKey: ["boundaries", projectId],
    queryFn: () => api.boundaries(projectId),
  });
}

/** Everything derived from a project's routes.
 *
 * Any edit that changes a day's points, or which days exist, must go through
 * this: the map shadow, the boundary sliders and the roadworks/pothole matches
 * are all computed from that geometry and go stale silently otherwise.
 */
function invalidateRouteData(qc: ReturnType<typeof useQueryClient>, projectId: number) {
  qc.invalidateQueries({ queryKey: ["project", projectId] });
  qc.invalidateQueries({ queryKey: ["boundaries", projectId] });
  qc.invalidateQueries({ queryKey: ["geometry", projectId] });
  qc.invalidateQueries({ queryKey: ["history", projectId] });
  qc.invalidateQueries({ queryKey: ["day"] });
  qc.invalidateQueries({ queryKey: ["roadworks"] });
  qc.invalidateQueries({ queryKey: ["potholes"] });
}

export function useMoveBoundary(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { index: number; deltaM: number }) =>
      api.moveBoundary(projectId, vars.index, vars.deltaM),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}

export function useShiftBoundaries(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deltaM: number) => api.shiftBoundaries(projectId, deltaM),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}

export function useSetEndLocks(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; lock_start?: boolean; lock_end?: boolean }) =>
      api.setEndLocks(vars.dayId, vars),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["day", vars.dayId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["boundaries", projectId] });
    },
  });
}

export function useReorderDays(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dayIds: number[]) => api.reorderDays(projectId, dayIds),
    onSuccess: (data) => {
      qc.setQueryData(["project", projectId], data);
      // Which days sit next to which has changed, so the joins have too.
      invalidateRouteData(qc, projectId);
    },
  });
}

/** Setting the range from the shadow replaces the day's points wholesale. */
export function useSetDayRange(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { dayId: number; startIndex: number; endIndex: number }) =>
      api.setDayRange(vars.dayId, vars.startIndex, vars.endIndex),
    onSuccess: (data: DayDetail) => {
      qc.setQueryData(["day", data.id], data);
      invalidateRouteData(qc, projectId);
      useUIStore.getState().setSelectedPoint(null);
    },
  });
}

export function useRestoreFullRoute(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dayId: number) => api.restoreFullRoute(dayId),
    onSuccess: (data: DayDetail) => {
      qc.setQueryData(["day", data.id], data);
      invalidateRouteData(qc, projectId);
    },
  });
}


export function useProjectGeometry(projectId: number) {
  return useQuery({
    queryKey: ["geometry", projectId],
    queryFn: () => api.projectGeometry(projectId),
  });
}

/** Move the shared boundary onto a point of the neighbouring day. */
/** Put a day's start or end on a point, handing the difference to the neighbour. */
export function useSetDayEdge(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      dayId: number;
      edge: "start" | "end";
      pointDayId: number;
      pointIndex: number;
    }) => api.setDayEdge(projectId, vars.dayId, vars.edge, vars.pointDayId, vars.pointIndex),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}

export function useHistory(projectId: number) {
  return useQuery({ queryKey: ["history", projectId], queryFn: () => api.history(projectId) });
}

export function useUndo(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.undo(projectId),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}

export function useRedo(projectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.redo(projectId),
    onSuccess: () => invalidateRouteData(qc, projectId),
  });
}
