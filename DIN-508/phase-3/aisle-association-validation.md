# Aisle association validation

Covered by `backend/tests/unit/live_stream/test_channel_identity.py`:

- Same aisle code case variants → same slug.
- Different codes → different slugs.
- Same code, different inventories → isolated slugs.
- Parity with `infrastructure/din-508-mediamtx/scripts/channel_id.py`.

`LiveStreamAisleChannelResolver` optionally links `aisle_id` when SQL row exists; channel path does not require aisle row.