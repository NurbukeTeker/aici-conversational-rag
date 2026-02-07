"""Tests for prompt formatting."""
import pytest
from app.prompts import (
    format_chunk,
    format_retrieved_chunks,
    build_user_prompt,
    build_user_prompt_doc_only,
)


class TestPromptFormatting:
    """Test cases for prompt formatting functions."""
    
    def test_format_chunk_with_all_fields(self):
        """Test chunk formatting with all metadata."""
        result = format_chunk(
            chunk_id="class_a_001",
            source="permitted_development.pdf",
            page="14",
            section="Class A",
            text="Extensions must not exceed 4 metres."
        )
        
        assert "[DOC: permitted_development.pdf | p14 | chunk: class_a_001 | Class A]" in result
        assert "Extensions must not exceed 4 metres." in result
    
    def test_format_chunk_without_section(self):
        """Test chunk formatting without section."""
        result = format_chunk(
            chunk_id="intro_001",
            source="document.pdf",
            page="1",
            section=None,
            text="Introduction text."
        )
        
        assert "[DOC: document.pdf | p1 | chunk: intro_001]" in result
        assert "Introduction text." in result
    
    def test_format_chunk_without_page(self):
        """Test chunk formatting without page number."""
        result = format_chunk(
            chunk_id="chunk_001",
            source="document.pdf",
            page=None,
            section="Section 1",
            text="Some text."
        )
        
        assert "p?" in result
    
    def test_format_retrieved_chunks_empty(self):
        """Test formatting with no chunks."""
        result = format_retrieved_chunks([])
        
        assert result == "No relevant excerpts found."
    
    def test_format_retrieved_chunks_multiple(self):
        """Test formatting with multiple chunks."""
        chunks = [
            {"id": "chunk_1", "source": "doc1.pdf", "page": "1", "section": "A", "text": "Text 1"},
            {"id": "chunk_2", "source": "doc2.pdf", "page": "2", "section": "B", "text": "Text 2"},
        ]
        
        result = format_retrieved_chunks(chunks)
        
        assert "chunk_1" in result
        assert "chunk_2" in result
        assert "doc1.pdf" in result
        assert "doc2.pdf" in result
    
    def test_build_user_prompt_complete(self):
        """Test complete user prompt building."""
        prompt = build_user_prompt(
            question="What are the rules for extensions?",
            json_objects=[{"layer": "Walls", "type": "line"}],
            session_summary={
                "layer_counts": {"Walls": 1},
                "plot_boundary_present": False,
                "highways_present": False,
                "limitations": ["No plot boundary defined"]
            },
            retrieved_chunks=[
                {"id": "c1", "source": "doc.pdf", "page": "5", "section": "Class A", "text": "Rule text"}
            ]
        )
        
        assert "What are the rules for extensions?" in prompt
        assert '"layer": "Walls"' in prompt
        assert "Walls=1" in prompt
        assert "Plot boundary present: False" in prompt
        assert "No plot boundary defined" in prompt
        assert "Rule text" in prompt


class TestPromptCompositionDocOnlyVsHybrid:
    """Doc-only prompt must not contain JSON/session summary; non-doc-only unchanged."""

    def test_doc_only_prompt_no_json_or_session_summary(self):
        """For doc_only, generated prompt must NOT contain JSON/session summary markers."""
        prompt = build_user_prompt_doc_only(
            question="What is a highway?",
            retrieved_chunks=[
                {"id": "c1", "source": "doc.pdf", "page": "5", "section": None, "text": "A highway is..."}
            ],
        )
        assert "What is a highway?" in prompt
        assert "A highway is..." in prompt
        # Must not contain hybrid-only content
        assert "Session drawing" not in prompt
        assert "json_objects" not in prompt
        assert "layer_counts" not in prompt
        assert "Layer counts" not in prompt
        assert "plot_boundary_present" not in prompt
        assert "highways_present" not in prompt

    def test_non_doc_only_prompt_unchanged(self):
        """For non-doc_only, existing build_user_prompt remains unchanged (has JSON + summary)."""
        prompt = build_user_prompt(
            question="Does this property front a highway?",
            json_objects=[{"layer": "Highway", "type": "line"}],
            session_summary={
                "layer_counts": {"Highway": 1},
                "plot_boundary_present": True,
                "highways_present": True,
                "limitations": [],
            },
            retrieved_chunks=[{"id": "c1", "source": "doc.pdf", "page": "1", "section": None, "text": "Highway means..."}],
        )
        assert "Does this property front a highway?" in prompt
        assert "Session drawing objects" in prompt
        assert "layer_counts" in prompt or "Layer counts" in prompt
        assert "Highway=1" in prompt
        assert "Highway means..." in prompt
