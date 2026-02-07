"""Follow-up handlers for geometry-guard refusals.

When the user asks follow-up questions like 'what it needs?' after a geometry-guard
refusal, we return a deterministic checklist without retrieval/LLM.
"""
from __future__ import annotations

import re

# English phrases (normalized: lowercase, optional punctuation)
_NEEDS_INPUT_PHRASES_EN = (
    r"what\s+it\s+needs",
    r"what\s+do\s+you\s+need",
    r"what\s+is\s+needed",
    r"what'?s\s+missing",
    r"what\s+do\s+i\s+need",
)

# Turkish phrases
_NEEDS_INPUT_PHRASES_TR = (
    r"ne\s+laz[ıi]m",
    r"ne\s+gerekiyor",
    r"ne\s+eksik",
    r"neye\s+ihtiya[çc]",
)

_NEEDS_INPUT_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (*_NEEDS_INPUT_PHRASES_EN, *_NEEDS_INPUT_PHRASES_TR)
]


def is_needs_input_followup(question: str) -> bool:
    """
    Return True if the question is a follow-up asking what input/geometry is needed.

    Matches phrases like:
    - English: "what it needs", "what do you need", "what is needed", "what's missing", "what do i need"
    - Turkish: "ne lazım", "ne gerekiyor", "ne eksik", "neye ihtiyaç"
    """
    if not question or not isinstance(question, str):
        return False
    text = (question or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _NEEDS_INPUT_PATTERNS)


def _layer_name(obj: dict) -> str | None:
    """Return canonical layer name from object."""
    layer = obj.get("layer") or obj.get("Layer")
    if layer is None or (isinstance(layer, str) and not layer.strip()):
        return None
    return str(layer).strip()


def get_missing_geometry_layers(session_objects: list[dict]) -> list[str]:
    """
    Determine which layers need geometry using geometry guard logic.

    Prefer: Highway and Plot Boundary if they exist and lack geometry.
    If all geometries are null, include all layers present (or at least Highway + Plot Boundary if present).
    """
    from .geometry_guard import missing_geometry_layers, has_geometry

    if not session_objects:
        return []

    layers_present = set()
    for obj in session_objects:
        ln = _layer_name(obj)
        if ln:
            layers_present.add(ln)

    # Always consider Highway and Plot Boundary when relevant
    required = layers_present | {"Highway", "Plot Boundary"}
    missing = missing_geometry_layers(session_objects, required)

    return sorted(missing)


def build_needs_input_message(missing_layers: list[str]) -> str:
    """
    Return a concise checklist: which layers need geometry and what geometry means.

    Geometry = non-null geometry with coordinates.
    """
    if not missing_layers:
        return (
            "All required layers have valid geometry. "
            "Geometry means non-null geometry with coordinates."
        )
    layers_str = ", ".join(missing_layers)
    return (
        f"**Layers needing geometry:** {layers_str}\n\n"
        "**Geometry requirement:** Non-null geometry with coordinates "
        "(e.g. points, lines, polygons with coordinate arrays). "
        "Add or correct geometry in the drawing for these layers to answer spatial questions."
    )
