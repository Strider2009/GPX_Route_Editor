"""Mapbox Vector Tile decoding, with Web Mercator georeferencing.

Tiles are supplied by hand (saved from a browser), so this only needs to read
them - there is no tile fetching anywhere in the app.
"""

import math

GEOM_TYPES = {0: "UNKNOWN", 1: "POINT", 2: "LINESTRING", 3: "POLYGON"}


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _iter_fields(buf: bytes, start: int = 0, end: int | None = None):
    """Yield (field_number, wire_type, value) for a protobuf message."""
    pos = start
    end = len(buf) if end is None else end
    while pos < end:
        key, pos = _read_varint(buf, pos)
        field, wire = key >> 3, key & 0x07
        if wire == 0:
            val, pos = _read_varint(buf, pos)
            yield field, wire, val
        elif wire == 2:
            length, pos = _read_varint(buf, pos)
            yield field, wire, buf[pos : pos + length]
            pos += length
        elif wire == 5:
            yield field, wire, int.from_bytes(buf[pos : pos + 4], "little")
            pos += 4
        elif wire == 1:
            yield field, wire, int.from_bytes(buf[pos : pos + 8], "little")
            pos += 8
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")


def _parse_value(buf: bytes):
    """MVT Value: string=1, float=2, double=3, int=4, uint=5, sint=6, bool=7."""
    import struct

    for field, _wire, val in _iter_fields(buf):
        if field == 1:
            return val.decode("utf-8", "replace")
        if field == 2:
            return struct.unpack("<f", val.to_bytes(4, "little"))[0]
        if field == 3:
            return struct.unpack("<d", val.to_bytes(8, "little"))[0]
        if field in (4, 5):
            return val
        if field == 6:
            return (val >> 1) ^ -(val & 1)
        if field == 7:
            return bool(val)
    return None


def _packed_varints(buf: bytes) -> list[int]:
    out, pos = [], 0
    while pos < len(buf):
        v, pos = _read_varint(buf, pos)
        out.append(v)
    return out


def _decode_geometry(cmds: list[int]) -> list[list[tuple[int, int]]]:
    """Decode MVT geometry commands into rings/lines of tile-local points."""
    parts: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    x = y = 0
    i = 0
    while i < len(cmds):
        cmd_int = cmds[i]
        cmd_id, count = cmd_int & 0x7, cmd_int >> 3
        i += 1
        if cmd_id == 1:  # MoveTo - starts a new part
            for _ in range(count):
                if i + 1 >= len(cmds):
                    break
                x += (cmds[i] >> 1) ^ -(cmds[i] & 1)
                y += (cmds[i + 1] >> 1) ^ -(cmds[i + 1] & 1)
                i += 2
                if current:
                    parts.append(current)
                current = [(x, y)]
        elif cmd_id == 2:  # LineTo
            for _ in range(count):
                if i + 1 >= len(cmds):
                    break
                x += (cmds[i] >> 1) ^ -(cmds[i] & 1)
                y += (cmds[i + 1] >> 1) ^ -(cmds[i + 1] & 1)
                i += 2
                current.append((x, y))
        elif cmd_id == 7:  # ClosePath
            if current:
                current.append(current[0])
        else:
            break
    if current:
        parts.append(current)
    return parts


def tile_point_to_lonlat(
    z: int, x: int, y: int, px: float, py: float, extent: int
) -> tuple[float, float]:
    """Convert a tile-local coordinate to (lat, lon)."""
    n = 2**z
    lon = (x + px / extent) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + py / extent) / n))))
    return lat, lon


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) for a tile."""
    n = 2**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return south, west, north, east


def tile_for_lonlat(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def decode_tile(data: bytes, z: int, x: int, y: int) -> list[dict]:
    """Decode a vector tile into features with WGS84 geometry.

    Returns [{layer, geom_type, attrs, coords: [(lat, lon), ...]}]
    """
    features_out: list[dict] = []
    for field, _wire, val in _iter_fields(data):
        if field != 3:  # Tile.layers
            continue
        layer_name = None
        extent = 4096
        keys: list[str] = []
        values: list = []
        raw_features: list[bytes] = []
        for lf, _lwire, lval in _iter_fields(val):
            if lf == 1:
                layer_name = lval.decode("utf-8", "replace")
            elif lf == 2:
                raw_features.append(lval)
            elif lf == 3:
                keys.append(lval.decode("utf-8", "replace"))
            elif lf == 4:
                values.append(_parse_value(lval))
            elif lf == 5:
                extent = lval

        for fbuf in raw_features:
            tags: list[int] = []
            gtype = 0
            geom: list[int] = []
            for ff, fwire, fval in _iter_fields(fbuf):
                if ff == 2:
                    tags = _packed_varints(fval) if fwire == 2 else [fval]
                elif ff == 3:
                    gtype = fval
                elif ff == 4:
                    geom = _packed_varints(fval) if fwire == 2 else [fval]

            attrs = {}
            for i in range(0, len(tags) - 1, 2):
                k, v = tags[i], tags[i + 1]
                if k < len(keys) and v < len(values):
                    attrs[keys[k]] = values[v]

            coords: list[tuple[float, float]] = []
            for part in _decode_geometry(geom):
                for px, py in part:
                    coords.append(tile_point_to_lonlat(z, x, y, px, py, extent))

            features_out.append(
                {
                    "layer": layer_name,
                    "geom_type": GEOM_TYPES.get(gtype, str(gtype)),
                    "attrs": attrs,
                    "coords": coords,
                }
            )
    return features_out
