/** Turning OSM tags into things a cyclist can act on.
 *
 * "Drinking water" on its own doesn't say whether a bottle fits under it, whether
 * it costs anything, or whether anyone has checked it this decade. OSM usually
 * knows; it just spreads the answer across several tags.
 */

export interface Fact {
  label: string;
  /** good = a reason to go, warn = a reason to think twice, plain = context. */
  tone: "good" | "warn" | "plain";
}

const FOUNTAIN_LABEL: Record<string, string> = {
  bottle_refill: "Bottle refill",
  bubbler: "Bubbler - bottle may not fit",
  drinking: "Drinking fountain",
  tap: "Tap - unspecified type",
};

function monthsSince(iso: string): number | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return (Date.now() - t) / (1000 * 60 * 60 * 24 * 30.4);
}

export function venueFacts(kind: string, tags: Record<string, string>): Fact[] {
  const facts: Fact[] = [];
  const add = (label: string, tone: Fact["tone"] = "plain") => facts.push({ label, tone });

  if (kind === "water") {
    const f = tags.fountain;
    if (f) add(FOUNTAIN_LABEL[f] ?? f, f === "bottle_refill" ? "good" : f === "bubbler" ? "warn" : "plain");
    if (tags.bottle === "yes") add("Bottle fits", "good");
    if (tags.bottle === "no") add("No bottle", "warn");
    if (tags.seasonal === "yes") add("Seasonal - may be off", "warn");
    if (tags.indoor === "yes") add("Indoors", "warn");
  }

  if (tags.fee === "no") add("Free", "good");
  if (tags.fee === "yes") add("Charged", "warn");
  if (tags.access && !["yes", "public", "permissive"].includes(tags.access)) {
    add(`Access: ${tags.access}`, "warn");
  }

  if (kind === "cafe" || kind === "food") {
    if (tags.bicycle_parking) add("Bike parking", "good");
    if (tags.outdoor_seating === "yes") add("Outdoor seating");
    if (tags.takeaway === "yes") add("Takeaway");
    if (tags.internet_access && tags.internet_access !== "no") add("Wifi");
    if (tags["diet:vegan"] === "yes") add("Vegan options");
    if (tags.brand) add(tags.brand);
    if (tags.cuisine) add(tags.cuisine.replace(/_/g, " ").replace(/;/g, ", "));
  }

  if (tags.wheelchair === "yes") add("Step-free");
  if (tags.dog === "yes") add("Dogs ok");
  if (tags.operator) add(tags.operator);

  // Freshness last, because it qualifies everything above it.
  const checked = tags.check_date ?? tags["survey:date"];
  if (checked) {
    const months = monthsSince(checked);
    if (months == null) add(`Checked ${checked}`);
    else if (months < 24) add(`Checked ${checked.slice(0, 7)}`, "good");
    else add(`Last checked ${checked.slice(0, 4)}`, "warn");
  } else {
    add("Never verified", "warn");
  }

  return facts;
}

/** Tags shown verbatim when a venue is expanded, minus the ones already spoken for. */
export const SUMMARISED_TAGS = new Set([
  "fountain", "bottle", "fee", "access", "seasonal", "indoor", "wheelchair", "dog",
  "operator", "brand", "cuisine", "bicycle_parking", "outdoor_seating", "takeaway",
  "internet_access", "diet:vegan", "check_date", "survey:date",
]);
