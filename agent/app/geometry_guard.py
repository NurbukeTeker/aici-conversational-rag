"""Geometry guard: deterministic guard for spatial questions when geometry is missing.
Prevents the agent from inventing spatial relationships when session objects have
geometry: null or no coordinates.

Rule: Trigger geometry guard ONLY when the user is asking about THIS SPECIFIC DRAWING
(e.g. "does this property...", "in the current drawing..."), NOT when asking about
general rules (e.g. "what is meant by...", "according to the regulations").
"""
from __future__ import annotations

# Phrases that indicate a GENERAL RULE / explanatory question → do NOT trigger guard (DOC_ONLY style)
_GENERAL_RULE_PHRASES = (
    "what is meant by",
    "what is ",
    "would ",
    "normally be permitted",
    "does the presence of",
    "restrict ",
    "according to the regulations",
    "according to the regulation",
    "generally",
)

# Phrases that indicate the question is about THIS SPECIFIC DRAWING → required to trigger guard
_THIS_DRAWING_PHRASES = (
    "does this property",
    "is this plot",
    "in the current drawing",
    "given this drawing",
    "this drawing",
    "this property",
    "this plot",
)

# Keywords/phrases that indicate a spatial/geometric question (normalized lowercase)
_SPATIAL_KEYWORDS = frozenset({
    "front", "fronts", "fronting",
    "adjacent", "adjacency",
    "distance", "far", "near", "proximity",
    "angle", "degrees",
    "coordinates", "geometry",
    "intersects", "intersection", "touch", "overlap",
    "align", "parallel", "perpendicular",
    "orientation", "position", "located", "relative",
    "elevation",  # when used with fronts/highway
})

# Canonical layer names used in required_layers_for_question and missing_geometry_layers
_LAYER_HIGHWAY = "Highway"
_LAYER_PLOT_BOUNDARY = "Plot Boundary"
_LAYER_WALLS = "Walls"
_LAYER_DOORS = "Doors"

# For fronting questions we require at minimum these layers
_FRONTING_REQUIRED_LAYERS = {_LAYER_HIGHWAY, _LAYER_PLOT_BOUNDARY}

# Question keywords that add Walls/Doors to required layers
_EXTRA_LAYER_KEYWORDS = {
    "elevation": {_LAYER_WALLS, _LAYER_DOORS},
    "wall": {_LAYER_WALLS},
    "walls": {_LAYER_WALLS},
    "door": {_LAYER_DOORS},
    "doors": {_LAYER_DOORS},
}


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def should_trigger_geometry_guard(question: str) -> bool:
    """
    One clear rule: trigger geometry guard only when the user is asking about
    THIS SPECIFIC DRAWING (e.g. "does this property front..."), not about
    general rules (e.g. "what is meant by fronting?", "according to the regulations").
    Returns True only if the question is spatial AND about this drawing AND not general.
    """
    if not question or not isinstance(question, str):
        return False
    normalized = _normalize(question)
    if not normalized:
        return False
    # General rule / explanatory → do not trigger
    if any(phrase in normalized for phrase in _GENERAL_RULE_PHRASES):
        return False
    # Must be about this specific drawing
    if not any(phrase in normalized for phrase in _THIS_DRAWING_PHRASES):
        return False
    # Must be spatial (fronting, distance, etc.)
    return any(kw in normalized for kw in _SPATIAL_KEYWORDS)


def is_spatial_question(question: str) -> bool:
    """
    Return True if the question requires spatial/geometric reasoning (fronting,
    adjacency, distance, angle, coordinates, intersection, alignment, position, etc.).
    Keyword-based; no LLM.
    """
    if not question or not isinstance(question, str):
        return False
    normalized = _normalize(question)
    if not normalized:
        return False
    return any(kw in normalized for kw in _SPATIAL_KEYWORDS)


def required_layers_for_question(question: str) -> set[str]:
    """
    Return the set of layer names that must have valid geometry for this question.
    For front/fronting questions: at minimum Highway and Plot Boundary.
    If question mentions elevation, wall(s), door(s), also require those layers.
    """
    normalized = _normalize(question)
    required = set()
    # Fronting-style questions always need Highway and Plot Boundary
    if any(p in normalized for p in ("front", "fronts", "fronting")):
        required.update(_FRONTING_REQUIRED_LAYERS)
    # Other spatial keywords that imply highway/boundary (e.g. "does the property front")
    if any(k in normalized for k in ("highway", "boundary", "plot", "adjacent", "distance",
                                      "intersect", "touch", "overlap", "align", "position",
                                      "orientation", "coordinates", "geometry")):
        required.update(_FRONTING_REQUIRED_LAYERS)
    for kw, layers in _EXTRA_LAYER_KEYWORDS.items():
        if kw in normalized:
            required.update(layers)
    return required


def has_geometry(obj: dict) -> bool:
    """
    Return True only if obj has a geometry dict and geometry has valid non-empty
    coordinates (or a valid point coordinate array).
    """
    if not obj or not isinstance(obj, dict):
        return False
    geometry = obj.get("geometry")
    if geometry is None or not isinstance(geometry, dict):
        return False
    coords = geometry.get("coordinates")
    if coords is None:
        return False
    if isinstance(coords, (list, tuple)):
        if len(coords) == 0:
            return False
        # Nested array e.g. [[x,y], ...] or [x, y]
        first = coords[0]
        if isinstance(first, (list, tuple)):
            return len(first) > 0
        return True
    return False


def _layer_name(obj: dict) -> str | None:
    """Return canonical layer name from object (layer or Layer key)."""
    layer = obj.get("layer") or obj.get("Layer")
    if layer is None or (isinstance(layer, str) and not layer.strip()):
        return None
    return str(layer).strip()


def _layer_matches(layer: str, required: set[str]) -> bool:
    """True if layer (from object) matches any required layer (case-insensitive)."""
    layer_lower = layer.lower()
    for r in required:
        if r.lower() == layer_lower:
            return True
    # Also match partial: e.g. "Plot Boundary" required, object has "Plot boundary"
    for r in required:
        if r.lower() in layer_lower or layer_lower in r.lower():
            return True
    return False


def missing_geometry_layers(
    session_objects: list[dict],
    required_layers: set[str],
) -> list[str]:
    """
    For each required layer: if at least one object exists in that layer but
    every such object has missing/invalid geometry, add that layer to the result.
    Layers with no objects are not considered missing geometry (different issue).
    Returns list of layer names (canonical from required set) that have objects
    but all lack geometry.
    """
    if not required_layers:
        return []
    if not session_objects:
        return []
    # Group objects by matching required layer (use first matching canonical name per obj)
    from collections import defaultdict
    layer_to_objs: dict[str, list[dict]] = defaultdict(list)
    canonical_for_match: dict[str, str] = {}  # normalized key -> canonical name from required
    for r in required_layers:
        canonical_for_match[r.lower()] = r
    for obj in session_objects:
        layer = _layer_name(obj)
        if not layer:
            continue
        for req in required_layers:
            if _layer_matches(layer, {req}):
                layer_to_objs[req].append(obj)
                break
    missing = []
    for layer_name, objs in layer_to_objs.items():
        if not objs:
            continue
        if all(not has_geometry(o) for o in objs):
            missing.append(layer_name)
    return missing
