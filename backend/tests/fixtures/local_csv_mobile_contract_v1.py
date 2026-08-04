"""Contract fixture: CSV shaped like the mobile exporter (schema v1).

Generated to match `mobile/src/features/localCsv/csvFormat.ts` headers and
detection `source` values. Backend assigns ingestion_source=LOCAL_CSV_IMPORT.
"""

from __future__ import annotations

# Keep in sync with mobile LOCAL_CSV_HEADERS + buildLocalCsvRows.
MOBILE_CSV_CONTRACT_V1 = (
    "schema_version,export_id,exported_at,device_id,company_id,client_id,"
    "inventory_id,inventory_name,aisle_id,aisle_code,capture_session_id,"
    "capture_photo_id,client_file_id,capture_order,captured_at,position_code,"
    "position_status,internal_code,quantity,quantity_status,detection_status,"
    "detector_version,parser_version,prepared_asset_fingerprint,source,"
    "requires_review,confirmed_manually,error_code,notes,freeze_id,freeze_generation\r\n"
    "1,export-contract-1,2026-08-04T10:00:00+00:00,install-uuid-1,company-1,client-1,"
    "inventory-1,Inv One,aisle-1,A1,session-1,"
    "photo-1,file-1,1,2026-08-04T09:59:00+00:00,A-01,"
    ",SKU-1,7,PRESENT,CONFIRMED,"
    "det-1,par-1,fp-1,LOCAL_CODE_SCAN,"
    "false,true,,ok,freeze-1,1\r\n"
).encode("utf-8")
