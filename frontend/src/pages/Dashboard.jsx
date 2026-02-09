import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { sessionApi, qaApi, exportApi, ApiError } from '../services/api';

// WebSocket URL for real-time streaming Q&A (no token in URL — sent in first message to avoid logs)
function getWsQaUrl() {
  const token = localStorage.getItem('token');
  if (!token) return null;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  return `${protocol}//${host}/api/ws/qa`;
}


/**
 * Parse LLM answer: keep only the narrative; remove any Evidence section or trailing boilerplate.
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
  // Strip trailing Evidence markers and the old "Evidence section below" line
  text = text.replace(/\s*\*\*Evidence\s*\*\*:?\s*$/gim, '').trim();
  text = text.replace(/\s*Relevant documents and JSON layers used are listed in the Evidence section below\.?\s*$/gi, '').trim();
  return text.trim();
}

const ALLOWED_OBJECT_KEYS = new Set(['type', 'layer', 'geometry', 'properties']);
const VALID_TYPES = new Set(['LINE', 'POLYLINE', 'POLYGON', 'POINT', 'CIRCLE', 'ARC', 'TEXT', 'BLOCK']);

/** Validate drawing objects: required keys (type, layer), no extra keys, valid type values. */
function validateSessionSchema(objects) {
  if (!Array.isArray(objects)) return { valid: false, message: 'Session must be a JSON array.' };
  for (let i = 0; i < objects.length; i++) {
    const obj = objects[i];
    if (obj === null || typeof obj !== 'object') {
      return { valid: false, message: `Object at index ${i} must be an object.` };
    }
    const keys = Object.keys(obj);
    const invalidKeys = keys.filter((k) => !ALLOWED_OBJECT_KEYS.has(k));
    if (invalidKeys.length) {
      return {
        valid: false,
        message: `Object at index ${i}: invalid key(s) ${invalidKeys.map((k) => `"${k}"`).join(', ')}. Allowed keys only: type, layer, geometry, properties.`,
      };
    }
    const typeVal = obj.type;
    if (typeVal == null || String(typeVal).trim() === '') {
      return { valid: false, message: `Object at index ${i} is missing or empty "type". Each drawing object must have "type".` };
    }
    // Validate type value matches backend expectations
    const typeUpper = String(typeVal).toUpperCase();
    if (!VALID_TYPES.has(typeUpper)) {
      return {
        valid: false,
        message: `Object at index ${i}: invalid type "${typeVal}". Must be one of: ${Array.from(VALID_TYPES).join(', ')}`,
      };
    }
    const layerVal = obj.layer;
    if (layerVal == null || String(layerVal).trim() === '') {
      return { valid: false, message: `Object at index ${i} is missing or empty "layer". Each drawing object must have "layer".` };
    }
  }
  return { valid: true };
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
  const [schemaError, setSchemaError] = useState(null); // e.g. missing "layer" in an object
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
  const streamedTextAccumulatorRef = useRef(''); // exact streamed text so "done" doesn't overwrite with shorter answer
  const wsRef = useRef(null);
  const [wsReady, setWsReady] = useState(false);
  const qaMessagesRef = useRef(null);
  const isNearBottomRef = useRef(true);
  const lastMessageRef = useRef(null);
  const prevMessagesLengthRef = useRef(0);
  const prevLastWasStreamingRef = useRef(false);
  const SCROLL_THRESHOLD_PX = 80;
  
  // Export state
  const [exportingCsv, setExportingCsv] = useState(false);
  const [exportingJson, setExportingJson] = useState(false);
  const [exportMessage, setExportMessage] = useState(null);

  // Load session objects on mount
  useEffect(() => {
    loadSessionObjects();
  }, []);

  // WebSocket for real-time streaming: connect on mount when token exists; auth via first message (token not in URL)
  useEffect(() => {
    const url = getWsQaUrl();
    const token = localStorage.getItem('token');
    if (!url || !token) return;
    const ws = new WebSocket(url);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token }));
      setWsReady(true);
    };
    ws.onclose = (event) => {
      setWsReady(false);
      if (event.code === 4001) logout(); // auth failed, redirect to login
    };
    ws.onerror = () => setWsReady(false);
    wsRef.current = ws;
    return () => {
      ws.close();
      wsRef.current = null;
      setWsReady(false);
    };
  }, [logout]);

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
        const objects = response.objects;
        setJsonText(JSON.stringify(objects, null, 2));
        const schema = validateSessionSchema(objects);
        setSchemaError(schema.valid ? null : schema.message);
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
    setJsonError(''); // Clear backend errors when user edits JSON

    try {
      const parsed = JSON.parse(text);
      setJsonValid(true);
      const schema = validateSessionSchema(Array.isArray(parsed) ? parsed : []);
      setSchemaError(schema.valid ? null : schema.message);
    } catch (err) {
      setJsonValid(false);
      setJsonError(err.message);
      setSchemaError(null);
    }
  };

  const handleSaveSession = async () => {
    if (!jsonValid) return;
    const objects = JSON.parse(jsonText);
    const schema = validateSessionSchema(Array.isArray(objects) ? objects : []);
    if (!schema.valid) {
      setSchemaError(schema.message);
      setJsonError(''); // Clear any previous backend errors
      return;
    }
    setSchemaError(null);
    setJsonError(''); // Clear previous errors before attempting save
    setSaving(true);
    try {
      await sessionApi.updateObjects(objects);
      setSessionSaved(true);
      setJsonError(''); // Clear errors on success
    } catch (err) {
      if (err instanceof ApiError) {
        setJsonError(err.message);
      } else {
        setJsonError(err.message || 'Failed to update session');
      }
      setSessionSaved(false);
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
      streamedTextAccumulatorRef.current = '';
      setStreamingAnswer('');
      setMessages(prev => [...prev, {
        id: msgId,
        question: currentQuestion,
        answer: '',
        sessionSummary: null,
        streaming: true
      }]);
      const handler = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.t === 'chunk') {
            const c = data.c || '';
            streamedTextAccumulatorRef.current += c;
            setStreamingAnswer(prev => prev + c);
          } else if (data.t === 'done') {
            ws.removeEventListener('message', handler);
            const doneAnswer = data.answer ?? '';
            const streamedSoFar = streamedTextAccumulatorRef.current;
            const finalAnswer = streamedSoFar.length >= doneAnswer.length ? streamedSoFar : doneAnswer;
            setStreamingAnswer(prev => (finalAnswer.length > prev.length ? finalAnswer : prev));
            setMessages(prev => prev.map(m =>
              m.id === msgId
                ? { ...m, answer: finalAnswer, sessionSummary: data.session_summary ?? null, streaming: true }
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
                ? { ...m, answer: `Error: ${data.message || 'Stream failed'}`, streaming: false }
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
      sessionSummary: null,
      streaming: true
    }]);
    try {
      const response = await qaApi.ask(currentQuestion);
      setMessages(prev => prev.map(m =>
        m.id === msgId
          ? { ...m, answer: response.answer, sessionSummary: response.session_summary, streaming: true }
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
          ? { ...m, answer: `Error: ${err instanceof ApiError ? err.message : 'Failed to get answer'}`, streaming: false }
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

  // Handle CSV download
  const handleDownloadCsv = async () => {
    if (messages.length === 0) return;
    
    setExportingCsv(true);
    setExportMessage(null);
    
    try {
      const dialogues = prepareDialoguesForExport();
      const sessionSummary = getSessionSummary();
      
      const blob = await exportApi.downloadCsv(dialogues, sessionSummary);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `AICI_QA_Export_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      setExportMessage({ type: 'success', text: 'CSV downloaded!' });
    } catch (err) {
      setExportMessage({ 
        type: 'error', 
        text: err instanceof ApiError ? err.message : 'Download failed'
      });
    } finally {
      setExportingCsv(false);
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
              <div className={`json-status ${jsonValid && !schemaError && !jsonError ? 'valid' : 'invalid'}`}>
                {!jsonValid
                  ? `Invalid JSON: ${jsonError}`
                  : jsonError
                    ? jsonError
                    : schemaError
                      ? schemaError + ' Update session not applied.'
                      : 'Valid JSON'}
              </div>
              <button
                className="btn-primary"
                onClick={handleSaveSession}
                disabled={!jsonValid || !!schemaError || !!jsonError || saving}
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
                  onClick={handleDownloadCsv}
                  disabled={exportingCsv}
                  title="Download as CSV"
                >
                  {exportingCsv ? (
                    <span className="spinner-small" />
                  ) : (
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
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
