# Authentication

## Token model

- Access tokens are short-lived JWTs with `type=access`
- Refresh tokens are longer-lived JWTs with `type=refresh`
- Both token types include `sub`, `email`, `sid`, `jti`, `kid`, `iat`, and `exp` claims
- The active signing key is selected by `JWT_ACTIVE_KID`
- Additional key material can be carried in `JWT_ADDITIONAL_KEYS` for rotation

## Session model

- Each token pair is bound to a `user_sessions` document
- Sessions track the session UUID, user UUID, email, refresh token hash, refresh JTI, device name, user agent, and IP address
- `touch_session()` updates `last_seen_at`
- `revoke_session()` and `revoke_all_sessions()` deactivate sessions

## Flows

### Registration

`POST /api/v1/auth/register`

- normalizes email to lowercase
- refuses duplicate email addresses
- hashes the password with Werkzeug
- creates a new user and session
- returns access token, refresh token, session UUID, expires_in, and user data

### Login

`POST /api/v1/auth/login`

- checks the user record and password hash
- updates `last_login_at`
- creates a new session
- is rate limited

### Refresh

`POST /api/v1/auth/refresh`

- validates the refresh JWT
- rejects revoked or stale refresh tokens
- verifies the user still exists
- rotates the session’s refresh token and issues a new access token

### Logout

`POST /api/v1/auth/logout`

- validates the refresh JWT
- revokes the refresh token
- writes a session audit event

### Session management

`GET /api/v1/auth/sessions`

- lists active sessions for the current user
- supports cursor or offset pagination

`POST /api/v1/auth/sessions/revoke`

- revokes another active session for the current user
- refuses to revoke the current session through this endpoint

`POST /api/v1/auth/logout-all`

- revokes all sessions for the current user
- optionally keeps the current session active

### Admin session control

`app/api/auth_admin_routes.py` adds admin-only access to:

- list another user’s sessions
- revoke one session
- revoke all sessions
- inspect audit logs
- check config health

## Security properties

- Passwords are hashed with Werkzeug
- Refresh token revocation uses `token_blocklist` plus session deactivation
- `token_blocklist` is TTL-backed
- Multiple JWT keys are supported for rotation through `JWT_ADDITIONAL_KEYS`
- Access tokens are not individually blocklisted; their TTL is the main revocation window
