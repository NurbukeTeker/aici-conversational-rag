"""Spatial analysis utilities for analyzing geometry relationships."""
from __future__ import annotations
from typing import Any
import math


def analyze_property_highway_relationship(
    plot_boundary: dict[str, Any],
    highway: dict[str, Any]
) -> dict[str, Any]:
    """
    Analyze spatial relationship between plot boundary and highway.
    
    Returns dict with:
    - fronts_highway: bool
    - distance_to_highway: float | None
    - analysis: str (human-readable)
    """
    plot_geom = plot_boundary.get("geometry")
    highway_geom = highway.get("geometry")
    
    # Handle None geometry
    if plot_geom is None or highway_geom is None:
        return {
            "fronts_highway": False,
            "distance_to_highway": None,
            "analysis": "Cannot determine: missing geometry"
        }
    
    # Ensure geometry is a dict
    if not isinstance(plot_geom, dict) or not isinstance(highway_geom, dict):
        return {
            "fronts_highway": False,
            "distance_to_highway": None,
            "analysis": "Cannot determine: invalid geometry format"
        }
    
    plot_coords = plot_geom.get("coordinates")
    highway_coords = highway_geom.get("coordinates")
    
    if not plot_coords or not highway_coords:
        return {
            "fronts_highway": False,
            "distance_to_highway": None,
            "analysis": "Cannot determine: missing coordinates"
        }
    
    # Extract coordinates based on GeoJSON type
    plot_points = _extract_points(plot_coords, plot_geom.get("type", "Polygon"))
    highway_points = _extract_points(highway_coords, highway_geom.get("type", "LineString"))
    
    if not plot_points or not highway_points:
        return {
            "fronts_highway": False,
            "distance_to_highway": None,
            "analysis": "Cannot determine: invalid geometry format"
        }
    
    # Check if property fronts highway (simplified: check if boundary edge is close/adjacent to highway)
    fronts, distance, analysis = _check_fronting(plot_points, highway_points)
    
    return {
        "fronts_highway": fronts,
        "distance_to_highway": distance,
        "analysis": analysis
    }


def _extract_points(coords: Any, geom_type: str) -> list[tuple[float, float]]:
    """Extract list of (x, y) points from GeoJSON coordinates."""
    if not coords:
        return []
    
    # Polygon: coordinates is [[[x,y], ...]] (first ring)
    if geom_type == "Polygon" and isinstance(coords, list) and len(coords) > 0:
        ring = coords[0]
        if isinstance(ring, list):
            return [(float(p[0]), float(p[1])) for p in ring if isinstance(p, list) and len(p) >= 2]
    
    # LineString: coordinates is [[x,y], ...]
    if geom_type == "LineString" and isinstance(coords, list):
        return [(float(p[0]), float(p[1])) for p in coords if isinstance(p, list) and len(p) >= 2]
    
    # Point: coordinates is [x, y]
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return [(float(coords[0]), float(coords[1]))]
    
    return []


def _check_fronting(
    plot_points: list[tuple[float, float]],
    highway_points: list[tuple[float, float]]
) -> tuple[bool, float | None, str]:
    """
    Check if plot fronts highway.
    Simplified: checks if any plot edge is close/adjacent to highway line.
    """
    if not plot_points or not highway_points:
        return False, None, "Insufficient points"
    
    # Find minimum distance from plot boundary to highway
    min_distance = float('inf')
    closest_plot_point = None
    closest_highway_point = None
    
    for plot_pt in plot_points:
        for highway_pt in highway_points:
            dist = math.sqrt((plot_pt[0] - highway_pt[0])**2 + (plot_pt[1] - highway_pt[1])**2)
            if dist < min_distance:
                min_distance = dist
                closest_plot_point = plot_pt
                closest_highway_point = highway_pt
    
    # Also check distance to highway line segments (not just points)
    for i in range(len(highway_points) - 1):
        seg_start = highway_points[i]
        seg_end = highway_points[i + 1]
        for plot_pt in plot_points:
            dist = _point_to_line_segment_distance(plot_pt, seg_start, seg_end)
            if dist < min_distance:
                min_distance = dist
    
    # Consider "fronting" if distance is very small (< 1 unit, or configurable threshold)
    threshold = 1.0
    fronts = min_distance < threshold
    
    if fronts:
        analysis = f"Property fronts highway (distance: {min_distance:.2f} units)"
    elif min_distance < float('inf'):
        analysis = f"Property is {min_distance:.2f} units from highway (does not front)"
    else:
        analysis = "Cannot determine fronting relationship"
    
    return fronts, min_distance if min_distance < float('inf') else None, analysis


def _point_to_line_segment_distance(
    point: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float]
) -> float:
    """Calculate distance from point to line segment."""
    px, py = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # Vector from line_start to line_end
    dx = x2 - x1
    dy = y2 - y1
    
    # If line segment is a point
    if dx == 0 and dy == 0:
        return math.sqrt((px - x1)**2 + (py - y1)**2)
    
    # Parameter t for closest point on line segment
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    
    # Closest point on line segment
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    
    # Distance
    return math.sqrt((px - closest_x)**2 + (py - closest_y)**2)


def analyze_session_spatial_relationships(session_objects: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Analyze spatial relationships in session objects.
    
    Returns dict with:
    - property_highway_analysis: dict | None
    - available_geometry: list[str] (layers with geometry)
    - missing_for_extensions: list[str] (what's needed for extension questions)
    """
    result = {
        "property_highway_analysis": None,
        "available_geometry": [],
        "missing_for_extensions": []
    }
    
    # Find plot boundary and highway
    plot_boundary = None
    highway = None
    
    for obj in session_objects:
        layer = obj.get("layer", "").lower()
        geometry = obj.get("geometry")
        
        # Check if geometry exists and has coordinates
        if geometry is not None and isinstance(geometry, dict):
            coords = geometry.get("coordinates")
            if coords:
                result["available_geometry"].append(obj.get("layer", "Unknown"))
        
        if "plot" in layer or "boundary" in layer:
            plot_boundary = obj
        if "highway" in layer or "road" in layer:
            highway = obj
    
    # Analyze property-highway relationship if both exist and have geometry
    if plot_boundary and highway:
        plot_geom = plot_boundary.get("geometry")
        highway_geom = highway.get("geometry")
        # Only analyze if both have valid geometry
        if (plot_geom is not None and isinstance(plot_geom, dict) and plot_geom.get("coordinates") and
            highway_geom is not None and isinstance(highway_geom, dict) and highway_geom.get("coordinates")):
            result["property_highway_analysis"] = analyze_property_highway_relationship(
                plot_boundary, highway
            )
    
    # Check what's missing for extension questions
    layers_present = {obj.get("layer", "").lower() for obj in session_objects}
    
    if "walls" not in layers_present:
        result["missing_for_extensions"].append("Walls layer (needed to determine principal/rear elevation)")
    if "doors" not in layers_present:
        result["missing_for_extensions"].append("Doors layer (helps identify principal elevation)")
    
    return result
