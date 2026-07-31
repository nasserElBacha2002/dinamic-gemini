/**
 * Regression: UploadsScreen must not embed raw text/whitespace between native views.
 * React Native throws "Text strings must be rendered within a <Text> component".
 */

import * as fs from 'fs';
import * as path from 'path';

describe('UploadsScreen JSX hygiene', () => {
  const sourcePath = path.join(__dirname, '../src/screens/UploadsScreen.tsx');
  const source = fs.readFileSync(sourcePath, 'utf8');

  it('does not close ProcessAisleConfirmModal with the known crash pattern', () => {
    expect(source).not.toContain('/>    </>');
    // Require a newline between self-closing modal and fragment close.
    expect(source).toMatch(/\/>\r?\n\s*<\/>/);
  });

  it('uses session-scoped or result-scoped sync from the aisle dialog path', () => {
    expect(source).toMatch(/syncPendingForSession|syncResults/);
    expect(source).not.toMatch(/authoritativeLocalSync\s*\.\s*syncPending\s*\(\s*\)/);
  });
});
