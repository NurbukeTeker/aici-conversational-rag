"""Tests for reasoning service."""
import pytest
from app.reasoning import ReasoningService


class TestReasoningService:
    """Test cases for ReasoningService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ReasoningService()
    
    def test_compute_session_summary_empty(self):
        """Test summary computation with empty objects."""
        summary = self.service.compute_session_summary([])
        
        assert summary.total_objects == 0
        assert summary.layer_counts == {}
        assert summary.plot_boundary_present is False
        assert summary.highways_present is False
        assert "No session objects provided" in summary.limitations
    
    def test_compute_session_summary_with_objects(self):
        """Test summary computation with sample objects."""
        objects = [
            {"layer": "Highway", "type": "line"},
            {"layer": "Highway", "type": "line"},
            {"layer": "Plot Boundary", "type": "polygon"},
            {"layer": "Walls", "type": "line"},
        ]
        
        summary = self.service.compute_session_summary(objects)
        
        assert summary.total_objects == 4
        assert summary.layer_counts["Highway"] == 2
        assert summary.layer_counts["Plot Boundary"] == 1
        assert summary.layer_counts["Walls"] == 1
        assert summary.plot_boundary_present is True
        assert summary.highways_present is True
    
    def test_validate_json_schema_valid(self):
        """Test JSON validation with valid objects."""
        objects = [
            {"layer": "Highway", "type": "line"},
            {"layer": "Walls", "type": "polygon"},
        ]
        
        warnings = self.service.validate_json_schema(objects)
        
        assert len(warnings) == 0
    
    def test_validate_json_schema_missing_layer(self):
        """Test JSON validation with missing layer field."""
        objects = [
            {"layer": "Highway"},
            {"type": "polygon"},  # Missing layer
        ]
        
        warnings = self.service.validate_json_schema(objects)
        
        assert len(warnings) == 1
        assert "missing 'layer' field" in warnings[0]
    
    def test_validate_json_schema_not_list(self):
        """Test JSON validation with non-list input."""
        warnings = self.service.validate_json_schema({"layer": "Highway"})
        
        assert len(warnings) == 1
        assert "must be a list" in warnings[0]

    def test_geometry_null_reports_no_coordinate_limitation(self):
        """geometry: null -> should report 'No coordinate/geometry data found'."""
        objects = [
            {"layer": "Highway", "geometry": None, "type": "line"},
            {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
        ]
        summary = self.service.compute_session_summary(objects)
        assert "No coordinate/geometry data found" in summary.limitations

    def test_geometry_with_coordinates_does_not_report_limitation(self):
        """Objects with valid geometry.coordinates -> should NOT report that limitation."""
        objects = [
            {"layer": "Highway", "geometry": {"coordinates": [[0, 0], [1, 0]]}, "type": "line"},
            {"layer": "Plot Boundary", "geometry": {"coordinates": [[0, 0], [1, 0], [1, 1], [0, 1]]}, "type": "polygon"},
        ]
        summary = self.service.compute_session_summary(objects)
        assert "No coordinate/geometry data found" not in summary.limitations
