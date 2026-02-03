import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { authApi, ApiError } from '../services/api';

// Debounce hook for validation
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  
  return debouncedValue;
}

// Password strength indicator component
function PasswordStrength({ password, strength }) {
  if (!password) return null;
  
  const getColor = () => {
    switch (strength?.strength) {
      case 'Very Weak': return '#ef4444';
      case 'Weak': return '#f97316';
      case 'Fair': return '#eab308';
      case 'Strong': return '#22c55e';
      case 'Very Strong': return '#10b981';
      default: return '#6b7280';
    }
  };
  
  const getWidth = () => `${strength?.score || 0}%`;
  
  return (
    <div className="password-strength">
      <div className="password-strength-bar">
        <div 
          className="password-strength-fill" 
          style={{ width: getWidth(), backgroundColor: getColor() }}
        />
      </div>
      <span className="password-strength-label" style={{ color: getColor() }}>
        {strength?.strength || 'Checking...'}
      </span>
    </div>
  );
}

// Validation feedback component
function ValidationFeedback({ errors, warnings }) {
  if (!errors?.length && !warnings?.length) return null;
  
  return (
    <div className="validation-feedback">
      {errors?.map((error, i) => (
        <div key={`error-${i}`} className="validation-error">
          <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <span>{error}</span>
        </div>
      ))}
      {warnings?.map((warning, i) => (
        <div key={`warning-${i}`} className="validation-warning">
          <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          <span>{warning}</span>
        </div>
      ))}
    </div>
  );
}

function LoginPage() {
  const { login } = useAuth();
  const [mode, setMode] = useState('login'); // 'login' or 'register'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Form data
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  
  // Password visibility
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  // Validation state
  const [validation, setValidation] = useState({
    username: { checking: false, available: null, message: null },
    email: { checking: false, available: null, message: null },
    password: { strength: null, errors: [], warnings: [] },
  });
  
  // Debounced values for async validation
  const debouncedUsername = useDebounce(formData.username, 500);
  const debouncedEmail = useDebounce(formData.email, 500);
  const debouncedPassword = useDebounce(formData.password, 300);
  
  // Check username availability
  useEffect(() => {
    if (mode !== 'register' || !debouncedUsername || debouncedUsername.length < 3) {
      setValidation(v => ({ ...v, username: { checking: false, available: null, message: null } }));
      return;
    }
    
    setValidation(v => ({ ...v, username: { ...v.username, checking: true } }));
    
    authApi.checkUsername(debouncedUsername)
      .then(result => {
        setValidation(v => ({
          ...v,
          username: { checking: false, available: result.available, message: result.message }
        }));
      })
      .catch(() => {
        setValidation(v => ({ ...v, username: { checking: false, available: null, message: null } }));
      });
  }, [debouncedUsername, mode]);
  
  // Check email availability
  useEffect(() => {
    if (mode !== 'register' || !debouncedEmail || !debouncedEmail.includes('@')) {
      setValidation(v => ({ ...v, email: { checking: false, available: null, message: null } }));
      return;
    }
    
    setValidation(v => ({ ...v, email: { ...v.email, checking: true } }));
    
    authApi.checkEmail(debouncedEmail)
      .then(result => {
        setValidation(v => ({
          ...v,
          email: { checking: false, available: result.available, message: result.message }
        }));
      })
      .catch(() => {
        setValidation(v => ({ ...v, email: { checking: false, available: null, message: null } }));
      });
  }, [debouncedEmail, mode]);
  
  // Check password strength
  useEffect(() => {
    if (mode !== 'register' || !debouncedPassword) {
      setValidation(v => ({ ...v, password: { strength: null, errors: [], warnings: [] } }));
      return;
    }
    
    authApi.checkPassword(debouncedPassword)
      .then(result => {
        setValidation(v => ({
          ...v,
          password: {
            strength: { score: result.score, strength: result.strength },
            errors: result.errors,
            warnings: result.warnings
          }
        }));
      })
      .catch(() => {
        // Fallback to basic validation
        setValidation(v => ({
          ...v,
          password: {
            strength: debouncedPassword.length >= 8 ? { score: 40, strength: 'Fair' } : { score: 10, strength: 'Weak' },
            errors: debouncedPassword.length < 8 ? ['Password must be at least 8 characters'] : [],
            warnings: []
          }
        }));
      });
  }, [debouncedPassword, mode]);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Client-side validation for registration
    if (mode === 'register') {
      if (formData.password !== formData.confirmPassword) {
        setError('Passwords do not match');
        setLoading(false);
        return;
      }
      
      if (validation.password.errors?.length > 0) {
        setError('Please fix password issues before continuing');
        setLoading(false);
        return;
      }
      
      if (validation.username.available === false) {
        setError('Username is not available');
        setLoading(false);
        return;
      }
      
      if (validation.email.available === false) {
        setError('Email is already registered');
        setLoading(false);
        return;
      }
    }

    try {
      if (mode === 'register') {
        // Register then login
        await authApi.register(formData.username, formData.email, formData.password);
        const { access_token } = await authApi.login(formData.username, formData.password);
        login(access_token, { username: formData.username, email: formData.email });
      } else {
        // Just login
        const { access_token } = await authApi.login(formData.username, formData.password);
        login(access_token, { username: formData.username });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = (newMode) => {
    setMode(newMode);
    setError('');
    setFormData({ username: '', email: '', password: '', confirmPassword: '' });
    setValidation({
      username: { checking: false, available: null, message: null },
      email: { checking: false, available: null, message: null },
      password: { strength: null, errors: [], warnings: [] },
    });
  };

  const renderFieldStatus = (field) => {
    const v = validation[field];
    if (!v) return null;
    
    if (v.checking) {
      return <span className="field-status checking">Checking...</span>;
    }
    
    if (v.available === true) {
      return <span className="field-status available">✓ Available</span>;
    }
    
    if (v.available === false) {
      return <span className="field-status unavailable">✗ {v.message || 'Not available'}</span>;
    }
    
    return null;
  };

  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-card">
          <div className="auth-header">
            <div className="auth-logo">AI</div>
            <h1 className="auth-title">AICI</h1>
            <p className="auth-subtitle">Planning Document Q&A System</p>
          </div>

          <div className="auth-tabs">
            <button
              className={`auth-tab ${mode === 'login' ? 'active' : ''}`}
              onClick={() => toggleMode('login')}
            >
              Sign In
            </button>
            <button
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => toggleMode('register')}
            >
              Register
            </button>
          </div>

          {error && <div className="message error">{error}</div>}

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username">
                {mode === 'login' ? 'Username or Email' : 'Username'}
              </label>
              <div className="input-wrapper">
                <input
                  type="text"
                  id="username"
                  name="username"
                  value={formData.username}
                  onChange={handleChange}
                  placeholder={mode === 'login' ? 'Enter username or email' : 'e.g. john_doe123'}
                  required
                  autoComplete="username"
                  className={mode === 'register' && (validation.username.available === false || (formData.username && !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(formData.username))) ? 'input-error' : ''}
                />
                {mode === 'register' && renderFieldStatus('username')}
              </div>
              {mode === 'register' && formData.username && !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(formData.username) && (
                <div className="validation-error" style={{ marginTop: '0.5rem' }}>
                  <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                  <span>Username must start with a letter and contain only letters, numbers, and underscores</span>
                </div>
              )}
              {mode === 'register' && formData.username && /^[a-zA-Z][a-zA-Z0-9_]*$/.test(formData.username) && formData.username.length < 3 && (
                <div className="field-hint">Username must be at least 3 characters</div>
              )}
              {mode === 'register' && !formData.username && (
                <div className="field-hint">Not your email! Choose a unique username (e.g. john_doe)</div>
              )}
            </div>

            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="email">Email</label>
                <div className="input-wrapper">
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="e.g. you@example.com"
                    required
                    autoComplete="email"
                    className={validation.email.available === false || (formData.email && !formData.email.includes('@')) ? 'input-error' : ''}
                  />
                  {renderFieldStatus('email')}
                </div>
                {formData.email && !formData.email.includes('@') && (
                  <div className="validation-error" style={{ marginTop: '0.5rem' }}>
                    <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <span>Please enter a valid email address</span>
                  </div>
                )}
                {validation.email.available === false && (
                  <div className="validation-error" style={{ marginTop: '0.5rem' }}>
                    <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <span>{validation.email.message || 'This email is already registered'}</span>
                  </div>
                )}
                {!formData.email && (
                  <div className="field-hint">We'll never share your email with anyone</div>
                )}
              </div>
            )}

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <div className="password-input-wrapper">
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder={mode === 'register' ? 'Min 8 chars with A-Z, a-z, 0-9, !@#' : 'Enter password'}
                  required
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                  className={mode === 'register' && validation.password.errors?.length > 0 ? 'input-error' : ''}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
              {mode === 'register' && formData.password && (
                <>
                  <PasswordStrength 
                    password={formData.password} 
                    strength={validation.password.strength} 
                  />
                  <ValidationFeedback 
                    errors={validation.password.errors}
                    warnings={validation.password.warnings}
                  />
                </>
              )}
              {mode === 'register' && !formData.password && (
                <div className="field-hint">Use uppercase, lowercase, numbers, and special characters</div>
              )}
            </div>

            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="confirmPassword">Confirm Password</label>
                <div className="password-input-wrapper">
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    placeholder="Confirm your password"
                    required
                    autoComplete="new-password"
                    className={formData.confirmPassword && formData.password !== formData.confirmPassword ? 'input-error' : ''}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
                  >
                    {showConfirmPassword ? (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" />
                        <line x1="1" y1="1" x2="23" y2="23" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </div>
                {formData.confirmPassword && formData.password !== formData.confirmPassword && (
                  <div className="validation-error" style={{ marginTop: '0.5rem' }}>
                    <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                    </svg>
                    <span>Passwords do not match</span>
                  </div>
                )}
                {formData.confirmPassword && formData.password === formData.confirmPassword && (
                  <div className="validation-success" style={{ marginTop: '0.5rem' }}>
                    <svg className="validation-icon" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Passwords match</span>
                  </div>
                )}
                {!formData.confirmPassword && (
                  <div className="field-hint">Re-enter your password to confirm</div>
                )}
              </div>
            )}

            <button
              type="submit"
              className="btn-primary auth-submit w-full"
              disabled={loading || (mode === 'register' && (
                validation.username.available === false ||
                validation.email.available === false ||
                (validation.password.errors?.length > 0) ||
                formData.password !== formData.confirmPassword ||
                !formData.username ||
                !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(formData.username) ||
                formData.username.length < 3 ||
                !formData.email ||
                !formData.email.includes('@') ||
                !formData.password ||
                !formData.confirmPassword
              ))}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-1">
                  <span className="spinner" />
                  {mode === 'register' ? 'Creating Account...' : 'Signing In...'}
                </span>
              ) : (
                mode === 'register' ? 'Create Account' : 'Sign In'
              )}
            </button>
          </form>
          
          {mode === 'register' && (
            <div className="auth-footer">
              <p className="password-requirements">
                Password must be at least 8 characters with uppercase, lowercase, number, and special character.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
