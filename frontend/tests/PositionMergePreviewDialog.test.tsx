import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import PositionMergePreviewDialog from '../src/features/results/components/PositionMergePreviewDialog';
import type { PositionMergePreviewResponse } from '../src/api/types';
import { I18nextProvider } from 'react-i18next';
import i18n from '../src/i18n';
import type { ReactElement } from 'react';

function wrap(ui: ReactElement) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>);
}

const previewOk: PositionMergePreviewResponse = {
  can_merge: true,
  preview_token: 'tok',
  sources: [
    {
      position_id: 'a',
      sku: 'SKU-1',
      quantity: 4,
      position_code: 'A01',
      source_image_filename: 'IMG_001.jpg',
    },
    {
      position_id: 'b',
      sku: 'SKU-1',
      quantity: 3,
      position_code: 'A01',
      source_image_filename: 'IMG_002.jpg',
    },
  ],
  merged_result: {
    survivor_id: 'a',
    sku: 'SKU-1',
    quantity: 7,
    position_code: 'A01',
    source_count: 2,
    image_count: 2,
  },
  warnings: [],
  conflicts: [],
};

describe('PositionMergePreviewDialog', () => {
  it('renders before/after and confirms', () => {
    const onConfirm = vi.fn();
    wrap(
      <PositionMergePreviewDialog
        open
        preview={previewOk}
        loading={false}
        confirming={false}
        errorMessage={null}
        onClose={() => undefined}
        onConfirm={onConfirm}
      />
    );
    expect(screen.getByTestId('position-merge-after')).toBeInTheDocument();
    expect(screen.getAllByTestId('position-merge-source-card')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('position-merge-confirm'));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('hides confirm when conflicts block merge', () => {
    wrap(
      <PositionMergePreviewDialog
        open
        preview={{
          ...previewOk,
          can_merge: false,
          conflicts: [{ code: 'sku_mismatch', message: 'SKU mismatch', values: ['A', 'B'] }],
        }}
        loading={false}
        confirming={false}
        errorMessage={null}
        onClose={() => undefined}
        onConfirm={() => undefined}
      />
    );
    expect(screen.getByTestId('position-merge-conflicts')).toBeInTheDocument();
    expect(screen.getByText(/SKU mismatch/)).toBeInTheDocument();
    expect(screen.queryByTestId('position-merge-confirm')).not.toBeInTheDocument();
  });

  it('shows warning values compactly', () => {
    wrap(
      <PositionMergePreviewDialog
        open
        preview={{
          ...previewOk,
          warnings: [
            {
              code: 'barcode_mismatch',
              message: 'Barcode mismatch',
              values: ['111', '222'],
            },
          ],
        }}
        loading={false}
        confirming={false}
        errorMessage={null}
        onClose={() => undefined}
        onConfirm={() => undefined}
      />
    );
    expect(screen.getByTestId('position-merge-warnings')).toBeInTheDocument();
    expect(screen.getByText(/111/)).toBeInTheDocument();
  });

  it('shows preview loading and confirm error', () => {
    const { unmount } = wrap(
      <PositionMergePreviewDialog
        open
        preview={null}
        loading
        confirming={false}
        errorMessage={null}
        onClose={() => undefined}
        onConfirm={() => undefined}
      />
    );
    expect(screen.getByTestId('position-merge-preview-loading')).toBeInTheDocument();
    unmount();

    wrap(
      <PositionMergePreviewDialog
        open
        preview={previewOk}
        loading={false}
        confirming={false}
        errorMessage="Los registros cambiaron"
        onClose={() => undefined}
        onConfirm={() => undefined}
      />
    );
    expect(screen.getByText(/Los registros cambiaron/)).toBeInTheDocument();
  });
});
