/**
 * Regression: ProcessAisleConfirmModal must not embed raw text/whitespace between views.
 * React Native throws "Text strings must be rendered within a <Text> component".
 */

import * as fs from 'fs';
import * as path from 'path';

describe('ProcessAisleConfirmModal JSX hygiene', () => {
  const sourcePath = path.join(__dirname, '../src/components/ProcessAisleConfirmModal.tsx');
  const source = fs.readFileSync(sourcePath, 'utf8');

  it('does not glue null} onto the next ActionRow on the same line', () => {
    expect(source).not.toContain(') : null}                <ActionRow');
    expect(source).not.toMatch(/\) : null\}[ \t]+</);
  });

  it('places Ver resultados ActionRow after the allowUploadLocalResults block', () => {
    const uploadIdx = source.indexOf('allowUploadLocalResults');
    const verIdx = source.indexOf('title="Ver resultados"');
    expect(uploadIdx).toBeGreaterThan(-1);
    expect(verIdx).toBeGreaterThan(uploadIdx);
  });
});
