"""Contract fixture: CSV shaped like the mobile exporter (schema v1).

Generated to match `mobile/src/features/localCsv/csvFormat.ts` headers and
detection `source` values. Backend assigns ingestion_source=LOCAL_CSV_IMPORT.
"""

from __future__ import annotations

# Keep in sync with mobile LOCAL_CSV_HEADERS + buildLocalCsvRows.
MOBILE_CSV_CONTRACT_V1 = (
    b"schema_version,export_id,exported_at,device_id,inventory_id,aisle_id,"
    b"capture_session_id,capture_photo_id,client_file_id,capture_order,captured_at,"
    b"position_code,position_label_id,position_payload_raw,internal_code,label_id,"
    b"quantity,quantity_status,detection_status,source,requires_review,error_code,notes\r\n"
    b"1.1,export-contract-1,2026-08-04T10:00:00+00:00,install-uuid-1,"
    b"inventory-1,aisle-1,session-1,photo-1,file-1,1,2026-08-04T09:59:00+00:00,A-01,"
    b",,SKU-1,,7,PRESENT,CONFIRMED,LOCAL_CODE_SCAN,false,,ok\r\n"
)
