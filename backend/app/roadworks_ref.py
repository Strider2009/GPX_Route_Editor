"""Code lookups for roadworks attributes.

Values taken from one.network's public /layer-filters endpoint, which is the
decode table for the integer codes carried in the vector tile features.
"""

# The integer codes the filter API uses, kept for reference. Tiles instead carry
# the label directly, and with finer granularity than this list (they also use
# "alternate one-way" and "priority working").
TRAFFIC_MANAGEMENT_CODES = {
    0: "Some roadway incursion",
    1: "Traffic control (stop/go boards)",
    2: "Traffic control (two-way signals)",
    3: "Traffic control (multi-way signals)",
    4: "Traffic control (give and take)",
    7: "Lane closure",
    9: "Road closure",
    12: "No roadway incursion",
    14: "Temporary obstruction (15 minute delay)",
    90: "Hard shoulder closure",
}

# How much each traffic-management type actually matters on a bike. Signals and
# lane closures are usually a non-event; a full road closure on a narrow lane is
# the thing that forces a reroute. Matched on the label, lowest match wins.
_RELEVANCE_RULES = [
    ("road closure", "high"),
    ("no carriageway incursion", "none"),
    ("no roadway incursion", "none"),
    ("hard shoulder", "none"),
    ("some carriageway incursion", "medium"),
    ("some roadway incursion", "medium"),
    ("temporary obstruction", "medium"),
    ("lane closure", "low"),
    ("traffic control", "low"),
]

RELEVANCE_ORDER = {"high": 3, "medium": 2, "low": 1, "none": 0}

IMPACT = {1: "Low - delays unlikely", 2: "Medium - delays possible", 3: "High - delays likely"}

WORKS_STATE = {
    -1: "No status",
    1: "Forward planning",
    2: "Advanced planning",
    3: "About to start",
    0: "In progress",
    4: "In progress",
    5: "Completed",
    6: "Completed",
    8: "Completed",
    7: "Cancelled",
}

PERMIT_STATUS = {
    -1: "No status",
    0: "No status",
    4: "Granted",
    5: "Revoked",
    11: "PAA granted",
    12: "Granted",
    13: "Granted",
    14: "PAA pending",
    25: "Modification request",
    26: "PAA granted",
    27: "Granted",
    28: "Granted",
    29: "Closed",
    30: "Under assessment",
    31: "Progressed",
    101: "Application (emergency)",
}

UTILITY_TYPE = {
    1: "Road agency",
    2: "Electricity",
    3: "Gas",
    4: "Water",
    5: "Fibre",
    6: "Rail",
    11: "Road agency contractor",
}

# Cancelled or completed works can't affect a future ride.
INACTIVE_WORKS_STATES = {5, 6, 7, 8}


def cycling_relevance(traffic_management: str | None, item_type: str | None = None) -> str:
    """Classify how much a work matters to a cyclist.

    Prefers the traffic-management label, but some layers (detours, closures)
    carry no traffman at all and describe themselves via itemtype instead - a
    detour exists precisely because something is shut, so it matters.
    """
    for text in (traffic_management, item_type):
        if not text:
            continue
        lowered = str(text).strip().lower()
        if "detour" in lowered or "diversion" in lowered:
            return "high"
        for needle, relevance in _RELEVANCE_RULES:
            if needle in lowered:
                return relevance
    return "low"


def label(table: dict, code):
    if code is None:
        return None
    try:
        return table.get(int(code))
    except (TypeError, ValueError):
        return None
