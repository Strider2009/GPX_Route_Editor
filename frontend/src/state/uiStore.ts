import { create } from "zustand";

type Mode = "select" | "add-connector-point";

interface UIState {
  selectedDayId: number | null;
  selectedPointIndex: number | null;
  /** Previewed under the cursor. Separate from selection: it must not scroll the
   *  point list or move the map, only light the point up. */
  hoveredPointIndex: number | null;
  /** A point picked on one of the shadow days, so it can be shown and acted on. */
  shadowPoint: { dayId: number; index: number; lat: number; lon: number } | null;
  rangeStart: number | null;
  mode: Mode;
  /** Bumped only when the user actively picks a point, which is the only time the map moves. */
  panRequestId: number;
  /** The POI picked on the map or in the panel; highlighted in both. */
  selectedPoiId: number | null;
  /** Bumped when a POI is picked from the panel, so the map brings it into view. */
  poiPanRequestId: number;
  setSelectedDay: (id: number | null) => void;
  setSelectedPoint: (index: number | null) => void;
  setHoveredPoint: (index: number | null) => void;
  setShadowPoint: (p: UIState["shadowPoint"]) => void;
  selectPointQuietly: (index: number) => void;
  setRangeStart: (index: number | null) => void;
  setMode: (m: Mode) => void;
  /** pan: move the map to it - wanted from the panel, not when it was clicked on the map. */
  selectPoi: (id: number | null, pan?: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedDayId: null,
  selectedPointIndex: null,
  hoveredPointIndex: null,
  shadowPoint: null,
  rangeStart: null,
  mode: "select",
  panRequestId: 0,
  selectedPoiId: null,
  poiPanRequestId: 0,
  setSelectedDay: (id) =>
    set({
      selectedDayId: id,
      selectedPointIndex: null,
      hoveredPointIndex: null,
      shadowPoint: null,
      rangeStart: null,
      selectedPoiId: null,
    }),
  setHoveredPoint: (index) => set({ hoveredPointIndex: index }),
  setShadowPoint: (p) => set({ shadowPoint: p }),
  // The user picked a point, so bring it into view.
  setSelectedPoint: (index) =>
    set((s) => ({ selectedPointIndex: index, shadowPoint: null, panRequestId: s.panRequestId + 1 })),
  // Select without moving the map. Used when a route edit renumbers the points
  // (the map is already on that spot) and when right-clicking, where the menu is
  // pinned to the cursor and would drift if the map slid underneath it.
  selectPointQuietly: (index) => set({ selectedPointIndex: index, shadowPoint: null }),
  setRangeStart: (index) => set({ rangeStart: index }),
  setMode: (m) => set({ mode: m }),
  selectPoi: (id, pan = false) =>
    set((s) => ({ selectedPoiId: id, poiPanRequestId: pan ? s.poiPanRequestId + 1 : s.poiPanRequestId })),
}));
