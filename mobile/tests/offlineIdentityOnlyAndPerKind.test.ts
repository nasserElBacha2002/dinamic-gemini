import { mapConfirmedToAuthoritativeRequest } from '../src/features/authoritativeLocalResult/authoritativeLocalResultPayloadMapper';
import type { ConfirmedLocalResultRow } from '../src/database/repositories/confirmedLocalResultRepository';
import { runProfileAwareLocalScan } from '../src/features/localCodeScan/profileAwareLocalScan';
import type { LocalLabelProfileResolver } from '../src/features/offlineRecognition/localLabelProfileResolver';
import { parseStoredProductResults } from '../src/core/storedProductResults';

describe('identity-only supplier ITEM', () => {
  it('maps empty confirmed internal_code to null on authoritative wire', () => {
    const row = {
      id: 'r1',
      capture_photo_id: 'p1',
      capture_session_id: 's1',
      client_file_id: 'cf1',
      asset_id: null,
      detected_internal_code: null,
      detected_quantity: null,
      confirmed_internal_code: '',
      confirmed_quantity: null,
      quantity_status: 'MISSING',
      source: 'LOCAL_CODE_SCAN',
      label_id: 'LPNA000184',
      detected_symbology: 'QR_CODE',
      parser_version: '1',
      detector_version: 'mlkit',
      prepared_asset_sha256: 'sha256:' + 'a'.repeat(64),
      confirmed_by_user_id: 'u1',
      confirmed_at: '2026-08-31T12:00:00Z',
      sync_status: 'PENDING',
      sync_attempt_count: 0,
      next_retry_at: null,
      sync_last_error_code: null,
      row_version: 1,
      applied_at: null,
      created_at: '2026-08-31T12:00:00Z',
      updated_at: '2026-08-31T12:00:00Z',
      recognition_profile_snapshot_json: JSON.stringify({
        offline: true,
        client_supplier_id: 'sup-a',
        item: {
          profile_source: 'SUPPLIER',
          profile_id: 'prof-item',
          profile_version: 3,
          configuration_schema_version: 2,
          status: 'VALID',
          label_id: 'LPNA000184',
          sku: null,
          quantity: null,
        },
      }),
    } as ConfirmedLocalResultRow;

    const body = mapConfirmedToAuthoritativeRequest(row);
    expect(body.internal_code).toBeNull();
    expect(body.quantity).toBeNull();
    expect(body.quantity_status).toBe('MISSING');
    expect(body.label_id).toBe('LPNA000184');
    expect(body.profile_source).toBe('SUPPLIER');
    expect(body.profile_version).toBe(3);
    expect(body.captured_offline).toBe(true);
  });

  it('parses stored product results with null quantity and null internalCode', () => {
    const rows = parseStoredProductResults(
      JSON.stringify([
        {
          labelId: 'LPNA000184',
          internalCode: null,
          quantity: null,
          formatVersion: 'SUPPLIER',
          validationStatus: 'VALID',
        },
      ]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]?.internalCode).toBeNull();
    expect(rows[0]?.quantity).toBeNull();
    expect(rows[0]?.labelId).toBe('LPNA000184');
  });
});

describe('per-kind missing profile', () => {
  it('still validates ITEM when only POSITION profile is missing', async () => {
    const resolver = {
      resolveForAisle: jest.fn(async () => ({
        item: {
          labelKind: 'ITEM',
          source: 'SUPPLIER',
          resolutionSource: 'CLIENT_SUPPLIER',
          clientSupplierId: 'sup-a',
          missingSupplierProfile: false,
          profile: {
            profile_id: 'pi',
            profile_version: 3,
            configuration_schema_version: 2,
          },
          configuration: {
            recognition_mode: 'MINIMAL',
            required_fields: ['label_id'],
            deterministic: {
              expected_prefix: 'LPNA',
              exact_length: 10,
              character_set: 'UPPERCASE_ALPHANUMERIC',
              payload_structure: 'SIMPLE',
              field_mappings: [{ target: 'label_id', source: 'WHOLE' }],
              normalization: { case_normalization: 'UPPER', trim_outer_whitespace: true },
            },
          },
        },
        position: {
          labelKind: 'POSITION',
          source: 'SUPPLIER',
          resolutionSource: 'CLIENT_SUPPLIER',
          clientSupplierId: 'sup-a',
          missingSupplierProfile: true,
          profile: null,
          configuration: null,
        },
      })),
    } as unknown as LocalLabelProfileResolver;

    const outcome = await runProfileAwareLocalScan({
      candidates: [{ rawValue: 'LPNA000184', symbology: 'QR_CODE' }],
      inventoryId: 'inv-1',
      aisleId: 'aisle-1',
      resolver,
      offline: true,
    });
    expect(outcome.itemProfileMissing).toBe(false);
    expect(outcome.positionProfileMissing).toBe(true);
    expect(outcome.supplierItem?.status).toBe('VALID');
    expect(outcome.supplierItem?.labelId).toBe('LPNA000184');
    expect(outcome.supplierItem?.sku).toBeNull();
    expect(outcome.supplierItem?.quantity).toBeNull();
    expect(outcome.supplierPosition).toBeNull();
  });
});
