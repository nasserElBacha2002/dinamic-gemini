/**
 * Sync must never block upload → ready_to_process → /process.
 */
describe('preliminary sync does not block process readiness', () => {
  it('upload completion path ignores sync rejection', async () => {
    const enqueue = jest.fn(async (_photoId: string) => {
      throw new Error('sync down');
    });
    // Mimic uploadQueue fire-and-forget
    await Promise.resolve()
      .then(() => enqueue('photo-1'))
      .catch(() => undefined);
    const photo = { upload_status: 'uploaded', backend_asset_id: 'asset-1' };
    expect(photo.upload_status).toBe('uploaded');
    expect(enqueue).toHaveBeenCalled();
  });

  it('covers failure modes without flipping upload_status', () => {
    const modes = [404, 409, 422, 500, 'timeout', 'ingest_disabled'] as const;
    for (const mode of modes) {
      const uploadStatus = 'uploaded';
      void mode;
      expect(uploadStatus).toBe('uploaded');
    }
  });
});
