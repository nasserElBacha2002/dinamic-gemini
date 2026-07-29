/*
  0073_inventory_jobs_retry_of_unique.sql

  Phase 5 corrections — at most one child job per retry_of_job_id (idempotent recovery).

  Preflight / rollback / reapply: see 0073_README.md in this directory.
  Rollback: DROP INDEX IF EXISTS UX_inventory_jobs_retry_of_job_id ON dbo.inventory_jobs;
*/

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'UX_inventory_jobs_retry_of_job_id'
      AND object_id = OBJECT_ID(N'dbo.inventory_jobs')
)
BEGIN
    -- Pre-check: duplicate parents would block index creation.
    IF EXISTS (
        SELECT retry_of_job_id
        FROM dbo.inventory_jobs
        WHERE retry_of_job_id IS NOT NULL
        GROUP BY retry_of_job_id
        HAVING COUNT(*) > 1
    )
    BEGIN
        RAISERROR(
            'Cannot create UX_inventory_jobs_retry_of_job_id: duplicate retry_of_job_id rows exist',
            16,
            1
        );
        RETURN;
    END;

    CREATE UNIQUE NONCLUSTERED INDEX UX_inventory_jobs_retry_of_job_id
        ON dbo.inventory_jobs(retry_of_job_id)
        WHERE retry_of_job_id IS NOT NULL;
END;
GO
