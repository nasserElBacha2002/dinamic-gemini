# Mobile ↔ Backend recognition parity matrix

Golden reference: job `f898e6f7-aab1-4eee-bb47-61e71df7cebe`, aisle `709fe503-2f5c-43ae-b680-25bbc3bbf51f`.

| Capability | Backend | Mobile | Status |
|------------|---------|--------|--------|
| Supplier wiring (ClientSupplier) | `client_supplier_label_profiles` + aisle `client_supplier_id` | Synced via recognition-config bundle | **PARITY** (if sync OK) |
| Aisle override precedence | LabelProfileResolver | LocalLabelProfileResolver same order | **PARITY** |
| ITEM profile version pinning | Snapshot at job start v10 | SQLite `profile_version` + draft snapshot | **PARITY** (design) |
| POSITION profile version pinning | Snapshot v3 | SQLite + draft snapshot | **PARITY** (design) |
| recognition-config endpoint | GET `/api/v3/inventories/{id}/recognition-config` | `OfflineRecognitionSyncService.fetchBundle` | **PARITY** |
| bundle_revision algorithm | SHA-256 canonical bundle (excl. generated_at) | Trusts server string; skip if equal | **PARITY** (server-side hash OK) |
| bundle_revision stale skip risk | N/A (authoritative) | Blind skip if revision unchanged | **MOBILE GAP** (P1 — mitigated if backend hash correct) |
| Atomic bundle replace | DB transaction | `replaceBundle` in `withTransactionAsync` | **PARITY** |
| MINIMAL offline validation | LabelValidationService | validateSupplierPayloadOffline | **PARITY** (shared vectors) |
| SIMPLE offline validation | Yes | Yes | **PARITY** |
| SEGMENTED offline validation | StructuredPayloadExtractor | extractFields SEGMENTED branch | **PARITY** (code); **MOBILE GAP** (fixtures) |
| GS1 offline | Supported server-side | Explicitly blocked offline | **NOT SUPPORTED BY DESIGN** |
| QR decode | pyzbar / CODE_SCAN | ML Kit QR_CODE | **PARITY** |
| CODE128 decode | pyzbar | ML Kit CODE_128 | **PARITY** |
| Dual-symbol same payload dedupe | `code_scan_label_classifier` DUPLICATE by identity | Native rawValue merge + first-valid candidate loop | **PARTIAL PARITY** (P1 — no explicit supplier identity dedupe test) |
| Normalization order | trim → case → spaces → hyphens | Same order in normalizeOfflinePayload | **PARITY** |
| Prefix / length / charset on raw payload | Before segmentation | Before segmentation | **PARITY** |
| ITEM: label_id + sku + quantity separate | Yes | Yes (validator L409 guard) | **PARITY** |
| ITEM: no quantity=0 sentinel | Yes | null preserved; confirm rejects qty≤0 | **PARITY** |
| ITEM: no internalCode from labelId (wire) | Authoritative ingest | mapConfirmedToAuthoritativeRequest null internal_code | **PARITY** |
| ITEM: labelId fallback in draft | N/A | `labelId \|\| internalCode` in strategy L286 | **MOBILE GAP** (P1) |
| POSITION: segmented fields | position_id, pallet, side, level | Same fields in validator | **PARITY** (code) |
| POSITION: quantity null | NOT_APPLICABLE | No quantity field set | **PARITY** |
| POSITION: no sku/internalCode invention | Yes | Supplier path uses position fields only | **PARITY** |
| AMBIGUOUS_LABEL_KIND | validate_best_effort both kinds | profileAwareLocalScan ambiguous flag | **PARITY** |
| DINAMIC fail-closed (invalid D1) | consolidator blocks legacy | consolidateCodeDetections + skip D1-looking in supplier loop | **PARITY** |
| Missing SUPPLIER profile | SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED | missingSupplierProfile + readiness block | **PARITY** |
| Per-kind missing profile | Separate ITEM/POSITION | itemProfileMissing / positionProfileMissing | **PARITY** |
| Historical profile on ingest | Exact version + label_kind | Sends profile_id/version; mapper hardcodes label_kind=ITEM | **MOBILE GAP** (P1 for POSITION authoritative path) |
| Backend authoritative revalidation | persist_authoritative_local_code_scan | Mobile optimistic + server revalidates | **PARITY** (design) |
| Preliminary upload metadata | Server-side job CODE_SCAN | preliminaryDraftPayloadMapper — no profile snapshot | **MOBILE GAP** (P2 — server re-scans) |
| Production fixture LPNA000184\|SKU773421\|24 | test_supplier_profile_runtime_wiring | No dedicated mobile test | **MOBILE GAP** (P1 test coverage) |
| Production fixture A04-R-02\|04\|RIGHT\|02 | test_supplier_profile_runtime_wiring | No dedicated mobile test | **MOBILE GAP** (P1 test coverage) |
| Observability events | code_scan.* pipeline events | No mobile.recognition.* events found | **MOBILE GAP** (P2) |
| Device E2E real images | Job f898e6f7 succeeded | Not executed | **UNVERIFIED** |
