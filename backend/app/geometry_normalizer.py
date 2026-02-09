"""Normalize geometry formats to GeoJSON for geometry guard compatibility.

Converts user-friendly formats (points, start/end) to GeoJSON coordinates
that the geometry guard expects.
"""
from typing import Any


def normalize_geometry(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize geometry to GeoJSON format (geometry.coordinates).
    
    Supports conversion from:
    - points → Polygon/Polyline coordinates
    - start/end → LineString coordinates
    - Already GeoJSON → pass through
    
    Returns normalized object (mutates input).
    """
    if not isinstance(obj, dict):
        return obj
    
    geometry = obj.get("geometry")
    if not isinstance(geometry, dict):
        return obj
    
    obj_type = obj.get("type", "").upper()
    
    # Already has coordinates? Pass through (but ensure GeoJSON structure)
    if "coordinates" in geometry:
        # Ensure it has type if missing
        if "type" not in geometry:
            geometry["type"] = _infer_geojson_type(obj_type, geometry["coordinates"])
        return obj
    
    # Convert points → coordinates (POLYGON, POLYLINE)
    if "points" in geometry:
        points = geometry["points"]
        if isinstance(points, list) and len(points) > 0:
            if obj_type == "POLYGON":
                # Polygon: wrap in extra array for GeoJSON
                geometry["coordinates"] = [points]
                geometry["type"] = "Polygon"
            elif obj_type == "POLYLINE":
                # Polyline: direct array
                geometry["coordinates"] = points
                geometry["type"] = "LineString"
            else:
                # Default: try to infer
                geometry["coordinates"] = points
                geometry["type"] = "LineString"
            # Remove old key
            del geometry["points"]
        return obj
    
    # Convert start/end → coordinates (LINE)
    if "start" in geometry and "end" in geometry:
        start = geometry["start"]
        end = geometry["end"]
        if isinstance(start, (list, tuple)) and isinstance(end, (list, tuple)):
            geometry["coordinates"] = [list(start), list(end)]
            geometry["type"] = "LineString"
            # Remove old keys
            del geometry["start"]
            del geometry["end"]
        return obj
    
    # Convert position → coordinates (POINT)
    if "position" in geometry:
        position = geometry["position"]
        if isinstance(position, (list, tuple)):
            geometry["coordinates"] = list(position)
            geometry["type"] = "Point"
            del geometry["position"]
        return obj
    
    # Convert center/radius → coordinates (CIRCLE)
    # Note: Circles aren't standard GeoJSON, but we can approximate with a point
    if "center" in geometry and "radius" in geometry:
        center = geometry["center"]
        if isinstance(center, (list, tuple)):
            geometry["coordinates"] = list(center)
            geometry["type"] = "Point"
            # Keep radius in properties or as metadata
            if "properties" not in obj:
                obj["properties"] = {}
            obj["properties"]["radius"] = geometry["radius"]
            del geometry["center"]
            del geometry["radius"]
        return obj
    
    return obj


def _infer_geojson_type(obj_type: str, coordinates: Any) -> str:
    """Infer GeoJSON geometry type from object type and coordinates structure."""
    if not isinstance(coordinates, list):
        return "Point"
    
    if obj_type == "POLYGON":
        return "Polygon"
    elif obj_type == "POLYLINE":
        return "LineString"
    elif obj_type == "LINE":
        return "LineString"
    elif obj_type == "POINT":
        return "Point"
    elif obj_type == "CIRCLE":
        return "Point"
    
    # Infer from structure
    if len(coordinates) == 0:
        return "Point"
    
    first = coordinates[0]
    if isinstance(first, list) and len(first) > 0:
        first_inner = first[0] if isinstance(first[0], list) else first
        if isinstance(first_inner, list):
            return "Polygon"  # Nested array: [[[x,y], ...]]
        return "LineString"  # Array of arrays: [[x,y], ...]
    
    return "Point"  # Single coordinate: [x, y]


def normalize_session_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalize all objects in a session to ensure geometry.coordinates format.
    
    Returns new list with normalized objects (does not mutate input).
    """
    normalized = []
    for obj in objects:
        # Create a copy to avoid mutating original
        obj_copy = dict(obj)
        if "geometry" in obj_copy and isinstance(obj_copy["geometry"], dict):
            obj_copy["geometry"] = dict(obj_copy["geometry"])
        normalized.append(normalize_geometry(obj_copy))
    return normalized
