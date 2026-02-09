"""Export service for dialogue export to CSV."""
import io
import csv
from typing import Optional


class ExportService:
    """Service for exporting Q&A dialogues to CSV format."""
    
    @staticmethod
    def create_dialogue_csv(
        dialogues: list[dict],
        username: str,
        session_summary: Optional[dict] = None
    ) -> bytes:
        """
        Create a CSV file from Q&A dialogues.
        
        Args:
            dialogues: List of Q&A pairs with format:
                [{"question": str, "answer": str, "evidence": dict, "timestamp": str}, ...]
            username: Username for the export
            session_summary: Optional session context (layer summary, etc.)
        
        Returns:
            CSV file as bytes
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header row
        headers = ["#", "Question", "Answer", "Document Evidence", "Session Context", "Timestamp"]
        writer.writerow(headers)
        
        # Write data rows
        for idx, dialogue in enumerate(dialogues, 1):
            # Format evidence
            evidence_text = ""
            if dialogue.get("evidence"):
                ev = dialogue["evidence"]
                if ev.get("document_chunks"):
                    chunks = ev["document_chunks"][:5]  # Max 5 chunks
                    evidence_text = "; ".join([
                        f"{c.get('source', 'Unknown')} (p{c.get('page', '?')}) - {c.get('section', 'general')}"
                        for c in chunks
                    ])
            
            # Format session context
            session_text = ""
            if dialogue.get("evidence", {}).get("session_objects"):
                so = dialogue["evidence"]["session_objects"]
                parts = []
                if so.get("layers_used"):
                    parts.append(f"Layers: {', '.join(so['layers_used'])}")
                if so.get("objects_count"):
                    parts.append(f"Objects: {so['objects_count']}")
                session_text = "; ".join(parts)
            
            # Write row (ensure all values are strings, handle None values, escape newlines)
            question = str(dialogue.get("question", "") or "").replace('\n', ' ').replace('\r', ' ')
            answer = str(dialogue.get("answer", "") or "").replace('\n', ' ').replace('\r', ' ')
            timestamp = str(dialogue.get("timestamp", "") or "")
            
            row_data = [
                idx,
                question,
                answer,
                evidence_text or "",
                session_text or "",
                timestamp
            ]
            writer.writerow(row_data)
        
        # Convert to bytes
        csv_string = output.getvalue()
        output.close()
        return csv_string.encode('utf-8-sig')  # UTF-8 with BOM for Excel compatibility


# Singleton instance
_export_service: Optional[ExportService] = None


def get_export_service() -> ExportService:
    """Get or create export service instance."""
    global _export_service
    if _export_service is None:
        _export_service = ExportService()
    return _export_service
