import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { sessionApi, qaApi, exportApi, ApiError } from '../services/api';

// WebSocket URL for real-time streaming Q&A (proxied in dev to backend)
function getWsQaUrl() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/api/ws/qa?token=${encodeURIComponent(token)}`;
}

// Sample drawing objects from the specification
const SAMPLE_OBJECTS = [
  { "layer": "Highway", "type": "line", "properties": { "name": "Main Road", "width": 6 } },
  { "layer": "Highway", "type": "line", "properties": { "name": "Side Street", "width": 4 } },
  { "layer": "Plot Boundary", "type": "polygon", "properties": { "area": 450 } },
  { "layer": "Walls", "type": "line", "properties": { "material": "brick", "height": 2.4 } },
  { "layer": "Walls", "type": "line", "properties": { "material": "brick", "height": 2.4 } },
  { "layer": "Doors", "type": "point", "properties": { "width": 0.9, "type": "entrance" } },
  { "layer": "Windows", "type": "point", "properties": { "width": 1.2, "height": 1.0 } }
];

function Dashboard() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [jsonText, setJsonText] = useState(JSON.stringify(SAMPLE_OBJECTS, null, 2));
  const [jsonValid, setJsonValid] = useState(true);
  const [jsonError, setJsonError] = useState('');
  const [sessionSaved, setSessionSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState(''); // current streaming text for live update
  const wsRef = useRef(null);
  const [wsReady, setWsReady] = useState(false);
  
  // Export state
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);
  const [exportMessage, setExportMessage] = useState(null);

  // Load session objects on mount
  useEffect(() => {
    loadSessionObjects();
  }, []);

  // WebSocket for real-time streaming: connect on mount when token exists
  useEffect(() => {
    const url = getWsQaUrl();
    if (!url) return;
    const ws = new WebSocket(url);
    ws.onopen = () => setWsReady(true);
    ws.onclose = () => setWsReady(false);
    ws.onerror = () => setWsReady(false);
    wsRef.current = ws;
    return () => {
      ws.close();
      wsRef.current = null;
      setWsReady(false);
    };
  }, []);

  const loadSessionObjects = async () => {
    try {
      const response = await sessionApi.getObjects();
      if (response.objects && response.objects.length > 0) {
        setJsonText(JSON.stringify(response.objects, null, 2));
        setSessionSaved(true);
      }
    } catch (err) {
      // Session might be empty, use sample data
      console.log('No existing session, using sample data');
    }
  };

  const handleJsonChange = (e) => {
    const text = e.target.value;
    setJsonText(text);
    setSessionSaved(false);
    
    try {
      JSON.parse(text);
      setJsonValid(true);
      setJsonError('');
    } catch (err) {
      setJsonValid(false);
      setJsonError(err.message);
    }
  };

  const handleSaveSession = async () => {
    if (!jsonValid) return;
    
    setSaving(true);
    try {
      const objects = JSON.parse(jsonText);
      await sessionApi.updateObjects(objects);
      setSessionSaved(true);
    } catch (err) {
      if (err instanceof ApiError) {
        setJsonError(err.message);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleAskQuestion = async (e) => {
    e.preventDefault();
    if (!question.trim() || asking) return;

    // Save session first if not saved
    if (!sessionSaved && jsonValid) {
      await handleSaveSession();
    }

    setAsking(true);
    const currentQuestion = question;
    setQuestion('');
    const msgId = Date.now();

    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Real-time path: stream via WebSocket
      setStreamingAnswer('');
      setMessages(prev => [...prev, {
        id: msgId,
        question: currentQuestion,
        answer: '',
        evidence: null,
        sessionSummary: null,
        streaming: true
      }]);
      const handler = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.t === 'chunk') {
            setStreamingAnswer(prev => prev + (data.c || ''));
          } else if (data.t === 'done') {
            ws.removeEventListener('message', handler);
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? {
                    ...m,
                    answer: data.answer ?? '',
                    evidence: data.evidence ?? null,
                    sessionSummary: data.session_summary ?? null,
                    streaming: false
                  }
                : m
            ));
            setStreamingAnswer('');
            setAsking(false);
          } else if (data.t === 'error') {
            ws.removeEventListener('message', handler);
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? { ...m, answer: `Error: ${data.message || 'Stream failed'}`, evidence: null, streaming: false }
                : m
            ));
            setStreamingAnswer('');
            setAsking(false);
          }
        } catch (err) {
          // ignore parse errors
        }
      };
      ws.addEventListener('message', handler);
      ws.send(JSON.stringify({ question: currentQuestion }));
      return;
    }

    // Fallback: REST
    try {
      const response = await qaApi.ask(currentQuestion);
      setMessages(prev => [...prev, {
        id: msgId,
        question: currentQuestion,
        answer: response.answer,
        evidence: response.evidence,
        sessionSummary: response.session_summary
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: msgId,
        question: currentQuestion,
        answer: `Error: ${err instanceof ApiError ? err.message : 'Failed to get answer'}`,
        evidence: null
      }]);
    } finally {
      setAsking(false);
    }
  };

  const getObjectCount = () => {
    try {
      const objects = JSON.parse(jsonText);
      return Array.isArray(objects) ? objects.length : 0;
    } catch {
      return 0;
    }
  };

  // Prepare dialogues for export (exclude messages still streaming)
  const prepareDialoguesForExport = () => {
    return messages
      .filter(msg => !msg.streaming)
      .map(msg => ({
      question: msg.question,
      answer: msg.answer,
      evidence: msg.evidence || null,
      timestamp: new Date(msg.id).toISOString()
    }));
  };

  // Get session summary for export
  const getSessionSummary = () => {
    try {
      const objects = JSON.parse(jsonText);
      if (!Array.isArray(objects)) return null;
      
      const layerSummary = {};
      objects.forEach(obj => {
        const layer = obj.layer || 'Unknown';
        layerSummary[layer] = (layerSummary[layer] || 0) + 1;
      });
      
      return {
        object_count: objects.length,
        layer_summary: layerSummary
      };
    } catch {
      return null;
    }
  };

  // Handle Excel download
  const handleDownloadExcel = async () => {
    if (messages.length === 0) return;
    
    setExportingExcel(true);
    setExportMessage(null);
    
    try {
      const dialogues = prepareDialoguesForExport();
      const sessionSummary = getSessionSummary();
      
      const blob = await exportApi.downloadExcel(dialogues, sessionSummary);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AICI_QA_Export_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      setExportMessage({ type: 'success', text: 'Excel downloaded!' });
    } catch (err) {
      setExportMessage({ 
        type: 'error', 
        text: err instanceof ApiError ? err.message : 'Download failed'
      });
    } finally {
      setExportingExcel(false);
      setTimeout(() => setExportMessage(null), 3000);
    }
  };

  // Handle JSON download
  const handleDownloadJson = async () => {
    if (messages.length === 0) return;
    
    setExportingJson(true);
    setExportMessage(null);
    
    try {
      const dialogues = prepareDialoguesForExport();
      const sessionSummary = getSessionSummary();
      
      const blob = await exportApi.downloadJson(dialogues, sessionSummary);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AICI_QA_Export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      setExportMessage({ type: 'success', text: 'JSON downloaded!' });
    } catch (err) {
      setExportMessage({ 
        type: 'error', 
        text: err instanceof ApiError ? err.message : 'Download failed'
      });
    } finally {
      setExportingJson(false);
      setTimeout(() => setExportMessage(null), 3000);
    }
  };

  return (
    <>
      <header className="header">
        <div className="header-brand">
          <div className="header-logo">AI</div>
          <div>
            <div className="header-title">AICI</div>
            <div className="header-subtitle">Planning Document Q&A</div>
          </div>
        </div>
        <div className="header-user">
          <span className="header-username">{user?.username || 'User'}</span>
          <button 
            className="theme-toggle" 
            onClick={toggleTheme}
            title={theme === 'light' ? 'Switch to night mode' : 'Switch to day mode'}
            aria-label={theme === 'light' ? 'Switch to night mode' : 'Switch to day mode'}
          >
            {theme === 'light' ? (
              <svg className="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg className="theme-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            )}
          </button>
          <button className="btn-secondary btn-logout" onClick={logout}>
            Logout
          </button>
        </div>
      </header>

      <main className="main-content">
        {/* JSON Editor Panel */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <svg className="panel-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              Drawing Objects (JSON)
            </div>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {getObjectCount()} objects
            </span>
          </div>
          
          <div className="panel-body json-editor">
            <textarea
              className="json-textarea"
              value={jsonText}
              onChange={handleJsonChange}
              spellCheck={false}
            />
          </div>
          
          <div className="panel-footer">
            <div className="flex justify-between items-center">
              <div className={`json-status ${jsonValid ? 'valid' : 'invalid'}`}>
                {jsonValid ? '✓ Valid JSON' : `✗ ${jsonError}`}
              </div>
              <button
                className="btn-primary"
                onClick={handleSaveSession}
                disabled={!jsonValid || saving}
              >
                {saving ? 'Saving...' : sessionSaved ? '✓ Saved' : 'Update Session'}
              </button>
            </div>
          </div>
        </div>

        {/* Q&A Panel */}
        <div className="panel">
          <div className="panel-header">
            <div className="panel-title">
              <svg className="panel-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
              Q&A
            </div>
            
            {/* Export Buttons */}
            {messages.length > 0 && (
              <div className="export-buttons">
                <button
                  className="btn-icon"
                  onClick={handleDownloadExcel}
                  disabled={exportingExcel}
                  title="Download as Excel"
                >
                  {exportingExcel ? (
                    <span className="spinner-small" />
                  ) : (
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  )}
                </button>
                <button
                  className="btn-icon"
                  onClick={handleDownloadJson}
                  disabled={exportingJson}
                  title="Download as JSON"
                >
                  {exportingJson ? (
                    <span className="spinner-small" />
                  ) : (
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                  )}
                </button>
                
                {exportMessage && (
                  <span className={`export-message ${exportMessage.type}`}>
                    {exportMessage.text}
                  </span>
                )}
              </div>
            )}
          </div>
          
          <div className="panel-body qa-panel">
            <div className="qa-messages">
              {messages.length === 0 ? (
                <div className="qa-empty">
                  <div className="qa-empty-icon">💬</div>
                  <p>Ask questions about your drawing and planning regulations.</p>
                  <p style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
                    Example: "Does this property front a highway?"
                  </p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div key={msg.id} className="qa-message">
                    <div className="qa-question">
                      <div className="qa-question-label">Question</div>
                      <div>{msg.question}</div>
                    </div>
                    <div className="qa-answer">
                      <div className="qa-answer-text">
                        {msg.streaming ? streamingAnswer : msg.answer}
                        {msg.streaming && !streamingAnswer && <span className="qa-streaming-cursor">▌</span>}
                      </div>
                      
                      {msg.evidence && !msg.streaming && (
                        <div className="qa-evidence">
                          <div className="qa-evidence-title">Evidence</div>
                          {msg.evidence.document_chunks?.length > 0 && (
                            <div>
                              {msg.evidence.document_chunks.slice(0, 3).map((chunk, i) => (
                                <div key={i} className="qa-evidence-item">
                                  📄 {chunk.source} (p{chunk.page || '?'}) - {chunk.section || 'general'}
                                </div>
                              ))}
                            </div>
                          )}
                          {msg.evidence.session_objects && (
                            <div className="qa-evidence-item">
                              🏠 Layers: {msg.evidence.session_objects.layers_used.join(', ')}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              
              {asking && !messages.some(m => m.streaming) && (
                <div className="qa-message">
                  <div className="qa-answer" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span className="spinner" />
                    <span>Thinking...</span>
                  </div>
                </div>
              )}
            </div>

            <form className="qa-input-area" onSubmit={handleAskQuestion}>
              <input
                type="text"
                className="qa-input"
                placeholder="Ask about planning regulations..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={asking}
              />
              <button
                type="submit"
                className="btn-primary qa-submit"
                disabled={!question.trim() || asking}
              >
                Ask
              </button>
            </form>
          </div>
        </div>
      </main>
    </>
  );
}

export default Dashboard;
