import { useState } from 'react';

/**
 * Collapsible Sources Panel for Q&A answers
 * Shows document sources and drawing layers used, collapsed by default
 */
function SourcesPanel({ evidence, sessionSummary }) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Extract sources from evidence
  const documentSources = evidence?.document_chunks || [];
  const layersUsed = evidence?.session_objects?.layers_used || [];
  const objectIndices = evidence?.session_objects?.object_indices || [];
  
  // Check if we have any content to show
  const hasSources = documentSources.length > 0;
  const hasLayers = layersUsed.length > 0;
  const hasContent = hasSources || hasLayers;
  
  // Generate a note if no sources were used
  const getNote = () => {
    if (!hasSources && !hasLayers) {
      return "No specific document rules or drawing elements were referenced for this response.";
    }
    return null;
  };
  
  const note = getNote();
  
  // If there's absolutely nothing to show, render minimal indicator
  if (!hasContent && !note) {
    return null;
  }
  
  return (
    <div className="sources-panel">
      <button 
        className="sources-toggle"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
      >
        <span className="sources-toggle-icon">{isExpanded ? '▾' : '▸'}</span>
        <span className="sources-toggle-text">Sources & details</span>
        {hasContent && (
          <span className="sources-count">
            {hasSources && `${documentSources.length} doc${documentSources.length !== 1 ? 's' : ''}`}
            {hasSources && hasLayers && ' · '}
            {hasLayers && `${layersUsed.length} layer${layersUsed.length !== 1 ? 's' : ''}`}
          </span>
        )}
      </button>
      
      {isExpanded && (
        <div className="sources-content">
          {/* Document Sources */}
          {hasSources && (
            <div className="sources-section">
              <div className="sources-section-title">📄 Document sources</div>
              <div className="sources-list">
                {documentSources.map((chunk, i) => (
                  <div key={i} className="source-item">
                    <span className="source-file">{chunk.source}</span>
                    <span className="source-meta">
                      {chunk.page && `p${chunk.page}`}
                      {chunk.section && chunk.section !== 'general' && ` · ${chunk.section}`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {/* Drawing Layers */}
          {hasLayers && (
            <div className="sources-section">
              <div className="sources-section-title">🏗️ Drawing elements considered</div>
              <div className="sources-layers">
                {layersUsed.map((layer, i) => (
                  <span key={i} className="layer-chip">{layer}</span>
                ))}
              </div>
              {objectIndices.length > 0 && (
                <div className="sources-meta">
                  {objectIndices.length} object{objectIndices.length !== 1 ? 's' : ''} referenced
                </div>
              )}
            </div>
          )}
          
          {/* Note for no sources */}
          {note && !hasSources && !hasLayers && (
            <div className="sources-note">
              <span className="sources-note-icon">ℹ️</span>
              {note}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default SourcesPanel;
