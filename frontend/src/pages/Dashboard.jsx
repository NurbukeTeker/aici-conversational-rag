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


/**
 * Parse LLM answer: keep only the narrative; remove Evidence section and everything after.
 * Evidence is shown in the dedicated Evidence panel from API.
 */
function parseAnswerNarrative(text) {
  if (!text || typeof text !== 'string') return text ?? '';
  const lower = text.toLowerCase();
  // Find start of Evidence block (take earliest match)
  const patterns = [
    '**evidence**',
    '\nevidence:',
    '\nevidence\n',
    '\n**document excerpts used:**',
    '\ndocument excerpts used:',
    '\n**json objects/layers used:**',
    '\njson objects/layers used:',
  ];
  let cut = -1;
  for (const p of patterns) {
    const i = lower.indexOf(p);
    if (i >= 0 && (cut < 0 || i < cut)) cut = i;
  }
  if (cut >= 0) text = text.slice(0, cut);
  // Strip trailing Evidence markers
  text = text.replace(/\s*\*\*Evidence\s*\*\*:?\s*$/gim, '').trim();
  return text.trim();
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
  const [streamingDisplayLength, setStreamingDisplayLength] = useState(0); // human-speed reveal (chars shown so far)
  const streamingAnswerRef = useRef('');
  const streamingIntervalRef = useRef(null);
  const currentStreamingMsgIdRef = useRef(null); // so we can finalize when typing catches up
  const wsRef = useRef(null);
  const [wsReady, setWsReady] = useState(false);
  const qaMessagesRef = useRef(null);
  const isNearBottomRef = useRef(true);
  const lastMessageRef = useRef(null);
  const prevMessagesLengthRef = useRef(0);
  const prevLastWasStreamingRef = useRef(false);
  const SCROLL_THRESHOLD_PX = 80;
  
  // Export state
  const [exportingExcel, setExportingExcel] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);
  const [exportMessage, setExportMessage] = useState(null);

  // Collapsible evidence: Set of message ids where evidence is collapsed
  const [collapsedEvidenceIds, setCollapsedEvidenceIds] = useState(() => new Set());
  const toggleEvidence = (msgId) => {
    setCollapsedEvidenceIds(prev => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

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

  // Auto-scroll to bottom when new content appears, only if user is already near bottom
  const handleQaMessagesScroll = () => {
    const el = qaMessagesRef.current;
    if (!el) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    isNearBottomRef.current = scrollHeight - scrollTop - clientHeight <= SCROLL_THRESHOLD_PX;
  };

  // Scroll to latest when: new question added, or last answer completes (evidence appears)
  useEffect(() => {
    const el = qaMessagesRef.current;
    if (!el || messages.length === 0) return;

    const len = messages.length;
    const lastMsg = messages[len - 1];
    const isNewMessage = len > prevMessagesLengthRef.current;
    const lastWasStreaming = prevLastWasStreamingRef.current;
    const lastJustFinished = lastWasStreaming && !lastMsg?.streaming;

    if (isNewMessage || lastJustFinished) {
      // New question or answer just completed — scroll to bottom to show latest content
      isNearBottomRef.current = true;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          el.scrollTop = el.scrollHeight - el.clientHeight;
        });
      });
    }

    prevMessagesLengthRef.current = len;
    prevLastWasStreamingRef.current = !!lastMsg?.streaming;
  }, [messages]);

  // During streaming: keep scrolling to bottom if user is following along
  useEffect(() => {
    if (!qaMessagesRef.current || !isNearBottomRef.current) return;
    const el = qaMessagesRef.current;
    el.scrollTop = el.scrollHeight - el.clientHeight;
  }, [messages, streamingAnswer]);

  // Human-speed typing: reveal streaming answer character by character (~35 chars/sec)
  const STREAMING_CHAR_MS = 28;
  useEffect(() => {
    streamingAnswerRef.current = streamingAnswer;
    if (!streamingAnswer) {
      setStreamingDisplayLength(0);
      if (streamingIntervalRef.current) clearInterval(streamingIntervalRef.current);
      streamingIntervalRef.current = null;
      return;
    }
    streamingIntervalRef.current = setInterval(() => {
      setStreamingDisplayLength((prev) => {
        const target = streamingAnswerRef.current.length;
        if (prev >= target) {
          if (streamingIntervalRef.current) {
            clearInterval(streamingIntervalRef.current);
            streamingIntervalRef.current = null;
          }
          // Typing finished — finalize so message shows as complete and evidence can appear (defer to avoid batching issues)
          const mid = currentStreamingMsgIdRef.current;
          if (mid != null) {
            currentStreamingMsgIdRef.current = null;
            queueMicrotask(() => {
              setMessages(prevMsgs => prevMsgs.map(m => (m.id === mid ? { ...m, streaming: false } : m)));
              setStreamingAnswer('');
              setStreamingDisplayLength(0);
            });
          }
          return prev;
        }
        return prev + 1;
      });
    }, STREAMING_CHAR_MS);
    return () => {
      if (streamingIntervalRef.current) clearInterval(streamingIntervalRef.current);
      streamingIntervalRef.current = null;
    };
  }, [streamingAnswer]);

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
      currentStreamingMsgIdRef.current = msgId;
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
            // Keep streaming: true and keep streamingAnswer — typing continues until animation catches up
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? {
                    ...m,
                    answer: data.answer ?? '',
                    evidence: data.evidence ?? null,
                    sessionSummary: data.session_summary ?? null,
                    streaming: true
                  }
                : m
            ));
            setAsking(false);
          } else if (data.t === 'error') {
            ws.removeEventListener('message', handler);
            const msg = (data.message || '').toLowerCase();
            if (msg.includes('credentials') || msg.includes('unauthorized')) {
              logout();
              return;
            }
            currentStreamingMsgIdRef.current = null;
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

    // Fallback: REST — add message row first so "Thinking..." appears where the answer will be
    currentStreamingMsgIdRef.current = msgId;
    setMessages(prev => [...prev, {
      id: msgId,
      question: currentQuestion,
      answer: '',
      evidence: null,
      sessionSummary: null,
      streaming: true
    }]);
    try {
      const response = await qaApi.ask(currentQuestion);
      // Keep streaming: true and feed answer into typing effect so it types out like WebSocket
      setMessages(prev => prev.map(m =>
        m.id === msgId
          ? {
              ...m,
              answer: response.answer,
              evidence: response.evidence,
              sessionSummary: response.session_summary,
              streaming: true
            }
          : m
      ));
      setStreamingAnswer(response.answer || '');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        return;
      }
      currentStreamingMsgIdRef.current = null;
      setMessages(prev => prev.map(m =>
        m.id === msgId
          ? { ...m, answer: `Error: ${err instanceof ApiError ? err.message : 'Failed to get answer'}`, evidence: null, streaming: false }
          : m
      ));
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
            <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
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
                {jsonValid ? 'Valid JSON' : `Invalid: ${jsonError}`}
              </div>
              <button
                className="btn-primary"
                onClick={handleSaveSession}
                disabled={!jsonValid || saving}
              >
                {saving ? 'Saving...' : sessionSaved ? 'Saved' : 'Update Session'}
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
            <div
              ref={qaMessagesRef}
              className="qa-messages"
              onScroll={handleQaMessagesScroll}
            >
              {messages.length === 0 ? (
                <div className="qa-empty">
                  <div className="qa-empty-icon" aria-hidden>Q&A</div>
                  <p>Ask questions about your drawing and planning regulations.</p>
                  <p style={{ fontSize: '0.85rem', marginTop: '0.5rem' }}>
                    Example: "Does this property front a highway?"
                  </p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div
                    key={msg.id}
                    ref={idx === messages.length - 1 ? lastMessageRef : undefined}
                    className="qa-message"
                  >
                    <div className="qa-question">
                      <div className="qa-question-label">Question</div>
                      <div>{msg.question}</div>
                    </div>
                    <div className="qa-answer">
                      <div className="qa-answer-text">
                        {msg.streaming ? (
                          !streamingAnswer ? (
                            <span className="qa-thinking" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                              <span className="spinner" />
                              <span>Thinking...</span>
                            </span>
                          ) : (
                            <>
                              {parseAnswerNarrative(streamingAnswer.slice(0, streamingDisplayLength))}
                              <span className="qa-streaming-cursor">▌</span>
                            </>
                          )
                        ) : (
                          parseAnswerNarrative(msg.answer)
                        )}
                      </div>

                      {msg.evidence && !msg.streaming && (msg.evidence.document_chunks?.length > 0 || msg.evidence.session_objects) && (
                        <div className="qa-evidence">
                          <div
                            className="qa-evidence-title"
                            role="button"
                            tabIndex={0}
                            onClick={() => toggleEvidence(msg.id)}
                            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleEvidence(msg.id); } }}
                            aria-expanded={!collapsedEvidenceIds.has(msg.id)}
                          >
                            <span className="qa-evidence-chevron" aria-hidden>
                              {collapsedEvidenceIds.has(msg.id) ? '▶' : '▼'}
                            </span>
                            <strong>Evidence:</strong>
                          </div>
                          {!collapsedEvidenceIds.has(msg.id) && (
                            <>
                          {msg.evidence.document_chunks?.length > 0 && (
                            <>
                              <div className="qa-evidence-subtitle"><strong>Document Excerpts Used:</strong></div>
                              <ul className="qa-evidence-list">
                                {msg.evidence.document_chunks.map((chunk, i) => (
                                  <li key={i} className="qa-evidence-item">
                                    [{chunk.chunk_id || chunk.source} | p{chunk.page || '?'}]: {chunk.text_snippet || `${chunk.section || 'general'}`}
                                  </li>
                                ))}
                              </ul>
                            </>
                          )}
                          {msg.evidence.session_objects && (() => {
                            const so = msg.evidence.session_objects;
                            const labels = so.object_labels || [];
                            const indices = so.object_indices || [];
                            const layers = so.layers_used || [];
                            const byLayer = {};
                            layers.forEach((layer, i) => {
                              if (!byLayer[layer]) byLayer[layer] = { indices: [], labels: [] };
                              byLayer[layer].indices.push(indices[i]);
                              byLayer[layer].labels.push(labels[i]);
                            });
                            return (
                              <>
                                <div className="qa-evidence-subtitle"><strong>JSON Objects/Layers Used:</strong></div>
                                <ul className="qa-evidence-list">
                                  {Object.entries(byLayer).map(([layer, { indices: idxs, labels: lbs }]) => {
                                    const indexStr = idxs.length <= 2
                                      ? idxs.join(' and ')
                                      : idxs.slice(0, -1).join(', ') + ' and ' + idxs[idxs.length - 1];
                                    const labelPart = lbs.some(Boolean)
                                      ? ` (for ${lbs.filter(Boolean).map((l) => `"${l}"`).join(' and ')})`
                                      : '';
                                    return (
                                      <li key={layer} className="qa-evidence-item">
                                        {layer} layer, indices {indexStr}{labelPart}.
                                      </li>
                                    );
                                  })}
                                </ul>
                              </>
                            );
                          })()}
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            <form className="qa-input-area" onSubmit={handleAskQuestion}>
              <input
                type="text"
                className="qa-input"
                placeholder="Ask about planning regulations..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={asking || messages.some(m => m.streaming)}
              />
              <button
                type="submit"
                className="btn-primary qa-submit"
                disabled={!question.trim() || asking || messages.some(m => m.streaming)}
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
