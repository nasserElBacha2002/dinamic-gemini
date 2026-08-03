import {
  nextSequenceAssignments,
  reserveSequenceRange,
  sortByGalleryOrder,
} from '../src/core/captureSequence';

describe('sortByGalleryOrder', () => {
  it('orders by date_added ASC then asset_id ASC (gallery contract)', () => {
    const mixed = [
      { assetId: '30', dateAdded: 2000 },
      { assetId: '10', dateAdded: 1000 },
      { assetId: '20', dateAdded: 1000 },
    ];
    expect(sortByGalleryOrder(mixed).map((i) => i.assetId)).toEqual(['10', '20', '30']);
  });
});

describe('nextSequenceAssignments (persist-time / defensive)', () => {
  it('assigns 1..N for photos without sequence', () => {
    const photos = [
      { id: 'a', sequence_number: null },
      { id: 'b', sequence_number: null },
      { id: 'c', sequence_number: null },
    ];
    expect(nextSequenceAssignments(photos)).toEqual([
      { id: 'a', sequenceNumber: 1 },
      { id: 'b', sequenceNumber: 2 },
      { id: 'c', sequenceNumber: 3 },
    ]);
  });

  it('does not recalculate existing sequence numbers (restart preserves)', () => {
    const photos = [
      { id: 'a', sequence_number: 1 },
      { id: 'b', sequence_number: 2 },
      { id: 'c', sequence_number: null },
    ];
    expect(nextSequenceAssignments(photos)).toEqual([{ id: 'c', sequenceNumber: 3 }]);
  });
});

describe('sequence assignment timing scenarios', () => {
  /**
   * Simulate: multi-select / batch admit assigns sequences in gallery order at persist,
   * then photos stabilize out of order. Sequences must stay gallery order.
   */
  it('stable out of order does not change persist-time sequences', () => {
    const selection = sortByGalleryOrder([
      { assetId: 'c', dateAdded: 3000, id: 'photo-c' },
      { assetId: 'a', dateAdded: 1000, id: 'photo-a' },
      { assetId: 'b', dateAdded: 2000, id: 'photo-b' },
    ]);
    const atPersist = nextSequenceAssignments(
      selection.map((p) => ({ id: p.id, sequence_number: null })),
    );
    expect(atPersist).toEqual([
      { id: 'photo-a', sequenceNumber: 1 },
      { id: 'photo-b', sequenceNumber: 2 },
      { id: 'photo-c', sequenceNumber: 3 },
    ]);

    // Stability completes as c → a → b (wrong physical order).
    const afterStability = [
      { id: 'photo-a', sequence_number: 1 },
      { id: 'photo-b', sequence_number: 2 },
      { id: 'photo-c', sequence_number: 3 },
    ];
    // Defensive upload-time pass must not reassign.
    expect(nextSequenceAssignments(afterStability)).toEqual([]);
  });

  /**
   * Transform/prep completing out of order must not rewrite sequences.
   */
  it('transform out of order leaves sequences intact', () => {
    const withSequences = [
      { id: 'photo-a', sequence_number: 1 },
      { id: 'photo-b', sequence_number: 2 },
      { id: 'photo-c', sequence_number: 3 },
    ];
    // Prep finishes as b, c, a — upload defensive recovery sees all assigned.
    expect(nextSequenceAssignments(withSequences)).toEqual([]);
  });

  it('restart preserves sequences and only fills NULL legacy rows', () => {
    const afterRestart = [
      { id: 'photo-a', sequence_number: 1 },
      { id: 'photo-b', sequence_number: 2 },
      { id: 'legacy', sequence_number: null },
    ];
    expect(nextSequenceAssignments(afterRestart)).toEqual([
      { id: 'legacy', sequenceNumber: 3 },
    ]);
  });

  it('exclude photo keeps existing sequences; gaps are allowed', () => {
    // photo-b excluded (kept in DB with sequence 2); remaining a=1, c=3.
    const afterExclude = [
      { id: 'photo-a', sequence_number: 1 },
      { id: 'photo-c', sequence_number: 3 },
    ];
    expect(nextSequenceAssignments(afterExclude)).toEqual([]);
  });

  it('add photo later appends after max existing sequence', () => {
    const afterExcludeThenAdd = [
      { id: 'photo-a', sequence_number: 1 },
      { id: 'photo-c', sequence_number: 3 },
      { id: 'photo-d', sequence_number: null },
    ];
    expect(nextSequenceAssignments(afterExcludeThenAdd)).toEqual([
      { id: 'photo-d', sequenceNumber: 4 },
    ]);
  });

  it('reserveSequenceRange allocates contiguous numbers after current max', () => {
    expect(reserveSequenceRange(0, 3)).toEqual([1, 2, 3]);
    expect(reserveSequenceRange(5, 2)).toEqual([6, 7]);
    expect(reserveSequenceRange(2, 0)).toEqual([]);
  });
});
