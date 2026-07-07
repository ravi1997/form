# JWT Key Rotation Runbook

This runbook describes zero-downtime JWT signing key rotation.

## Terminology

- Active key: used to sign new tokens (`JWT_SECRET_KEY` + `JWT_ACTIVE_KID`)
- Additional keys: accepted only for verification (`JWT_ADDITIONAL_KEYS`)

Token behavior:

- New access/refresh tokens are issued with `kid` claim and header from `JWT_ACTIVE_KID`.
- Verification supports active key plus additional keys.

## Environment Variables

- `JWT_SECRET_KEY` (active signing secret)
- `JWT_ACTIVE_KID` (active key version, for example `v2`)
- `JWT_ADDITIONAL_KEYS` (comma list, for example `v1:old-secret,v0:older-secret`)

## Rotation Procedure (No Downtime)

1. Prepare new key material

- Generate new secret securely.
- Choose next key id, for example `v2`.

2. Deploy verification overlap

- Keep current active key unchanged.
- Add new key to `JWT_ADDITIONAL_KEYS` temporarily if needed for staged rollout validation.

3. Switch signing key

- Set:
  - `JWT_ACTIVE_KID=v2`
  - `JWT_SECRET_KEY=<new-secret>`
- Move old key into `JWT_ADDITIONAL_KEYS` as `v1:<old-secret>`.

4. Observe and validate

- Confirm startup snapshot/logs show expected `jwt_active_kid`.
- Check `/api/v1/auth/admin/config/health` returns expected:
  - `jwt_active_kid`
  - `jwt_additional_key_ids`

5. Drain old tokens

- Wait at least refresh token TTL (`JWT_REFRESH_TOKEN_EXPIRES_DAYS`) plus buffer.

6. Retire old key

- Remove old key from `JWT_ADDITIONAL_KEYS`.

## Rollback

If issues occur after key switch:

- Revert `JWT_ACTIVE_KID` and `JWT_SECRET_KEY` to previous values.
- Keep both keys in `JWT_ADDITIONAL_KEYS` during rollback window.

## Security Notes

- Never log raw secrets.
- Store secrets in a dedicated secret manager.
- Rotate keys periodically and on incident response triggers.
