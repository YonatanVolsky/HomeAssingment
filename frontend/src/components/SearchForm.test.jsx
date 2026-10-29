import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { SearchForm } from './SearchForm';
describe('SearchForm', () => {
  it('submits the trimmed term on Enter', async () => {
    const onSubmit = vi.fn();
    render(<SearchForm onSubmit={onSubmit} loading={false} />);
    await userEvent.type(screen.getByLabelText('Subreddit'), '  r/ubisoft  {Enter}');
    expect(onSubmit).toHaveBeenCalledWith('r/ubisoft');
  });
  it('blocks a blank submission with an inline message and sends nothing', async () => {
    const onSubmit = vi.fn();
    render(<SearchForm onSubmit={onSubmit} loading={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Collect posts' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Enter a subreddit name, like r/ubisoft.')).toBeInTheDocument();
    expect(screen.getByLabelText('Subreddit')).toHaveAttribute('aria-invalid', 'true');
  });
  it('disables Collect and marks it busy while loading', () => {
    render(<SearchForm onSubmit={vi.fn()} loading />);
    const button = screen.getByRole('button', { name: 'Collecting…' });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });
  it('shows Refresh only when a result can be refreshed', async () => {
    const onRefresh = vi.fn();
    const { rerender } = render(<SearchForm onSubmit={vi.fn()} loading={false} />);
    expect(screen.queryByRole('button', { name: 'Refresh' })).not.toBeInTheDocument();
    rerender(<SearchForm onSubmit={vi.fn()} loading={false} onRefresh={onRefresh} />);
    await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });
  it('starts with an initial term when given one', () => {
    render(<SearchForm onSubmit={vi.fn()} loading={false} initialTerm="gaming" />);
    expect(screen.getByLabelText('Subreddit')).toHaveValue('gaming');
  });
});
