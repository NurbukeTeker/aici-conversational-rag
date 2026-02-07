"""Session reasoning and summary computation."""
import logging
from typing import Any
from collections import Counter

from .models import SessionSummary

logger = logging.getLogger(__name__)


class ReasoningService:
    """Service for computing session summaries and reasoning."""
    
    # Known layer types from the drawing specification
    KNOWN_LAYERS = {
        "Highway", "Plot Boundary", "Walls", "Doors", "Windows",
        "Roof", "Extension", "Garage", "Garden", "Fence",
        "Driveway", "Patio", "Conservatory"
    }
    
    def compute_session_summary(self, session_objects: list[dict[str, Any]]) -> SessionSummary:
        """Compute a summary of session objects for reasoning."""
        if not session_objects:
            return SessionSummary(
                layer_counts={},
                plot_boundary_present=False,
                highways_present=False,
                total_objects=0,
                limitations=["No session objects provided"]
            )
        
        # Count layers
        layers = []
        for obj in session_objects:
            layer = obj.get("layer", obj.get("Layer", "Unknown"))
            layers.append(layer)
        
        layer_counts = dict(Counter(layers))
        
        # Check for specific layers
        layer_names_lower = [l.lower() for l in layers]
        plot_boundary_present = any("plot" in l or "boundary" in l for l in layer_names_lower)
        highways_present = any("highway" in l or "road" in l for l in layer_names_lower)
        
        # Detect limitations
        limitations = self._detect_limitations(session_objects, layer_counts)
        
        return SessionSummary(
            layer_counts=layer_counts,
            plot_boundary_present=plot_boundary_present,
            highways_present=highways_present,
            total_objects=len(session_objects),
            limitations=limitations
        )
    
    def _object_has_geometry(self, obj: dict[str, Any]) -> bool:
        """
        True only if the object has usable coordinate/geometry data.
        - geometry must be non-null AND contain coordinate arrays (GeoJSON-like: geometry.coordinates).
        - OR object has top-level "coordinates" with a non-empty list.
        """
        if not obj or not isinstance(obj, dict):
            return False
        # Top-level coordinates (e.g. [x, y] or [[x,y], ...])
        coords = obj.get("coordinates")
        if coords is not None and isinstance(coords, (list, tuple)):
            if len(coords) > 0:
                first = coords[0]
                if isinstance(first, (list, tuple)):
                    return len(first) > 0
                return True
        # geometry dict with coordinates
        geometry = obj.get("geometry")
        if geometry is None or not isinstance(geometry, dict):
            return False
        coords = geometry.get("coordinates")
        if coords is None:
            return False
        if isinstance(coords, (list, tuple)) and len(coords) > 0:
            first = coords[0]
            if isinstance(first, (list, tuple)):
                return len(first) > 0
            return True
        return False

    def _detect_limitations(
        self,
        objects: list[dict[str, Any]],
        layer_counts: dict[str, int]
    ) -> list[str]:
        """Detect limitations in the session data."""
        limitations = []
        
        # Check for missing common layers
        layer_names = set(layer_counts.keys())
        layer_names_lower = {l.lower() for l in layer_names}
        
        if not any("plot" in l or "boundary" in l for l in layer_names_lower):
            limitations.append("No plot boundary defined")
        
        # Check for missing measurements
        has_measurements = False
        for obj in objects:
            props = obj.get("properties", obj.get("Properties", {}))
            if isinstance(props, dict):
                if any(k.lower() in ["length", "width", "height", "area", "distance"] 
                       for k in props.keys()):
                    has_measurements = True
                    break
        
        if not has_measurements:
            limitations.append("No measurement data found in objects")
        
        # Check for coordinate data: geometry must be non-null and contain coordinate arrays
        has_coordinates = False
        for obj in objects:
            if self._object_has_geometry(obj):
                has_coordinates = True
                break
        
        if not has_coordinates:
            limitations.append("No coordinate/geometry data found")
        
        return limitations
    
    def extract_layers_used(
        self,
        session_objects: list[dict[str, Any]],
        question: str
    ) -> tuple[list[str], list[int]]:
        """Extract which layers are relevant to the question."""
        question_lower = question.lower()
        
        layers_used = []
        indices_used = []
        
        # Keywords to layer mapping
        keyword_layer_map = {
            "highway": ["highway", "road"],
            "boundary": ["plot boundary", "boundary", "plot"],
            "wall": ["walls", "wall"],
            "door": ["doors", "door"],
            "window": ["windows", "window"],
            "extension": ["extension"],
            "roof": ["roof"],
        }
        
        # Find relevant keywords in question
        relevant_layer_keywords = set()
        for keyword, layer_matches in keyword_layer_map.items():
            if keyword in question_lower:
                relevant_layer_keywords.update(layer_matches)
        
        # If no specific keywords, include all layers
        if not relevant_layer_keywords:
            relevant_layer_keywords = None
        
        # Find matching objects
        for idx, obj in enumerate(session_objects):
            layer = obj.get("layer", obj.get("Layer", "")).lower()
            
            if relevant_layer_keywords is None or any(kw in layer for kw in relevant_layer_keywords):
                layers_used.append(obj.get("layer", obj.get("Layer", "Unknown")))
                indices_used.append(idx)
        
        return layers_used, indices_used
    
    def validate_json_schema(self, session_objects: list[dict[str, Any]]) -> list[str]:
        """Validate session JSON and return warnings."""
        warnings = []
        
        if not isinstance(session_objects, list):
            warnings.append("Session objects must be a list")
            return warnings
        
        for idx, obj in enumerate(session_objects):
            if not isinstance(obj, dict):
                warnings.append(f"Object at index {idx} is not a dictionary")
                continue
            
            # Check for required fields
            if "layer" not in obj and "Layer" not in obj:
                warnings.append(f"Object at index {idx} missing 'layer' field")
        
        return warnings
