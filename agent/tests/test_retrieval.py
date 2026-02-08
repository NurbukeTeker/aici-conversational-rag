"""Unit tests for retrieval postprocessing (dedupe + optional distance threshold)."""
import pytest
from app.rag.retrieval_postprocess import postprocess


def _chunk(id_: str, source: str, page: str | None, distance: float | None, text: str = "x"):
    return {"id": id_, "source": source, "page": page, "text": text, "distance": distance}


class TestPostprocessRetrievedChunks:
    """Dedupe by (source, page) keeping best; optional max_distance; order ascending by distance."""

    def test_same_source_page_keeps_top_two_by_distance(self):
        """Per (source, page) keep up to 2 best by distance; multiple chunks from same page survive."""
        chunks = [
            _chunk("c1", "doc.pdf", "1", 0.8),
            _chunk("c2", "doc.pdf", "1", 0.3),
            _chunk("c3", "doc.pdf", "1", 0.5),
        ]
        result = postprocess(chunks, max_distance=None)
        assert len(result) == 2
        assert result[0]["id"] == "c2" and result[0]["distance"] == 0.3
        assert result[1]["id"] == "c3" and result[1]["distance"] == 0.5

    def test_ordering_by_distance_preserved(self):
        """Final order is ascending by distance across all chunks."""
        chunks = [
            _chunk("c1", "doc.pdf", "1", 0.5),
            _chunk("c2", "doc.pdf", "1", 0.2),
            _chunk("c3", "other.pdf", "1", 0.3),
        ]
        result = postprocess(chunks, max_distance=None)
        assert [c["id"] for c in result] == ["c2", "c3", "c1"]
        assert [c["distance"] for c in result] == [0.2, 0.3, 0.5]

    def test_max_distance_filters_out_high_distance(self):
        """If max_distance is set, chunks above threshold are removed."""
        chunks = [
            _chunk("c1", "doc.pdf", "1", 0.2),
            _chunk("c2", "doc.pdf", "2", 0.9),
            _chunk("c3", "doc.pdf", "3", 1.1),
        ]
        result = postprocess(chunks, max_distance=0.5)
        assert len(result) == 1
        assert result[0]["id"] == "c1"
        assert result[0]["distance"] == 0.2

    def test_ordering_ascending_distance(self):
        """After postprocess, order is ascending by distance (most relevant first)."""
        chunks = [
            _chunk("c1", "a.pdf", "1", 0.9),
            _chunk("c2", "b.pdf", "1", 0.2),
            _chunk("c3", "c.pdf", "1", 0.5),
        ]
        result = postprocess(chunks, max_distance=None)
        assert [c["id"] for c in result] == ["c2", "c3", "c1"]
        assert [c["distance"] for c in result] == [0.2, 0.5, 0.9]

    def test_empty_returns_empty(self):
        """Empty input returns empty list."""
        assert postprocess([], max_distance=None) == []
        assert postprocess([], max_distance=0.5) == []

    def test_dedupe_different_pages_both_kept(self):
        """Different (source, page) pairs are all kept."""
        chunks = [
            _chunk("c1", "doc.pdf", "1", 0.5),
            _chunk("c2", "doc.pdf", "2", 0.3),
        ]
        result = postprocess(chunks, max_distance=None)
        assert len(result) == 2
        assert result[0]["id"] == "c2"  # lower distance first
        assert result[1]["id"] == "c1"
