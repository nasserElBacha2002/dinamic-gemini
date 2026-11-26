# Public access security validation

- Public API: `GET /api/public/live/{token}` — no JWT; returns playback ticket only (no inventory metadata).
- Tokens stored as SHA-256 hash; plaintext token only in URL path.
- Grant expiry and revocation enforced in use case and MediaMTX auth (view user).
- Residual window: HLS clients may play buffered segments after revoke until playlist refresh (~segment cache; not measured in CI).