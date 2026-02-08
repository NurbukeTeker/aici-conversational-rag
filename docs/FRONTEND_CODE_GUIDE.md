# Frontend Code Guide

Folder-level, file-by-file documentation for `frontend/src/`. All claims are derived from actual code.

---

## frontend/src/main.jsx

**Purpose:** React entry point. Renders App inside ThemeProvider and AuthProvider. Loads global styles.

**Key symbols:**
- `ReactDOM.createRoot(document.getElementById('root')).render(...)` — Mounts App with providers.

**Structure:** ThemeProvider (outer) → AuthProvider (inner) → App. Imports `./styles/index.css`.

**Callers:** Vite (via index.html script src). Callees: React, ReactDOM, App, AuthProvider, ThemeProvider, index.css.

**Edge cases / errors:** None. Assumes `#root` exists (provided by index.html).

---

## frontend/src/App.jsx

**Purpose:** Top-level routing: LoginPage when unauthenticated, Dashboard when authenticated.

**Key functions:**
- Renders loading screen (spinner + "Loading...") while `loading` from useAuth.
- Conditionally renders Dashboard or LoginPage based on `isAuthenticated`.

**Inputs/outputs:**
- Uses `useAuth()` for `isAuthenticated`, `loading`.
- Output: single div.app with either loading screen, LoginPage, or Dashboard.

**Callers:** `main.jsx`. Callees: useAuth, LoginPage, Dashboard, App.css.

**Edge cases / errors:** Loading state handled; no explicit error boundary.

**Potential refactors:** No React Router; navigation is purely auth-based. Consider adding error boundary for uncaught errors.

---

## frontend/src/context/AuthContext.jsx

**Purpose:** React Context for auth state. Stores token and user in localStorage; provides login/logout and isAuthenticated.

**Key symbols:**
- `AuthContext` — createContext(null).
- `AuthProvider` — State: user, token, loading. On mount: reads localStorage.token, localStorage.user; sets loading false.
- `login(tokenData, userData)` — Saves token and user to localStorage and state.
- `logout()` — Clears localStorage and state.
- `useAuth()` — useContext(AuthContext); throws if used outside provider.

**Inputs/outputs:**
- `login`: tokenData (string), userData (object). Stored as localStorage.token, localStorage.user (JSON).
- `logout`: no args; clears token, user from storage and state.

**Callers:** `App.jsx`, `LoginPage.jsx`, `Dashboard.jsx`. Callees: React createContext, useContext, useState, useEffect.

**Edge cases / errors:** JSON.parse on stored user; catch clears corrupted data and removes items. No token validation on load; invalid token may cause 401 on first API call.

**Potential refactors:** No token expiry check; user stays "logged in" until logout or 401. Consider validating token on mount or before use.

---

## frontend/src/context/ThemeContext.jsx

**Purpose:** React Context for light/dark theme. Persists preference in localStorage.

**Key symbols:**
- `ThemeContext` — createContext(null).
- `ThemeProvider` — State: theme (from localStorage or 'light'). Effect: sets document.documentElement attribute `data-theme` and localStorage.theme on change.
- `toggleTheme()` — Flips theme between 'light' and 'dark'.
- `useTheme()` — useContext(ThemeContext); throws if used outside provider.

**Inputs/outputs:**
- `theme`: 'light' | 'dark'.
- `toggleTheme`: no args; toggles theme.

**Callers:** `main.jsx`, `Dashboard.jsx`. Callees: React createContext, useContext, useState, useEffect.

**Edge cases / errors:** Invalid stored value defaults to 'light' (saved || 'light').

---

## frontend/src/services/api.js

**Purpose:** HTTP client for backend API. Handles auth header, error normalization, and exports API methods.

**Key symbols:**
- `API_BASE` — '/api' (relative; proxied to backend in dev/prod).
- `ApiError` — Custom Error with `status` property.
- `normalizeDetail(detail, fallback)` — Converts backend `detail` (string or array of {msg}) to display string.
- `request(endpoint, options)` — Adds Authorization Bearer from localStorage.token; returns JSON or throws ApiError.
- `authApi` — register, login, me, checkUsername, checkEmail, checkPassword.
- `sessionApi` — getObjects, updateObjects.
- `qaApi` — ask.
- `healthApi` — check.
- `exportApi` — downloadExcel, downloadJson.

**Inputs/outputs:**
- `register`: POST /auth/register, body {username, email, password}; returns UserResponse.
- `login`: POST /auth/login, form-urlencoded username/password; returns {access_token, expires_in}.
- `updateObjects`: PUT /session/objects, body {objects}; returns SessionObjectsResponse.
- `ask`: POST /qa, body {question}; returns QAResponse (answer, evidence?, session_summary?).
- `downloadExcel`, `downloadJson`: POST /export/excel or /export/json, body {dialogues, session_summary}; returns Blob.

**Callers:** `LoginPage.jsx`, `Dashboard.jsx`. Callees: fetch, localStorage.

**Edge cases / errors:** 401 → ApiError; callers may call logout(). Error detail normalized from string or array. Export uses fetch with blob response; non-JSON errors parsed as JSON may fail.

**Potential refactors:** No request timeout configuration. No retry logic. Login uses form-urlencoded; register uses JSON (backend expects OAuth2 form for login).

---

## frontend/src/pages/LoginPage.jsx

**Purpose:** Login and registration UI. Username/email availability checks, password strength, validation feedback.

**Key symbols:**
- `useDebounce(value, delay)` — Custom hook for debounced value.
- `PasswordStrength` — Renders strength bar and label.
- `ValidationFeedback` — Renders errors and warnings.
- `LoginPage` — Form with username, email (register), password, confirmPassword (register). Mode: 'login' | 'register'.

**Inputs/outputs:**
- Auth: `authApi.register`, `authApi.login`, `authApi.checkUsername`, `authApi.checkEmail`, `authApi.checkPassword`.
- On success: `login(access_token, {username, email?})` from AuthContext.

**Callers:** `App.jsx`. Callees: useAuth, authApi, useDebounce.

**Edge cases / errors:** Debounced validation for username (500ms), email (500ms), password (300ms). Register flow: validates password match, password errors, username/email availability before submit. ApiError message displayed; 401 not explicitly handled (login should succeed or show error).

**Potential refactors:** `useCallback` imported but not used. Validation logic spread across effects and submit handler.

---

## frontend/src/pages/Dashboard.jsx

**Purpose:** Main authenticated UI: JSON editor for drawing objects, Q&A panel with streaming, export buttons.

**Key symbols:**
- `getWsQaUrl()` — Builds WebSocket URL (no token in URL): `ws(s)://host/api/ws/qa`; auth sent as first message `{type:'auth',token:...}`.
- `parseAnswerNarrative(text)` — Strips evidence markers and trailing Evidence block from answer text.
- `SAMPLE_OBJECTS` — Default JSON for editor.
- `Dashboard` — JSON textarea, Update Session button, Q&A messages, Ask input, export Excel/JSON buttons, theme toggle, logout.

**Inputs/outputs:**
- Session: `sessionApi.getObjects`, `sessionApi.updateObjects`.
- QA: WebSocket (preferred) or `qaApi.ask`. WebSocket: send `{question}`, receive `{t:'chunk',c:...}` then `{t:'done',answer,session_summary}` or `{t:'error',message}`.
- Export: `exportApi.downloadExcel`, `exportApi.downloadJson` with dialogues (question, answer, timestamp) and session_summary (object_count, layer_summary).

**Callers:** `App.jsx`. Callees: useAuth, useTheme, sessionApi, qaApi, exportApi, ApiError.

**Key logic:**
- Load session on mount; if empty, use sample objects.
- JSON validation: try JSON.parse on change; set jsonValid, jsonError.
- Ask: if WebSocket open, use WS; else REST. Streaming: append chunks; human-speed reveal via interval (~35 chars/sec). Finalize on `t:done` or `t:error`.
- Export: prepareDialoguesForExport filters out streaming messages; getSessionSummary from parsed JSON.

**Edge cases / errors:** WebSocket closes on 401/credentials error → logout(). REST 401 → logout(). Export excludes streaming messages. Scroll behavior: scroll to bottom on new message or when streaming finishes if user was near bottom.

**Potential refactors:** Streaming logic is complex (refs for accumulator, display length, interval). Evidence UI not rendered; parseAnswerNarrative strips it but Dashboard never displays evidence section. `.qa-evidence` CSS exists in App.css but no corresponding JSX.

---

## frontend/src/styles/index.css

**Purpose:** Global CSS variables for light/dark theme and base styles. Theme driven by `[data-theme="light"]` and `[data-theme="dark"]`.

**Key symbols:**
- `:root`, `[data-theme="light"]` — Light theme variables (bg, surface, text, accent, border, success, error, warning, shadows).
- `[data-theme="dark"]` — Dark theme overrides.
- Base resets, fonts (Outfit, JetBrains Mono), body, #root.

**Inputs/outputs:**
- Applied globally. ThemeContext sets `data-theme` on document.documentElement.

**Callers:** `main.jsx` (import). Callees: none (CSS).

**Edge cases / errors:** Fonts loaded from Google Fonts (index.html). Fallbacks defined for font-family.

---

## frontend/src/styles/App.css

**Purpose:** Component-specific styles for layout, header, panels, JSON editor, Q&A, export, theme toggle, forms, buttons.

**Key sections:**
- `.app`, `.loading-screen` — App layout.
- `.header`, `.header-brand`, `.header-user`, `.theme-toggle`, `.btn-logout` — Header.
- `.main-content` — Two-panel layout (JSON editor, Q&A).
- `.panel`, `.panel-header`, `.panel-body`, `.panel-footer` — Panel structure.
- `.json-editor`, `.json-textarea`, `.json-status` — JSON editor.
- `.qa-panel`, `.qa-messages`, `.qa-message`, `.qa-question`, `.qa-answer`, `.qa-input-area`, `.qa-input`, `.qa-submit` — Q&A.
- `.qa-evidence`, `.qa-evidence-title`, `.qa-evidence-subtitle`, `.qa-evidence-list`, `.qa-evidence-card`, `.qa-evidence-debug` — **Evidence styles defined but not used in current Dashboard JSX.**
- `.auth-page`, `.auth-container`, `.auth-card`, `.auth-form`, `.form-group`, `.btn-primary`, `.btn-secondary` — Auth forms.
- `.spinner`, `.spinner-small` — Loading indicators.
- `.validation-error`, `.validation-warning`, `.password-strength` — Validation UI.

**Inputs/outputs:**
- Applied via `import './styles/App.css'` in App.jsx.

**Callers:** `App.jsx`. Callees: none.

**Edge cases / errors:** CSS variables from index.css. `.qa-evidence` block exists for future evidence UI but is unused.

**Potential refactors:** Evidence CSS could be removed if evidence UI is not planned, or used when evidence display is implemented. Consider CSS modules or styled-components for scoping.

---

## Unused / Legacy Notes

| Item | Location | Reason |
|------|----------|--------|
| `motion` | package.json | Dependency present but never imported in src. **Likely unused.** |
| `.qa-evidence` styles | App.css | CSS classes defined but no corresponding JSX in Dashboard. Evidence UI not implemented. |
| `healthApi` | api.js | Exported but not called anywhere in src. |

---

## Call Graph Summary

```
main.jsx
  └── ThemeProvider
        └── AuthProvider
              └── App
                    ├── LoginPage (if !isAuthenticated)
                    │     └── authApi (register, login, checkUsername, checkEmail, checkPassword)
                    └── Dashboard (if isAuthenticated)
                          ├── sessionApi (getObjects, updateObjects)
                          ├── qaApi.ask (REST fallback)
                          ├── WebSocket /api/ws/qa (streaming)
                          └── exportApi (downloadExcel, downloadJson)
```
