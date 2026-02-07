"""Tests for DOC_ONLY guard: term must appear in retrieved context."""
import pytest

from app.doc_only_guard import (
    extract_definition_term,
    term_appears_in_chunks,
    should_use_retrieved_for_doc_only,
)


class TestExtractDefinitionTerm:
    """extract_definition_term: quoted and unquoted definition-style questions."""

    def test_what_is_meant_by_quoted(self):
        assert extract_definition_term("What is meant by 'curtilage'?") == "curtilage"
        assert extract_definition_term('What is meant by "side elevation"?') == "side elevation"

    def test_what_is_meant_by_unquoted(self):
        assert extract_definition_term("What is meant by side elevation?") == "side elevation"
        assert extract_definition_term("What is meant by principal elevation?") == "principal elevation"

    def test_what_is_a_x(self):
        assert extract_definition_term("What is a highway?") == "highway"
        assert extract_definition_term("What is the principal elevation?") == "principal elevation"

    def test_what_is_the_definition_of_a_x(self):
        """Extract term from 'what is the definition of a X?' → X (not 'definition of a X')."""
        assert extract_definition_term("What is the definition of a highway?") == "highway"
        assert extract_definition_term("What is the meaning of a highway?") == "highway"

    def test_define_meaning(self):
        assert extract_definition_term("Define curtilage") == "curtilage"
        assert extract_definition_term("Definition of highway") == "highway"
        assert extract_definition_term("Meaning of fronting") == "fronting"

    def test_non_definition_returns_none(self):
        assert extract_definition_term("Does this property front a highway?") is None
        assert extract_definition_term("List all layers") is None
        assert extract_definition_term("") is None


class TestTermAppearsInChunks:
    """term_appears_in_chunks: case-insensitive substring in chunk text."""

    def test_term_present(self):
        chunks = [{"text": "The principal elevation fronts the highway."}, {"text": "Curtilage is land which forms part and parcel."}]
        assert term_appears_in_chunks("curtilage", chunks) is True
        assert term_appears_in_chunks("principal elevation", chunks) is True

    def test_term_absent(self):
        chunks = [{"text": "The principal elevation fronts the highway."}]
        assert term_appears_in_chunks("side elevation", chunks) is False
        assert term_appears_in_chunks("curtilage", chunks) is False

    def test_empty_chunks(self):
        assert term_appears_in_chunks("highway", []) is False

    def test_page_content_key(self):
        chunks = [{"page_content": "Side elevation is any wall that fronts a highway."}]
        assert term_appears_in_chunks("side elevation", chunks) is True


class TestShouldUseRetrievedForDocOnly:
    """should_use_retrieved_for_doc_only: only True when term is in chunks (or no term extracted)."""

    def test_no_chunks_false(self):
        assert should_use_retrieved_for_doc_only("What is meant by 'curtilage'?", []) is False

    def test_term_in_chunks_true(self):
        chunks = [{"text": "Curtilage means land which forms part and parcel with the house."}]
        assert should_use_retrieved_for_doc_only("What is meant by 'curtilage'?", chunks) is True

    def test_definition_of_highway_term_in_chunks_true(self):
        """'What is the definition of a highway?' extracts 'highway'; chunk contains 'highway' → use LLM."""
        chunks = [{"text": "Highway – is a public right of way."}]
        assert should_use_retrieved_for_doc_only("What is the definition of a highway?", chunks) is True

    def test_term_not_in_chunks_false(self):
        """Asked for 'side elevation' but chunks don't define it → don't call LLM."""
        chunks = [{"text": "The principal elevation fronts the highway. Permitted development applies."}]
        assert should_use_retrieved_for_doc_only("What is meant by 'side elevation'?", chunks) is False

    def test_no_term_extracted_allows_llm(self):
        """Vague question (no clear definition term) → allow LLM."""
        chunks = [{"text": "Some regulatory text."}]
        assert should_use_retrieved_for_doc_only("What are the main restrictions?", chunks) is True
