/** Route colours by a day's position in the trip, so neighbouring days are easy to
 *  tell apart on the map. Steers clear of the start/end green and red and the POI
 *  purple, and cycles once a trip runs past the end of the list. */
const DAY_COLORS = [
  "#2563eb", // blue
  "#ea580c", // orange
  "#0d9488", // teal
  "#db2777", // pink
  "#65a30d", // lime
  "#4f46e5", // indigo
  "#ca8a04", // mustard
  "#0e7490", // dark cyan
];

export function dayColor(position: number): string {
  if (position < 0) return DAY_COLORS[0];
  return DAY_COLORS[position % DAY_COLORS.length];
}

/** Colour for every day, keyed by id, from each day's place in the trip order. */
export function dayColorMap(days: { id: number; order_index: number }[]): Map<number, string> {
  const ordered = [...days].sort((a, b) => a.order_index - b.order_index);
  return new Map(ordered.map((d, i) => [d.id, dayColor(i)]));
}
