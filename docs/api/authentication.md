# Authentication

## Token model

- Access tokens are short-lived JWTs used in `Authorization: Bearer ...`
- Refresh tokens are used to create new token pairs
- Sessions are stored in MongoDB and tied to the issued token pair

## Flows

- `POST /api/v1/auth/register` creates a user and initial session
- `POST /api/v1/auth/login` authenticates an existing user and creates a session
- `POST /api/v1/auth/refresh` rotates refresh tokens and returns a new access token
- `POST /api/v1/auth/logout` revokes a refresh token and deactivates the session

## Security properties

- Passwords are hashed with Werkzeug
- Refresh token revocation uses MongoDB-backed session state and blocklisting
- Multiple JWT keys are supported for rotation through `JWT_ADDITIONAL_KEYS`
