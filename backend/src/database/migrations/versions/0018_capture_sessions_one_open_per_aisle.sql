-- Sprint 2 hardening — at most one non-terminal open capture session per (inventory_id, aisle_id).
-- Aligns with count_open_sessions_for_aisle semantics (closed_at IS NULL and status not terminal).
--
-- If duplicate "open" rows already exist (e.g. race before this index, or integration test data),
-- we keep the earliest session by (created_at, id) and cancel the rest so CREATE UNIQUE INDEX succeeds.

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UQ_capture_sessions_one_open_per_aisle'
      AND object_id = OBJECT_ID('dbo.capture_sessions')
)
BEGIN
    ;WITH open_ranked AS (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY inventory_id, aisle_id
                ORDER BY created_at ASC, id ASC
            ) AS rn
        FROM dbo.capture_sessions
        WHERE closed_at IS NULL
          AND status <> 'cancelled'
          AND status <> 'failed'
          AND status <> 'confirmed'
    )
    UPDATE cs
    SET
        status = 'cancelled',
        closed_at = SYSUTCDATETIME(),
        updated_at = SYSUTCDATETIME()
    FROM dbo.capture_sessions AS cs
    INNER JOIN open_ranked AS r ON r.id = cs.id
    WHERE r.rn > 1;

    CREATE UNIQUE NONCLUSTERED INDEX UQ_capture_sessions_one_open_per_aisle
        ON dbo.capture_sessions (inventory_id, aisle_id)
        WHERE closed_at IS NULL
          AND status <> 'cancelled'
          AND status <> 'failed'
          AND status <> 'confirmed';
END;
GO
