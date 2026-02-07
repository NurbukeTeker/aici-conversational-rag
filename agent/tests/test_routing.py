"""Unit tests for question routing (DOC_ONLY, JSON_ONLY, HYBRID)."""
import pytest
from app.routing import (
    is_definition_only_question,
    is_json_only_question,
    get_query_mode,
)


class TestIsDefinitionOnlyQuestion:
    """Routing: doc_only = True for definition-style, False when drawing intent present."""

    def test_what_is_considered_a_highway_doc_only_true(self):
        """What is considered a highway? → doc_only = True."""
        assert is_definition_only_question("What is considered a highway?") is True

    def test_define_principal_elevation_doc_only_true(self):
        """Define principal elevation → doc_only = True."""
        assert is_definition_only_question("Define principal elevation") is True

    def test_does_this_property_front_highway_doc_only_false(self):
        """Does this property front a highway? → doc_only = False (property, front)."""
        assert is_definition_only_question("Does this property front a highway?") is False

    def test_what_is_highway_in_my_drawing_doc_only_false(self):
        """What is a highway in my drawing? → doc_only = False (drawing intent)."""
        assert is_definition_only_question("What is a highway in my drawing?") is False

    def test_what_is_highway_no_drawing_keywords_doc_only_true(self):
        """What is a highway? (no drawing keywords) → doc_only = True."""
        assert is_definition_only_question("What is a highway?") is True

    def test_meaning_of_highway_doc_only_true(self):
        """Meaning of highway → doc_only = True."""
        assert is_definition_only_question("Meaning of highway") is True

    def test_extension_allowed_doc_only_false(self):
        """Question containing 'extension' / 'allowed' → doc_only = False."""
        assert is_definition_only_question("Is this extension allowed?") is False
        assert is_definition_only_question("What does comply mean for walls?") is False


class TestIsJsonOnlyQuestion:
    """Routing: json_only = True for counting/listing session objects only."""

    def test_how_many_layers_json_only_true(self):
        assert is_json_only_question("How many drawing layers are present?") is True
        assert is_json_only_question("How many layers are there?") is True

    def test_list_layers_json_only_true(self):
        assert is_json_only_question("List the layers") is True

    def test_what_layers_present_json_only_true(self):
        assert is_json_only_question("What layers are in the drawing?") is True

    def test_definition_not_json_only(self):
        """Definition questions are doc_only, not json_only."""
        assert is_json_only_question("What is the definition of a highway?") is False

    def test_hybrid_not_json_only(self):
        assert is_json_only_question("Does this property front a highway?") is False

    def test_what_is_width_of_main_road_json_only_true(self):
        """Object property from drawing -> JSON_ONLY."""
        assert is_json_only_question("What is the width of Main Road?") is True
        assert is_json_only_question("What is the height of the extension?") is True


class TestGetQueryMode:
    """Router: doc_only | json_only | hybrid."""

    def test_doc_only_definition_highway(self):
        """What is the definition of a highway? → doc_only."""
        assert get_query_mode("What is the definition of a highway?") == "doc_only"

    def test_json_only_how_many_layers(self):
        """How many drawing layers are present? → json_only."""
        assert get_query_mode("How many drawing layers are present?") == "json_only"

    def test_hybrid_fronts_highway(self):
        """Does this property front a highway? → hybrid."""
        assert get_query_mode("Does this property front a highway?") == "hybrid"

    def test_doc_only_define_principal_elevation(self):
        assert get_query_mode("Define principal elevation") == "doc_only"

    def test_json_only_list_objects(self):
        assert get_query_mode("List the objects in the drawing") == "json_only"
