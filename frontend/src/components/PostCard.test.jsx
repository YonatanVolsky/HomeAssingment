import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { makePost, NOW } from '../test/makePost';
import { PostCard } from './PostCard';
import { PostList } from './PostList';
describe('PostCard', () => {
  it('shows the title as a heading with author, subreddit and relative time', () => {
    render(
      <PostCard
        post={makePost('t3_a', { title: 'Is it playable?', author: 'LazyGas' })}
        now={NOW}
      />,
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Is it playable?' })).toBeInTheDocument();
    expect(screen.getByText('u/LazyGas')).toBeInTheDocument();
    expect(screen.getByText('r/ubisoft')).toBeInTheDocument();
    const time = screen.getByText('49 min ago');
    expect(time.tagName).toBe('TIME');
    expect(time).toHaveAttribute('dateTime', '2026-10-29T11:11:00.000Z');
  });
  it('shows [deleted] for a missing author', () => {
    render(<PostCard post={makePost('t3_a', { author: null })} now={NOW} />);
    expect(screen.getByText('[deleted]')).toBeInTheDocument();
  });
  it('shows flair and preview text only when present', () => {
    const { rerender } = render(
      <PostCard
        post={makePost('t3_a', { flair: 'Question', previewText: 'Body text' })}
        now={NOW}
      />,
    );
    expect(screen.getByText('Question')).toBeInTheDocument();
    expect(screen.getByText('Body text')).toBeInTheDocument();
    rerender(<PostCard post={makePost('t3_a')} now={NOW} />);
    expect(screen.queryByText('Question')).not.toBeInTheDocument();
    expect(screen.queryByText('Body text')).not.toBeInTheDocument();
  });
  it('labels counts for screen readers with exact numbers', () => {
    render(<PostCard post={makePost('t3_a', { commentCount: 1250, score: 1 })} now={NOW} />);
    expect(screen.getByText('1.3k')).toBeInTheDocument();
    expect(screen.getByText('1250 comments')).toHaveClass('visually-hidden');
    expect(screen.getByText('1 point')).toHaveClass('visually-hidden');
  });
  it('links to the original post in a new tab', () => {
    render(<PostCard post={makePost('t3_a')} now={NOW} />);
    const link = screen.getByRole('link', { name: /open on reddit/i });
    expect(link).toHaveAttribute('href', 'https://www.reddit.com/r/ubisoft/comments/t3_a/');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
  it.each(['javascript:alert(1)', 'https://evil.com/r/x/', 'http://www.reddit.com/r/x/'])(
    'renders no link for the unsafe permalink %s',
    (permalink) => {
      render(<PostCard post={makePost('t3_a', { permalink })} now={NOW} />);
      expect(screen.queryByRole('link')).not.toBeInTheDocument();
    },
  );
});
describe('PostList', () => {
  it('renders one list item per post in the given order', () => {
    render(<PostList posts={[makePost('t3_b'), makePost('t3_a')]} now={NOW} />);
    const items = within(screen.getByRole('list', { name: 'Posts' })).getAllByRole('listitem');
    expect(items.map((item) => within(item).getByRole('heading').textContent)).toEqual([
      'Post t3_b',
      'Post t3_a',
    ]);
  });
});
