"""Guards: doc_only_guard, geometry_guard."""

from .doc_only_guard import (
    extract_definition_term,
    term_appears_in_chunks,
    should_use_retrieved_for_doc_only,
)
from .geometry_guard import (
    should_trigger_geometry_guard,
    required_layers_for_question,
    missing_geometry_layers,
    is_spatial_question,
    has_geometry,
)

__all__ = [
    "extract_definition_term",
    "term_appears_in_chunks",
    "should_use_retrieved_for_doc_only",
    "should_trigger_geometry_guard",
    "required_layers_for_question",
    "missing_geometry_layers",
    "is_spatial_question",
    "has_geometry",
]
