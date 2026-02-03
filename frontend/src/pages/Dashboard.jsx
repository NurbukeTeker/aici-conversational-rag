import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { sessionApi, qaApi, ApiError } from '../services/api';

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

  // Load session objects on mount
  useEffect(() => {
    loadSessionObjects();
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

    try {
      const response = await qaApi.ask(currentQuestion);
      
      setMessages(prev => [...prev, {
        id: Date.now(),
        question: currentQuestion,
        answer: response.answer,
        evidence: response.evidence,
        sessionSummary: response.session_summary
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        id: Date.now(),
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
              /* Moon icon - click to switch to night */
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
              </svg>
            ) : (
              /* Sun icon - click to switch to day */
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z" />
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
                      <div className="qa-answer-text">{msg.answer}</div>
                      
                      {msg.evidence && (
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
              
              {asking && (
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
