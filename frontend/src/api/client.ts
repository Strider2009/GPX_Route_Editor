import type {
  ConnectorType,
  DayDetail,
  Point,
  ProjectDetail,
  ProjectSummary,
  FetchResult,
  Boundary,
  BoundaryList,
  DayWeather,
  HistoryStatus,
  ProjectGeometry,
  ShiftResult,
  PotholeFetchResult,
  PotholeResponse,
  RoadworksResponse,
  StravaRoute,
  StravaStatus,
  TilesForDay,
} from "./types";

const BASE = "/api";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isForm = options.body instanceof FormData;
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: isForm ? options.headers : { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listProjects: () => request<ProjectSummary[]>("/projects"),
  getProject: (id: number) => request<ProjectDetail>(`/projects/${id}`),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, { method: "DELETE" }),
  importProject: (files: File[], name?: string) => {
    const form = new FormData();
    if (name) form.append("name", name);
    files.forEach((f) => form.append("files", f));
    return request<ProjectDetail>("/projects/import", { method: "POST", body: form });
  },
  exportProjectUrl: (id: number, mode: "combined" | "zip" = "combined") =>
    `${BASE}/projects/${id}/export?mode=${mode}`,

  getDay: (id: number) => request<DayDetail>(`/days/${id}`),
  updateDay: (id: number, data: { name?: string; order_index?: number }) =>
    request<DayDetail>(`/days/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  history: (projectId: number) => request<HistoryStatus>(`/projects/${projectId}/history`),
  undo: (projectId: number) =>
    request<HistoryStatus & { undone: string }>(`/projects/${projectId}/undo`, { method: "POST" }),
  redo: (projectId: number) =>
    request<HistoryStatus & { redone: string }>(`/projects/${projectId}/redo`, { method: "POST" }),
  projectGeometry: (projectId: number) =>
    request<ProjectGeometry>(`/projects/${projectId}/geometry`),
  setDayEdge: (
    projectId: number,
    dayId: number,
    edge: "start" | "end",
    pointDayId: number,
    pointIndex: number
  ) =>
    request<{ days: unknown[] }>(
      `/projects/${projectId}/boundaries/set-edge?day_id=${dayId}&edge=${edge}` +
        `&point_day_id=${pointDayId}&point_index=${pointIndex}`,
      { method: "POST" }
    ),
  setDayRange: (dayId: number, startIndex: number, endIndex: number) =>
    request<DayDetail>(
      `/days/${dayId}/set-range?start_index=${startIndex}&end_index=${endIndex}`,
      { method: "POST" }
    ),
  restoreFullRoute: (dayId: number) =>
    request<DayDetail>(`/days/${dayId}/restore-full`, { method: "POST" }),
  reorderDays: (projectId: number, dayIds: number[]) =>
    request<ProjectDetail>(`/projects/${projectId}/days/reorder`, {
      method: "POST",
      body: JSON.stringify({ day_ids: dayIds }),
    }),
  boundaries: (projectId: number) => request<BoundaryList>(`/projects/${projectId}/boundaries`),
  moveBoundary: (projectId: number, index: number, deltaM: number) =>
    request<{ moved_m: number; boundary: Boundary }>(
      `/projects/${projectId}/boundaries/${index}/move?delta_m=${deltaM}`,
      { method: "POST" }
    ),
  shiftBoundaries: (projectId: number, deltaM: number) =>
    request<ShiftResult>(`/projects/${projectId}/boundaries/shift?delta_m=${deltaM}`, {
      method: "POST",
    }),
  setEndLocks: (dayId: number, locks: { lock_start?: boolean; lock_end?: boolean }) => {
    const q = new URLSearchParams();
    if (locks.lock_start !== undefined) q.set("lock_start", String(locks.lock_start));
    if (locks.lock_end !== undefined) q.set("lock_end", String(locks.lock_end));
    return request<DayDetail>(`/days/${dayId}/lock-end?${q.toString()}`, { method: "POST" });
  },
  splitEven: (id: number, parts: number, climbWeight: number) =>
    request<DayDetail[]>(`/days/${id}/split-even?parts=${parts}&climb_weight=${climbWeight}`, {
      method: "POST",
    }),
  dayWeather: (id: number, date: string) =>
    request<DayWeather>(`/days/${id}/weather?target_date=${date}`),
  addRoutesToProject: (projectId: number, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<ProjectDetail>(`/projects/${projectId}/import`, { method: "POST", body: form });
  },
  deleteDay: (id: number) => request<void>(`/days/${id}`, { method: "DELETE" }),
  setCircular: (id: number, value: boolean) =>
    request<DayDetail>(`/days/${id}/circular`, { method: "POST", body: JSON.stringify({ value }) }),
  setLocked: (id: number, value: boolean) =>
    request<DayDetail>(`/days/${id}/lock`, { method: "POST", body: JSON.stringify({ value }) }),
  rotate: (id: number, index: number) =>
    request<DayDetail>(`/days/${id}/rotate`, { method: "POST", body: JSON.stringify({ index }) }),
  trim: (id: number, start_index: number, end_index: number) =>
    request<DayDetail>(`/days/${id}/trim`, { method: "POST", body: JSON.stringify({ start_index, end_index }) }),
  reverse: (id: number) => request<DayDetail>(`/days/${id}/reverse`, { method: "POST" }),
  split: (id: number, indices: number[]) =>
    request<DayDetail[]>(`/days/${id}/split`, { method: "POST", body: JSON.stringify({ indices }) }),
  merge: (dayIdA: number, dayIdB: number) =>
    request<DayDetail>(`/days/merge`, {
      method: "POST",
      body: JSON.stringify({ day_id_a: dayIdA, day_id_b: dayIdB }),
    }),
  exportDayUrl: (id: number, includeConnectors = true) =>
    `${BASE}/days/${id}/export?include_connectors=${includeConnectors}`,

  addConnector: (dayId: number, data: { name: string; type: ConnectorType; points: Point[] }) =>
    request(`/days/${dayId}/connectors`, { method: "POST", body: JSON.stringify(data) }),
  updateConnector: (connectorId: number, data: { name?: string; points?: Point[] }) =>
    request(`/connectors/${connectorId}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteConnector: (connectorId: number) => request<void>(`/connectors/${connectorId}`, { method: "DELETE" }),

  getDayRoadworks: (
    dayId: number,
    opts: { targetDate?: string; bufferM?: number; minRelevance?: string; includeInactive?: boolean }
  ) => {
    const q = new URLSearchParams();
    if (opts.targetDate) q.set("target_date", opts.targetDate);
    if (opts.bufferM != null) q.set("buffer_m", String(opts.bufferM));
    if (opts.minRelevance) q.set("min_relevance", opts.minRelevance);
    if (opts.includeInactive) q.set("include_inactive", "true");
    return request<RoadworksResponse>(`/days/${dayId}/roadworks?${q.toString()}`);
  },
  tilesForDay: (dayId: number, z: number) => request<TilesForDay>(`/days/${dayId}/roadworks/tiles?z=${z}`),
  fetchRoadworks: (dayId: number, z: number, targetDate?: string) => {
    const q = new URLSearchParams({ z: String(z) });
    if (targetDate) q.set("target_date", targetDate);
    return request<FetchResult>(`/days/${dayId}/roadworks/fetch?${q.toString()}`, { method: "POST" });
  },
  stravaStatus: () => request<StravaStatus>("/strava/status"),
  stravaRoutes: () => request<StravaRoute[]>("/strava/routes"),
  importStravaRoute: (routeId: string, name?: string) =>
    request<ProjectDetail>(
      `/strava/routes/${routeId}/import${name ? `?name=${encodeURIComponent(name)}` : ""}`,
      { method: "POST" }
    ),
  disconnectStrava: () => request<void>("/strava/disconnect", { method: "POST" }),

  roadworksStatus: () =>
    request<{ total: number; cached_tiles: number; cached_bytes: number; last_fetch: string | null }>(
      "/roadworks"
    ),
  clearRoadworks: () => request<void>("/roadworks", { method: "DELETE" }),

  potholeStatus: () => request<{ total: number; areas_fetched: number; areas_saturated: number }>("/potholes"),
  clearPotholes: () => request<void>("/potholes", { method: "DELETE" }),
  fetchPotholes: (dayId: number, z: number) =>
    request<PotholeFetchResult>(`/days/${dayId}/potholes/fetch?z=${z}`, { method: "POST" }),
  getDayPotholes: (dayId: number, opts: { bufferM: number; maxAgeYears: number }) =>
    request<PotholeResponse>(
      `/days/${dayId}/potholes?buffer_m=${opts.bufferM}&max_age_years=${opts.maxAgeYears}`
    ),
};
