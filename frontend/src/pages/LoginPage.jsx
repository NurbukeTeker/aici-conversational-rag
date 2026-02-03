import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { authApi, ApiError } from '../services/api';

function LoginPage() {
  const { login } = useAuth();
  const [mode, setMode] = useState('login'); // 'login' or 'register'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
  });

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

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
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
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
              onClick={() => { setMode('login'); setError(''); }}
            >
              Sign In
            </button>
            <button
              className={`auth-tab ${mode === 'register' ? 'active' : ''}`}
              onClick={() => { setMode('register'); setError(''); }}
            >
              Register
            </button>
          </div>

          {error && <div className="message error">{error}</div>}

          <form className="auth-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                type="text"
                id="username"
                name="username"
                value={formData.username}
                onChange={handleChange}
                placeholder="Enter username"
                required
                autoComplete="username"
              />
            </div>

            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="email">Email</label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  placeholder="Enter email"
                  required
                  autoComplete="email"
                />
              </div>
            )}

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                type="password"
                id="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                placeholder="Enter password"
                required
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              />
            </div>

            <button
              type="submit"
              className="btn-primary auth-submit w-full"
              disabled={loading}
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
        </div>
      </div>
    </div>
  );
}

export default LoginPage;
