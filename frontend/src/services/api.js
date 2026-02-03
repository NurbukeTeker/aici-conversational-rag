/**
 * API Service for AICI Backend
 */

const API_BASE = '/api';

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(endpoint, options = {}) {
  const token = localStorage.getItem('token');
  
  const config = {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
  };

  const response = await fetch(`${API_BASE}${endpoint}`, config);
  
  if (!response.ok) {
    let message = 'Request failed';
    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      message = response.statusText;
    }
    throw new ApiError(message, response.status);
  }

  return response.json();
}

// Auth API
export const authApi = {
  register: (username, email, password) =>
    request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    }),

  login: (username, password) => {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);
    
    return fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const error = await res.json();
        throw new ApiError(error.detail || 'Login failed', res.status);
      }
      return res.json();
    });
  },
  
  // Get current user info
  me: () => request('/auth/me'),
  
  // Check username availability
  checkUsername: (username) =>
    request(`/auth/check-username?username=${encodeURIComponent(username)}`),
  
  // Check email availability
  checkEmail: (email) =>
    request(`/auth/check-email?email=${encodeURIComponent(email)}`),
  
  // Check password strength
  checkPassword: (password) =>
    request('/auth/check-password', {
      method: 'POST',
      body: JSON.stringify(password),
    }),
};

// Session API
export const sessionApi = {
  getObjects: () => request('/session/objects'),

  updateObjects: (objects) =>
    request('/session/objects', {
      method: 'PUT',
      body: JSON.stringify({ objects }),
    }),
};

// QA API
export const qaApi = {
  ask: (question) =>
    request('/qa', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),
};

// Health API
export const healthApi = {
  check: () => request('/health'),
};

export { ApiError };
