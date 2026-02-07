"""Unit tests for definition-only question routing."""
import pytest
from app.routing import is_definition_only_question


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
