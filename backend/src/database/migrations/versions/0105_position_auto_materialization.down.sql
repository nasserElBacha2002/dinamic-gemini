/*
  DESTRUCTIVE ROLLBACK PREFLIGHT — position auto-materialization.

  Before running:
    1. Disable POSITION_AUTO_MATERIALIZATION_ENABLED and
       POSITION_MATERIALIZATION_RECOVERY_ENABLED in every API/worker process.
    2. Stop recovery schedulers and take a database backup.
    3. Roll back 0107 and 0106 first.
    4. Verify both queries return zero rows:

       SELECT id, association_status
       FROM dbo.position_materialization_requests;

       SELECT id, creation_source, source_capture_id
       FROM dbo.aisle_locations
       WHERE creation_source = 'AUTO';

  There is no operator override. The ledger is dropped only when empty and no
  auto-created locations or mobile request references remain. This migration
  never deletes aisle_locations or mobile_preliminary_detections rows.

  Provenance/mobile columns are intentionally retained. Migration 0105 added
  them conditionally, so a down migration cannot prove column ownership on a
  database where similarly named columns predated 0105. Retention avoids
  deleting preexisting non-owned schema or data.
*/

IF OBJECT_ID(N'dbo.position_materialization_association_receipts', N'U') IS NOT NULL
    THROW 51014, '0105 rollback requires 0106 to be rolled back first', 1;
GO

IF OBJECT_ID(N'dbo.position_materialization_requests', N'U') IS NOT NULL
AND EXISTS (SELECT 1 FROM dbo.position_materialization_requests)
    THROW 51015, '0105 rollback requires the materialization ledger to be drained', 1;
GO

IF COL_LENGTH(N'dbo.aisle_locations', N'creation_source') IS NOT NULL
AND EXISTS (
    SELECT 1 FROM dbo.aisle_locations WHERE creation_source = 'AUTO'
)
    THROW 51017, '0105 rollback requires auto-created locations to be drained or converted by an audited operator procedure', 1;
GO

IF COL_LENGTH(
    N'dbo.mobile_preliminary_detections',
    N'position_materialization_request_id'
) IS NOT NULL
AND EXISTS (
    SELECT 1
    FROM dbo.mobile_preliminary_detections
    WHERE position_materialization_request_id IS NOT NULL
)
    THROW 51018, '0105 rollback requires mobile materialization references to be drained', 1;
GO

IF OBJECT_ID(N'dbo.position_materialization_requests', N'U') IS NOT NULL
    DROP TABLE dbo.position_materialization_requests;
GO

/*
  Intentionally retained for ownership safety:
    dbo.mobile_preliminary_detections.position_created
    dbo.mobile_preliminary_detections.position_idempotent_replay
    dbo.mobile_preliminary_detections.position_materialization_request_id
    dbo.aisle_locations creation/provenance columns and their named constraints

  Post-rollback verification:
    SELECT OBJECT_ID(N'dbo.position_materialization_requests', N'U') AS ledger;
    SELECT COUNT_BIG(*) AS auto_locations
    FROM dbo.aisle_locations WHERE creation_source = 'AUTO';
*/
