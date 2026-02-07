"""Unit tests for follow-up handlers."""
import pytest

from app.followups import (
    is_needs_input_followup,
    build_needs_input_message,
    get_missing_geometry_layers,
)


class TestIsNeedsInputFollowup:
    """is_needs_input_followup: detect follow-up phrases."""

    def test_what_it_needs_true(self):
        assert is_needs_input_followup("what it needs?") is True
        assert is_needs_input_followup("What it needs") is True

    def test_what_do_you_need_true(self):
        assert is_needs_input_followup("what do you need?") is True

    def test_what_is_needed_true(self):
        assert is_needs_input_followup("what is needed") is True

    def test_whats_missing_true(self):
        assert is_needs_input_followup("what's missing?") is True
        assert is_needs_input_followup("whats missing") is True

    def test_what_do_i_need_true(self):
        assert is_needs_input_followup("what do i need") is True

    def test_turkish_ne_lazim_true(self):
        assert is_needs_input_followup("ne lazım?") is True
        assert is_needs_input_followup("Ne lazım") is True

    def test_turkish_ne_gerekiyor_true(self):
        assert is_needs_input_followup("ne gerekiyor") is True

    def test_turkish_ne_eksik_true(self):
        assert is_needs_input_followup("ne eksik") is True

    def test_turkish_neye_ihtiyac_true(self):
        assert is_needs_input_followup("neye ihtiyaç") is True

    def test_normal_question_false(self):
        assert is_needs_input_followup("Does this property front a highway?") is False
        assert is_needs_input_followup("What is a highway?") is False
        assert is_needs_input_followup("How do I add geometry?") is False

    def test_empty_none_false(self):
        assert is_needs_input_followup("") is False
        assert is_needs_input_followup(None) is False


class TestBuildNeedsInputMessage:
    """build_needs_input_message: concise checklist."""

    def test_with_missing_layers(self):
        msg = build_needs_input_message(["Highway", "Plot Boundary"])
        assert "Highway" in msg
        assert "Plot Boundary" in msg
        assert "geometry" in msg.lower() or "coordinates" in msg.lower()

    def test_empty_layers(self):
        msg = build_needs_input_message([])
        assert "geometry" in msg.lower()
        assert "coordinates" in msg.lower() or "valid" in msg.lower()


class TestGetMissingGeometryLayers:
    """get_missing_geometry_layers: layers needing geometry."""

    def test_highway_plot_boundary_null_returns_both(self):
        session_objects = [
            {"layer": "Highway", "geometry": None, "type": "line"},
            {"layer": "Plot Boundary", "geometry": None, "type": "polygon"},
        ]
        result = get_missing_geometry_layers(session_objects)
        assert set(result) == {"Highway", "Plot Boundary"}

    def test_geometry_present_returns_empty(self):
        session_objects = [
            {"layer": "Highway", "geometry": {"coordinates": [0, 0]}, "type": "line"},
            {"layer": "Plot Boundary", "geometry": {"coordinates": [[0, 0], [1, 0]]}, "type": "polygon"},
        ]
        result = get_missing_geometry_layers(session_objects)
        assert result == []
