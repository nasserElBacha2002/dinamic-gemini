import '@testing-library/jest-dom/vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RelatedEntityCell from '../src/components/ui/RelatedEntityCell';

describe('RelatedEntityCell', () => {
  it('renders empty label when name is missing', () => {
    render(<RelatedEntityCell name={null} emptyLabel="Sin cliente" testId="cell" />);
    expect(screen.getByTestId('cell')).toHaveTextContent('Sin cliente');
  });

  it('trims whitespace-only names to empty state', () => {
    render(<RelatedEntityCell name="   " emptyLabel="Sin cliente" testId="cell" />);
    expect(screen.getByTestId('cell')).toHaveTextContent('Sin cliente');
  });

  it('trims display name and renders without link when to is absent', () => {
    render(<RelatedEntityCell name="  Acme  " emptyLabel="Sin cliente" testId="cell" />);
    expect(screen.getByTestId('cell')).toHaveTextContent('Acme');
    expect(screen.getByTestId('cell').tagName).not.toBe('A');
  });

  it('renders truncated name with link when to is provided', () => {
    render(
      <MemoryRouter>
        <RelatedEntityCell
          name="Nombre muy largo de entidad relacionada"
          emptyLabel="Sin cliente"
          to="/clients/c-1"
          testId="cell"
        />
      </MemoryRouter>
    );
    const link = screen.getByTestId('cell');
    expect(link).toHaveTextContent('Nombre muy largo de entidad relacionada');
    expect(link).toHaveAttribute('href', '/clients/c-1');
  });

  it('stops click propagation on link', () => {
    const parentClick = vi.fn();
    render(
      <MemoryRouter>
        <div onClick={parentClick}>
          <RelatedEntityCell name="Acme" emptyLabel="Sin" to="/clients/c-1" testId="cell" />
        </div>
      </MemoryRouter>
    );
    fireEvent.click(screen.getByTestId('cell'));
    expect(parentClick).not.toHaveBeenCalled();
  });
});
