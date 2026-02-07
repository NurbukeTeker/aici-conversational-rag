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

/** Normalize backend error.detail (string or array of { msg }) for display. */
function normalizeDetail(detail, fallback = 'Request failed') {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((e) => (e && e.msg) || (e && e.message) || JSON.stringify(e));
    return parts.length ? parts.join('; ') : fallback;
  }
  return detail != null ? String(detail) : fallback;
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
      message = normalizeDetail(error.detail, message);
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
        throw new ApiError(normalizeDetail(error.detail, 'Login failed'), res.status);
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

// Export API
export const exportApi = {
  /**
   * Download dialogues as Excel file
   * @param {Array} dialogues - Array of {question, answer, evidence, timestamp}
   * @param {Object} sessionSummary - Optional session context
   * @returns {Promise<Blob>} Excel file blob
   */
  downloadExcel: async (dialogues, sessionSummary = null) => {
    const token = localStorage.getItem('token');
    
    const response = await fetch(`${API_BASE}/export/excel`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify({ dialogues, session_summary: sessionSummary }),
    });
    
    if (!response.ok) {
      let message = 'Export failed';
      try {
        const error = await response.json();
        message = normalizeDetail(error.detail, message);
      } catch {
        message = response.statusText;
      }
      throw new ApiError(message, response.status);
    }
    
    return response.blob();
  },
  
  /**
   * Download dialogues as JSON file
   * @param {Array} dialogues - Array of {question, answer, evidence, timestamp}
   * @param {Object} sessionSummary - Optional session context
   * @returns {Promise<Blob>} JSON file blob
   */
  downloadJson: async (dialogues, sessionSummary = null) => {
    const token = localStorage.getItem('token');
    
    const response = await fetch(`${API_BASE}/export/json`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify({ dialogues, session_summary: sessionSummary }),
    });
    
    if (!response.ok) {
      let message = 'Export failed';
      try {
        const error = await response.json();
        message = normalizeDetail(error.detail, message);
      } catch {
        message = response.statusText;
      }
      throw new ApiError(message, response.status);
    }
    
    return response.blob();
  },
};

export { ApiError };
