import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { getSupplierReferenceImageFileUrl, uploadSupplierReferenceImages } from '../src/api/clientSuppliersApi';
import {
  supplierReferenceImageFilePath,
  supplierReferenceImagePath,
  supplierReferenceImagesPath,
} from '../src/constants/v3ApiPaths';

describe('supplier reference images API paths', () => {
  it('supplierReferenceImagesPath encodes client and supplier ids', () => {
    expect(supplierReferenceImagesPath('c/1', 's 2')).toBe(
      `/api/v3/clients/${encodeURIComponent('c/1')}/suppliers/${encodeURIComponent('s 2')}/reference-images`
    );
  });

  it('supplierReferenceImagePath appends image id', () => {
    expect(supplierReferenceImagePath('cli', 'sup', 'img/x')).toContain(
      `/reference-images/${encodeURIComponent('img/x')}`
    );
  });

  it('supplierReferenceImageFilePath ends with /file', () => {
    expect(supplierReferenceImageFilePath('a', 'b', 'c')).toMatch(/\/file$/);
  });
});

describe('getSupplierReferenceImageFileUrl', () => {
  it('includes the same logical path as supplierReferenceImageFilePath', () => {
    const url = getSupplierReferenceImageFileUrl('client-1', 'sup-1', 'img-1');
    expect(url.endsWith(supplierReferenceImageFilePath('client-1', 'sup-1', 'img-1'))).toBe(true);
  });
});

describe('uploadSupplierReferenceImages FormData', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        text: async () =>
          JSON.stringify({
            items: [
              {
                id: 'img-1',
                client_supplier_id: 'sup-1',
                filename: 'a.jpg',
                mime_type: 'image/jpeg',
                file_size: 10,
                created_at: '2026-05-07T00:00:00Z',
                updated_at: '2026-05-07T00:00:00Z',
              },
            ],
          }),
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('appends each file as files and optional label/description', async () => {
    const payloadFetch = vi.mocked(fetch);
    const file = new File([new Uint8Array([1, 2])], 'pic.jpg', { type: 'image/jpeg' });
    await uploadSupplierReferenceImages('c1', 's1', {
      files: [file],
      label: ' L ',
      description: ' D ',
    });

    expect(payloadFetch).toHaveBeenCalledTimes(1);
    const init = payloadFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBeInstanceOf(FormData);
    const form = init.body as FormData;
    expect(form.getAll('files').length).toBe(1);
    expect(form.get('label')).toBe('L');
    expect(form.get('description')).toBe('D');
  });
});
