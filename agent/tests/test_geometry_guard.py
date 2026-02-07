"""Unit and integration tests for geometry guard."""
import pytest
from unittest.mock import patch, MagicMock

from app.geometry_guard import (
    is_spatial_question,
    required_layers_for_question,
    has_geometry,
    missing_geometry_layers,
)


class TestIsSpatialQuestion:
    """is_spatial_question: spatial questions True, definition-only False."""

    def test_front_a_highway_true(self):
        assert is_spatial_question("Does this property front a highway?") is True

    def test_what_is_a_highway_false(self):
        assert is_spatial_question("What is a highway?") is False

    def test_adjacent_distance_angle_true(self):
        assert is_spatial_question("Is the wall adjacent to the boundary?") is True
        assert is_spatial_question("What is the distance to the highway?") is True
        assert is_spatial_question("Angle between front and side?") is True

    def test_coordinates_geometry_true(self):
        assert is_spatial_question("Do we have coordinates for the plot?") is True
        assert is_spatial_question("Geometry of the highway?") is True


class TestRequiredLayersForQuestion:
    """required_layers_for_question: fronting → Highway + Plot Boundary; elevation/wall/door add more."""

    def test_fronting_includes_highway_and_plot_boundary(self):
        required = required_layers_for_question("Does this property front a highway?")
        assert "Highway" in required
        assert "Plot Boundary" in required

    def test_elevation_adds_walls_doors(self):
        required = required_layers_for_question("Does the principal elevation front the highway?")
        assert "Highway" in required
        assert "Plot Boundary" in required
        assert "Walls" in required
        assert "Doors" in required


class TestMissingGeometryLayers:
    """missing_geometry_layers: returns layers that have objects but all lack geometry."""

    def test_highway_and_plot_boundary_null_returns_both(self):
        """If Highway and Plot Boundary objects exist with geometry: null → returns ['Highway', 'Plot Boundary']."""
        session_objects = [
            {"layer": "Highway", "geometry": None, "type": "line"},
            {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
        ]
        required = {"Highway", "Plot Boundary"}
        result = missing_geometry_layers(session_objects, required)
        assert set(result) == {"Highway", "Plot Boundary"}

    def test_geometry_present_returns_empty(self):
        """If geometry present on required layers → returns []."""
        session_objects = [
            {"layer": "Highway", "geometry": {"coordinates": [0, 0]}, "type": "line"},
            {"layer": "Plot Boundary", "geometry": {"coordinates": [[0, 0], [1, 0], [1, 1]]}, "type": "polygon"},
        ]
        required = {"Highway", "Plot Boundary"}
        result = missing_geometry_layers(session_objects, required)
        assert result == []

    def test_one_layer_has_geometry_one_missing(self):
        """One layer has geometry, one missing → only missing layer in result."""
        session_objects = [
            {"layer": "Highway", "geometry": None},
            {"layer": "Plot Boundary", "geometry": {"coordinates": [[0, 0], [1, 0]]}},
        ]
        required = {"Highway", "Plot Boundary"}
        result = missing_geometry_layers(session_objects, required)
        assert result == ["Highway"]

    def test_no_objects_for_required_layer_not_listed(self):
        """Layers with no objects are not in missing list."""
        session_objects = [
            {"layer": "Highway", "geometry": None},
        ]
        required = {"Highway", "Plot Boundary"}
        result = missing_geometry_layers(session_objects, required)
        assert result == ["Highway"]


class TestHasGeometry:
    """has_geometry: True only when geometry dict has non-empty coordinates."""

    def test_null_geometry_false(self):
        assert has_geometry({"layer": "Highway", "geometry": None}) is False

    def test_empty_coordinates_false(self):
        assert has_geometry({"layer": "Highway", "geometry": {"coordinates": []}}) is False
        assert has_geometry({"layer": "Highway", "geometry": {"coordinates": None}}) is False

    def test_valid_point_true(self):
        assert has_geometry({"layer": "Highway", "geometry": {"coordinates": [0, 0]}}) is True
        assert has_geometry({"layer": "Highway", "geometry": {"coordinates": [[0, 0], [1, 0]]}}) is True


class TestGeometryGuardIntegration:
    """Integration: /answer with geometry null and spatial question → deterministic response, no retrieval/LLM."""

    @pytest.fixture
    def client(self):
        try:
            from fastapi.testclient import TestClient
            from app.main import app
        except Exception as e:
            pytest.skip(f"App not available: {e}")
        return TestClient(app)

    def test_front_highway_null_geometry_no_retrieval_no_llm(self, client):
        """
        Build AnswerRequest with geometry null and 'Does this property front a highway?'
        Assert: answer contains 'Cannot determine' / 'missing geometric information',
        evidence.document_chunks == [], and vector_store.search and llm_service.generate_answer not called.
        """
        from app import main
        if main.vector_store is None:
            pytest.skip("vector_store not initialized in this environment")
        session_objects = [
            {"layer": "Highway", "geometry": None, "type": "line"},
            {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
        ]
        request_body = {
            "question": "Does this property front a highway if no geometry is provided?",
            "session_objects": session_objects,
        }
        with patch.object(main, "vector_store", MagicMock()) as mock_vs:
            with patch.object(main, "llm_service", MagicMock()) as mock_llm:
                mock_vs.is_ready = MagicMock(return_value=True)
                mock_vs.search = MagicMock(return_value=[])
                mock_llm.is_available = MagicMock(return_value=True)
                mock_llm.generate_answer = MagicMock(return_value="Yes.")
                resp = client.post("/answer", json=request_body)
        if resp.status_code == 503:
            pytest.skip("App returned 503 (services not ready)")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        answer = data["answer"]
        assert "Cannot determine" in answer or "missing" in answer.lower() or "geometric information" in answer
        assert data["evidence"]["document_chunks"] == []
        mock_vs.search.assert_not_called()
        mock_llm.generate_answer.assert_not_called()
