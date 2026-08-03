import { compactSequenceAssignments, nextSequenceAssignments } from '../src/core/captureSequence';

describe('compactSequenceAssignments', () => {
  it('returns empty when already contiguous 1..N', () => {
    expect(
      compactSequenceAssignments([
        { id: 'a', sequence_number: 1 },
        { id: 'b', sequence_number: 2 },
        { id: 'c', sequence_number: 3 },
      ]),
    ).toEqual([]);
  });

  it('compacts gaps after exclusion (max=6 expected 5)', () => {
    expect(
      compactSequenceAssignments([
        { id: 'a', sequence_number: 1 },
        { id: 'b', sequence_number: 2 },
        { id: 'c', sequence_number: 3 },
        { id: 'd', sequence_number: 5 },
        { id: 'e', sequence_number: 6 },
      ]),
    ).toEqual([
      { id: 'd', sequenceNumber: 4 },
      { id: 'e', sequenceNumber: 5 },
    ]);
  });

  it('documents two-phase apply is required when target equals another current', () => {
    // 5→4 while another row still holds 4 (excluded) would unique-fail in one pass.
    const changes = compactSequenceAssignments([
      { id: 'keep', sequence_number: 1 },
      { id: 'gap', sequence_number: 5 },
    ]);
    expect(changes).toEqual([{ id: 'gap', sequenceNumber: 2 }]);
  });
});

describe('nextSequenceAssignments', () => {
  it('only fills null sequences', () => {
    expect(
      nextSequenceAssignments([
        { id: 'a', sequence_number: 1 },
        { id: 'b', sequence_number: null },
      ]),
    ).toEqual([{ id: 'b', sequenceNumber: 2 }]);
  });
});
