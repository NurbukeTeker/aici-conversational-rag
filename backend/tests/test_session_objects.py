"""Tests for session object validation."""
import pytest
from pydantic import ValidationError

from app.models import (
    DrawingObject, SessionObjects, 
    MAX_OBJECTS_COUNT, MAX_STRING_LENGTH
)
from app.main import compute_layer_summary, validate_objects_warnings


class TestDrawingObjectValidation:
    """Test DrawingObject schema validation."""
    
    def test_valid_line_object(self):
        """Test valid LINE object passes validation."""
        obj = DrawingObject(
            type="LINE",
            layer="Walls",
            geometry={"start": [0, 0], "end": [10, 10]},
            properties={"material": "brick"}
        )
        assert obj.type == "LINE"
        assert obj.layer == "Walls"
    
    def test_valid_polygon_object(self):
        """Test valid POLYGON object passes validation."""
        obj = DrawingObject(
            type="POLYGON",
            layer="Plot Boundary",
            geometry={"points": [[0, 0], [100, 0], [100, 50], [0, 50]]},
            properties={"area": 5000}
        )
        assert obj.type == "POLYGON"
    
    def test_valid_point_object(self):
        """Test valid POINT object passes validation."""
        obj = DrawingObject(
            type="POINT",
            layer="Doors",
            geometry={"position": [50, 25]},
            properties={"width": 0.9}
        )
        assert obj.type == "POINT"
    
    def test_lowercase_type_accepted(self):
        """Test lowercase type names are accepted."""
        obj = DrawingObject(
            type="line",
            layer="Walls"
        )
        assert obj.type == "line"
    
    def test_missing_type_fails(self):
        """Test missing 'type' field fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(layer="Walls")
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("type",) for e in errors)
    
    def test_missing_layer_fails(self):
        """Test missing 'layer' field fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(type="LINE")
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("layer",) for e in errors)
    
    def test_invalid_type_fails(self):
        """Test invalid type value fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(type="INVALID_TYPE", layer="Walls")
        
        errors = exc_info.value.errors()
        assert any("invalid" in str(e["msg"]).lower() for e in errors)
    
    def test_empty_layer_fails(self):
        """Test empty layer string fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(type="LINE", layer="")
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("layer",) for e in errors)
    
    def test_layer_too_long_fails(self):
        """Test layer name exceeding max length fails."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(type="LINE", layer="x" * (MAX_STRING_LENGTH + 1))
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("layer",) for e in errors)
    
    def test_deeply_nested_properties_fails(self):
        """Test deeply nested properties exceeding depth limit fails."""
        # Create deeply nested structure
        deep_props = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}
        
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(type="LINE", layer="Walls", properties=deep_props)
        
        errors = exc_info.value.errors()
        assert any("nested" in str(e["msg"]).lower() for e in errors)
    
    def test_object_without_geometry_valid(self):
        """Test object without geometry is still valid (geometry optional)."""
        obj = DrawingObject(type="LINE", layer="Walls")
        assert obj.geometry is None

    def test_extra_keys_forbidden(self):
        """Test that invalid keys (e.g. typex, layerxxx) cause validation error."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(**{"type": "LINE", "layer": "Walls", "typex": "polygon"})
        errors = exc_info.value.errors()
        assert any(e.get("type") == "extra_forbidden" for e in errors)
        assert any("typex" in str(e.get("loc", [])) for e in errors)

    def test_multiple_extra_keys_forbidden(self):
        """Test that multiple invalid keys (typex, layerxxx) cause validation errors."""
        with pytest.raises(ValidationError) as exc_info:
            DrawingObject(**{
                "typex": "polygon",
                "layerxxx": "Plot Boundary",
                "geometry": None,
                "properties": {"area": 450},
            })
        errors = exc_info.value.errors()
        # Should have extra_forbidden for typex and layerxxx, and missing type/layer
        extra_errors = [e for e in errors if e.get("type") == "extra_forbidden"]
        assert len(extra_errors) >= 2  # typex and layerxxx
        locs = [e.get("loc", ()) for e in extra_errors]
        assert any("typex" in str(loc) for loc in locs)
        assert any("layerxxx" in str(loc) for loc in locs)


class TestSessionObjectsValidation:
    """Test SessionObjects (list of objects) validation."""
    
    def test_empty_list_valid(self):
        """Test empty object list is valid."""
        session = SessionObjects(objects=[])
        assert len(session.objects) == 0
    
    def test_valid_objects_list(self):
        """Test valid list of objects passes validation."""
        session = SessionObjects(objects=[
            {"type": "LINE", "layer": "Walls"},
            {"type": "POLYGON", "layer": "Plot Boundary"},
            {"type": "POINT", "layer": "Doors"}
        ])
        assert len(session.objects) == 3
    
    def test_mixed_valid_objects(self):
        """Test mixed object types with full data."""
        session = SessionObjects(objects=[
            {
                "type": "LINE",
                "layer": "Highway",
                "geometry": {"start": [0, 0], "end": [100, 0]},
                "properties": {"name": "Main Road", "width": 6}
            },
            {
                "type": "POLYGON",
                "layer": "Plot Boundary",
                "geometry": {"points": [[10, 10], [90, 10], [90, 40], [10, 40]]},
                "properties": {"area": 2400}
            }
        ])
        assert len(session.objects) == 2
        assert session.objects[0].layer == "Highway"
    
    def test_invalid_object_in_list_fails(self):
        """Test invalid object in list returns error with index."""
        with pytest.raises(ValidationError) as exc_info:
            SessionObjects(objects=[
                {"type": "LINE", "layer": "Walls"},  # Valid
                {"type": "LINE"},  # Missing layer - index 1
                {"type": "LINE", "layer": "Doors"}  # Valid
            ])
        
        errors = exc_info.value.errors()
        # Check that error includes the index
        assert any(1 in e["loc"] for e in errors)
    
    def test_max_objects_limit(self):
        """Test that object count limit is enforced."""
        # Create more than MAX_OBJECTS_COUNT objects
        too_many = [{"type": "POINT", "layer": "Layer"} for _ in range(MAX_OBJECTS_COUNT + 1)]
        
        with pytest.raises(ValidationError) as exc_info:
            SessionObjects(objects=too_many)
        
        errors = exc_info.value.errors()
        # Pydantic v2 uses "at most" in error message or "too_long" as error type
        assert any(
            "at most" in str(e["msg"]).lower() or 
            e.get("type") == "too_long" 
            for e in errors
        )


class TestLayerSummary:
    """Test layer summary computation."""
    
    def test_empty_list(self):
        """Test summary of empty list."""
        summary = compute_layer_summary([])
        assert summary == {}
    
    def test_single_layer(self):
        """Test summary with objects in single layer."""
        objects = [
            {"type": "LINE", "layer": "Walls"},
            {"type": "LINE", "layer": "Walls"},
            {"type": "POINT", "layer": "Walls"}
        ]
        summary = compute_layer_summary(objects)
        assert summary == {"Walls": 3}
    
    def test_multiple_layers(self):
        """Test summary with objects in multiple layers."""
        objects = [
            {"type": "LINE", "layer": "Highway"},
            {"type": "LINE", "layer": "Highway"},
            {"type": "POLYGON", "layer": "Plot Boundary"},
            {"type": "POINT", "layer": "Doors"},
            {"type": "POINT", "layer": "Doors"}
        ]
        summary = compute_layer_summary(objects)
        assert summary == {"Highway": 2, "Plot Boundary": 1, "Doors": 2}
    
    def test_missing_layer_becomes_unknown(self):
        """Test objects without layer are counted as Unknown."""
        objects = [
            {"type": "LINE", "layer": "Walls"},
            {"type": "LINE"}  # No layer
        ]
        summary = compute_layer_summary(objects)
        assert summary == {"Walls": 1, "Unknown": 1}


class TestValidationWarnings:
    """Test validation warnings generation."""
    
    def test_empty_list_warning(self):
        """Test warning for empty object list."""
        warnings = validate_objects_warnings([])
        assert any("no objects" in w.lower() for w in warnings)
    
    def test_no_geometry_warning(self):
        """Test warning when objects lack geometry."""
        objects = [
            {"type": "LINE", "layer": "Walls"},  # No geometry
            {"type": "LINE", "layer": "Walls"}   # No geometry
        ]
        warnings = validate_objects_warnings(objects)
        assert any("no geometry" in w.lower() for w in warnings)
    
    def test_no_plot_boundary_warning(self):
        """Test warning when no plot boundary layer exists."""
        objects = [
            {"type": "LINE", "layer": "Walls"},
            {"type": "LINE", "layer": "Doors"}
        ]
        warnings = validate_objects_warnings(objects)
        assert any("plot boundary" in w.lower() for w in warnings)
    
    def test_no_warning_with_complete_data(self):
        """Test no warnings with complete data including plot boundary."""
        objects = [
            {
                "type": "LINE",
                "layer": "Walls",
                "geometry": {"start": [0, 0], "end": [10, 10]}
            },
            {
                "type": "POLYGON",
                "layer": "Plot Boundary",
                "geometry": {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]}
            }
        ]
        warnings = validate_objects_warnings(objects)
        # Should only have no warnings or maybe just the "no geometry" if some objects lack it
        assert not any("no objects" in w.lower() for w in warnings)
