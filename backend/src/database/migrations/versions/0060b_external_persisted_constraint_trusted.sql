-- Phase 6/7 correction: trust PERSISTED integrity constraint after diagnosing inconsistent rows.
-- Additive / idempotent. Does not drop data.

IF OBJECT_ID('external_image_analysis_requests', 'U') IS NULL
BEGIN
    PRINT '0060b: external_image_analysis_requests missing — skip';
END
ELSE
BEGIN
    -- Diagnose inconsistent PERSISTED rows (no position/active result).
    IF OBJECT_ID('tempdb..#eiar_persisted_inconsistent') IS NOT NULL
        DROP TABLE #eiar_persisted_inconsistent;

    SELECT id, job_id, asset_id, status, position_id, active_result_id
    INTO #eiar_persisted_inconsistent
    FROM external_image_analysis_requests
    WHERE status = 'PERSISTED'
      AND position_id IS NULL
      AND active_result_id IS NULL;

    DECLARE @inconsistent INT = (SELECT COUNT(1) FROM #eiar_persisted_inconsistent);
    IF @inconsistent > 0
    BEGIN
        -- Soft-reconcile: mark as PERSISTENCE_PENDING so recovery can finish without losing evidence.
        UPDATE external_image_analysis_requests
        SET status = 'PERSISTENCE_PENDING',
            error_code = COALESCE(error_code, 'PERSISTED_WITHOUT_RESULT'),
            error_message = COALESCE(
                error_message,
                'Corrected by migration 0060b: PERSISTED without position/active_result'
            ),
            updated_at = SYSUTCDATETIME()
        WHERE status = 'PERSISTED'
          AND position_id IS NULL
          AND active_result_id IS NULL;

        PRINT CONCAT(
            '0060b: reconciled ',
            @inconsistent,
            ' inconsistent PERSISTED external_image_analysis_requests to PERSISTENCE_PENDING'
        );
    END

    -- Drop untrusted / NOCHECK constraint if present, then recreate trusted WITH CHECK.
    IF EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE name = 'CK_external_image_analysis_requests_persisted_result'
          AND parent_object_id = OBJECT_ID('external_image_analysis_requests')
    )
    BEGIN
        ALTER TABLE external_image_analysis_requests
            DROP CONSTRAINT CK_external_image_analysis_requests_persisted_result;
    END

    ALTER TABLE external_image_analysis_requests WITH CHECK
    ADD CONSTRAINT CK_external_image_analysis_requests_persisted_result
    CHECK (
        status <> 'PERSISTED'
        OR position_id IS NOT NULL
        OR active_result_id IS NOT NULL
    );
END
GO
