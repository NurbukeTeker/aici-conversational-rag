"""Unit and integration tests for geometry guard."""
import pytest
from unittest.mock import patch, MagicMock

from app.guards.geometry_guard import (
    is_spatial_question,
    should_trigger_geometry_guard,
    required_layers_for_question,
    has_geometry,
    missing_geometry_layers,
)


class TestShouldTriggerGeometryGuard:
    """One rule: trigger only for questions about THIS drawing, not general rules."""

    def test_general_rule_phrases_do_not_trigger(self):
        assert should_trigger_geometry_guard("What is meant by fronting?") is False
        assert should_trigger_geometry_guard("What is a highway?") is False
        assert should_trigger_geometry_guard("According to the regulations, does fronting apply?") is False
        assert should_trigger_geometry_guard("Generally, would this be permitted?") is False
        assert should_trigger_geometry_guard("Would development normally be permitted?") is False
        assert should_trigger_geometry_guard("Does the presence of a wall restrict the front?") is False

    def test_would_this_property_triggers(self):
        """'Would this property front...' is about this drawing -> trigger guard."""
        assert should_trigger_geometry_guard("Would this property front a highway?") is True

    def test_would_normally_permitted_does_not_trigger(self):
        """'Would development ... normally be permitted?' is general rule -> do not trigger."""
        assert should_trigger_geometry_guard("Would development in front of the principal elevation normally be permitted?") is False

    def test_this_drawing_spatial_triggers(self):
        assert should_trigger_geometry_guard("Does this property front a highway?") is True
        assert should_trigger_geometry_guard("Is this plot adjacent to the highway?") is True
        assert should_trigger_geometry_guard("In the current drawing, does the plot front?") is True
        assert should_trigger_geometry_guard("In this drawing, does the plot front?") is True
        assert should_trigger_geometry_guard("Given this drawing, is there fronting?") is True

    def test_spatial_but_not_about_this_drawing_does_not_trigger(self):
        """Spatial keywords but no 'this property/plot/drawing' → no guard."""
        assert should_trigger_geometry_guard("What is the distance to the highway?") is False
        assert should_trigger_geometry_guard("When is a property said to front?") is False


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
        retrieval/LLM not called.
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
        with patch("app.rag.retrieval.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.graph_lc.nodes.invoke_hybrid", MagicMock(return_value="Yes.")):
                resp = client.post("/answer", json=request_body)
        if resp.status_code == 503:
            pytest.skip("App returned 503 (services not ready)")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        answer = data["answer"]
        assert "Cannot determine" in answer or "missing" in answer.lower() or "geometric information" in answer
        mock_retrieve.assert_not_called()

    def test_needs_input_followup_returns_checklist_no_retrieval_no_llm(self, client):
        """
        Session has Highway + Plot Boundary with geometry null.
        Q "what it needs?" -> returns concise checklist, no document chunks, no retrieval/LLM.
        """
        from app import main
        if main.vector_store is None:
            pytest.skip("vector_store not initialized in this environment")
        session_objects = [
            {"layer": "Highway", "geometry": None, "type": "line"},
            {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
        ]
        request_body = {
            "question": "what it needs?",
            "session_objects": session_objects,
        }
        with patch("app.rag.retrieval.retrieve", MagicMock(return_value=[])) as mock_retrieve:
            with patch("app.graph_lc.nodes.invoke_hybrid", MagicMock(return_value="Generic long answer.")):
                resp = client.post("/answer", json=request_body)
        if resp.status_code == 503:
            pytest.skip("App returned 503 (services not ready)")
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        answer = data["answer"]
        assert "Highway" in answer and "Plot Boundary" in answer
        assert "geometry" in answer.lower() or "coordinates" in answer.lower()
        mock_retrieve.assert_not_called()
