# Backend Code Guide

Folder-level, file-by-file documentation for `backend/app/`. All claims are derived from actual code.

---

## backend/app/__init__.py

**Purpose:** Package marker. Contains only a docstring describing the service.

**Key symbols:** None (no executable code).

**Callers:** Python package loader.

---

## backend/app/config.py

**Purpose:** Centralizes backend configuration via Pydantic Settings loaded from environment variables.

**Key classes/functions:**
- `Settings` — BaseSettings subclass with JWT, Redis, DB, Agent URL, session TTL, password/username policy fields.
- `get_settings()` — Cached settings instance (lru_cache).

**Inputs/outputs:**
- Inputs: Environment variables, `.env` file.
- Outputs: `Settings` instance with defaults (e.g. `jwt_secret_key="change-this-secret-key-in-production"`, `session_ttl_seconds=3600`).

**Callers:** `auth.py`, `session.py`, `database.py`, `main.py`, `validators.py`.

**Edge cases / errors:** Config ignores extra env vars (`extra="ignore"`). Missing required values use defaults.

**Potential refactors:** Consider validating `JWT_SECRET_KEY` length or strength in production; `session_ttl_seconds` not exposed in env.example (uses default).

---

## backend/app/database.py

**Purpose:** SQLAlchemy engine, User ORM model, and database session factory for auth/user persistence.

**Key classes/functions:**
- `Base` — Declarative base for ORM.
- `User` — SQLAlchemy model: id (UUID), username, email, hashed_password, display_name, is_active, is_verified, created_at, updated_at, last_login_at. Indexes on email/username.
- `DatabaseService` — Creates engine, sessionmaker, calls `create_all`. `get_session()` returns a new session.
- `get_database()` — Singleton factory.
- `get_db_session()` — Generator dependency; yields session and closes on exit.

**Inputs/outputs:**
- Inputs: `DATABASE_URL` (e.g. `sqlite:////data/users.db`).
- Outputs: Session instances for CRUD.

**Callers:** `main.py` (via `get_db_session`), `user_service.py` (receives session from main).

**Edge cases / errors:** SQLite `check_same_thread=False` set for async compatibility. Path in `DATABASE_URL` is created with `mkdir(parents=True, exist_ok=True)` before engine init.

**Potential refactors:** Single global `_db_service`; consider dependency injection for tests. No migration tooling (Alembic); schema changes require manual handling.

---

## backend/app/auth.py

**Purpose:** JWT creation/validation and Argon2 password hashing for authentication.

**Key classes/functions:**
- `pwd_context` — CryptContext(schemes=["argon2"]).
- `verify_password(plain_password, hashed_password)` — Returns bool.
- `get_password_hash(password)` — Returns Argon2 hash string.
- `create_access_token(data, expires_delta)` — Builds JWT with `sub`, `user_id`, `exp`; HS256.
- `decode_token(token)` — Validates JWT, returns `TokenData(username, user_id)`; raises HTTPException 401 on invalid/missing.
- `get_current_user(token)` — FastAPI dependency; calls `decode_token`.

**Inputs/outputs:**
- `create_access_token`: `data={"sub": username, "user_id": id}`; outputs JWT string.
- `decode_token`: JWT string; outputs `TokenData`.

**Callers:** `main.py` (create_access_token, get_current_user, decode_token), `user_service.py` (get_password_hash, verify_password).

**Edge cases / errors:** JWT decode failures raise HTTPException 401. Missing `sub` in payload raises 401.

**Potential refactors:** `decode_token` raises HTTPException; consider separating decode logic from HTTP for reuse (e.g. WebSocket). No refresh token support.

---

## backend/app/session.py

**Purpose:** Redis-backed session storage for user drawing objects. Keys and metadata stored with TTL.

**Key classes/functions:**
- `SessionService` — Manages Redis connection. Methods: `set_objects`, `get_objects`, `delete_session`, `is_connected`.
- `_get_objects_key(user_id)` — Returns `session:{user_id}:objects`.
- `_get_meta_key(user_id)` — Returns `session:{user_id}:meta`.
- `get_session_service()` — Singleton factory.

**Inputs/outputs:**
- `set_objects(user_id, objects)` — Stores JSON-serialized list; meta: `{updated_at, object_count}`. TTL applied to both keys.
- `get_objects(user_id)` — Returns `(list[dict], dict | None)` (objects, meta). Returns `([], None)` on exception.

**Callers:** `main.py` (update_session_objects, get_session_objects, ask_question, websocket_qa, health_check).

**Edge cases / errors:** On Redis errors, `set_objects` returns False; `get_objects` returns `([], None)`. Logs errors. TTL refreshed on every `set_objects` call.

**Potential refactors:** No retry logic for transient Redis failures. Consider connection pooling for high concurrency.

---

## backend/app/models.py

**Purpose:** Pydantic request/response models for API validation and serialization.

**Key classes:**
- `ErrorDetail`, `ErrorResponse` — Error response format.
- `UserRegister`, `UserLogin`, `Token`, `TokenData`, `UserResponse` — Auth models.
- `PasswordStrengthResponse`, `AvailabilityResponse` — Validation endpoints.
- `DrawingObject`, `SessionObjects`, `SessionObjectsResponse` — Session models.
- `QARequest`, `QAResponse` — QA endpoint. `QAResponse` requires `evidence: Evidence` (agent does not return it; see Doc vs Code Mismatches).
- `ChunkEvidence`, `ObjectEvidence`, `Evidence`, `SessionSummary` — Evidence structure.
- `HealthResponse`, `DialogueItem`, `ExportRequest` — Health and export.

**Constants:** `MAX_OBJECTS_COUNT=1000`, `MAX_PAYLOAD_SIZE_KB=512`, `MAX_STRING_LENGTH=500`, `MAX_NESTING_DEPTH=5`, `EXAMPLE_DRAWING_OBJECTS`.

**Inputs/outputs:**
- `SessionObjects`: `{objects: [DrawingObject]}` with max 1000, validation on type/layer/geometry/properties.
- `QARequest`: `{question: str}`.
- `QAResponse`: `{answer, evidence, session_summary}` — evidence required but agent omits it.

**Callers:** `main.py` (all endpoints), `auth.py` (TokenData), `export_service.py` (implicit via dicts).

**Edge cases / errors:** DrawingObject validates `type` in allowed set; `properties` depth limited to 5. Session objects max 1000.

**Potential refactors:** Make `QAResponse.evidence` optional or add backend-side evidence construction to align with agent response. Consider splitting models into separate modules by domain.

---

## backend/app/user_service.py

**Purpose:** User CRUD, validation, and authentication. Persists users via SQLAlchemy.

**Key classes/functions:**
- `UserAlreadyExistsError`, `UserNotFoundError`, `ValidationError` — Custom exceptions.
- `UserService` — Methods: `create_user`, `get_by_username`, `get_by_email`, `get_by_id`, `authenticate`, `update_password`, `check_username_available`, `check_email_available`, `validate_password_strength`.
- `get_user_service(db_session)` — Factory.

**Inputs/outputs:**
- `create_user`: username, email, password, display_name; outputs `User`. Raises ValidationError, UserAlreadyExistsError.
- `authenticate`: username_or_email, password; outputs `User | None`.
- `check_username_available`, `check_email_available`: (available: bool, message: str | None).

**Callers:** `main.py` (register, login, get_current_user_info, check_username, check_email).

**Edge cases / errors:** Username/email lookups case-insensitive (ilike). IntegrityError on create_user triggers rollback and re-raises UserAlreadyExistsError. Inactive users fail authenticate.

**Potential refactors:** `last_login_at` updated in authenticate but no separate login-history table. Email normalizer in EmailValidator used; consider centralizing.

---

## backend/app/validators.py

**Purpose:** Password, username, and email validation with configurable rules. Used at registration and for availability checks.

**Key classes/functions:**
- `ValidationResult` — Dataclass: is_valid, errors, warnings.
- `PasswordValidator` — validate(), get_strength(). Checks length, uppercase, lowercase, digit, special, common passwords, sequential/repeated chars.
- `UsernameValidator` — validate(). Pattern, length, consecutive underscores, reserved words.
- `EmailValidator` — validate(), normalize(). RFC-style pattern, plus-addressing, disposable domains, typo warnings.
- `_create_validators_from_config()` — Wires validators to config.
- `validate_registration(username, email, password)` — Combined validation; returns ValidationResult.

**Inputs/outputs:**
- `validate`: string input; outputs `ValidationResult`.
- `get_strength(password)`: outputs `(score: 0-100, label: str)`.
- Module-level: `password_validator`, `username_validator`, `email_validator`.

**Callers:** `user_service.py` (password_validator, username_validator, email_validator). `validate_registration` used only in tests.

**Edge cases / errors:** Common passwords and sequential/repeated chars produce errors or warnings. Email typo detection (e.g. gmial.com) adds warnings.

**Potential refactors:** `validate_registration` exists but `user_service.create_user` calls validators individually; could use `validate_registration` for consistency. Validators created at import time; config changes require restart.

---

## backend/app/export_service.py

**Purpose:** Generates Excel and structured data for Q&A dialogue export. Excel via openpyxl.

**Key classes/functions:**
- `ExportService` — `create_dialogue_excel(dialogues, username, session_summary)` returns bytes.
- `get_export_service()` — Singleton factory.

**Inputs/outputs:**
- `create_dialogue_excel`: dialogues = list of `{question, answer, evidence?, timestamp}`; session_summary = optional `{object_count, layer_summary}`. Output: .xlsx bytes.

**Callers:** `main.py` (download_dialogue_excel). JSON export built inline in main.py.

**Edge cases / errors:** Handles missing evidence/empty lists. Evidence format: `document_chunks`, `session_objects` with `layers_used`, `object_indices`. Up to 5 document chunks in Excel.

**Potential refactors:** JSON export logic lives in main.py; could move to ExportService for consistency. Excel styles and layout are hardcoded.

---

## backend/app/main.py

**Purpose:** FastAPI application entry. Defines routes, exception handlers, lifespan, middleware (CORS, request size limit).

**Key functions:**
- `validation_exception_handler` — 422 with field details; includes example for session errors.
- `json_decode_exception_handler` — 400 for invalid JSON.
- `RequestSizeLimitMiddleware` — Rejects requests > 512 KB (413).
- `compute_layer_summary(objects)` — Counter of layer names.
- `validate_objects_warnings(objects)` — Non-fatal warnings (no objects, no geometry, no plot boundary).
- `lifespan` — Initializes session_service, database.

**Endpoints:**
- Auth: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `GET /auth/check-username`, `GET /auth/check-email`, `POST /auth/check-password`.
- Session: `PUT /session/objects`, `GET /session/objects`.
- QA: `POST /qa` (REST), `WebSocket /ws/qa` (streaming).
- Health: `GET /health`.
- Export: `POST /export/excel`, `POST /export/json`.
- Root: `GET /`.

**Inputs/outputs:**
- `/qa`: Forwards `{question, session_objects}` to agent `/answer`; returns `QAResponse(**agent_response)`. Agent does not return evidence; this may cause validation failure.
- WebSocket: Authenticates via `?token=<jwt>`; forwards NDJSON stream from agent `/answer/stream`.

**Callers:** Uvicorn (`app.main:app`). Callees: config, models, auth, session, database, user_service, validators, export_service.

**Edge cases / errors:** 401 on invalid/missing token. 502 on agent non-200. 503 on agent request failure. WebSocket closes with 4001 on auth failure. Payload > 512 KB returns 413.

**Potential refactors:** QA endpoint assumes agent returns evidence; add fallback or make evidence optional. Consider extracting route groups into routers.
