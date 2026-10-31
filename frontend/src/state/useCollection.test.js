import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import { useCollection } from './useCollection';
const response = {
  collection: {
    id: 1,
    term: 'ubisoft',
    source: 'live',
    collectedAt: '2026-10-29T12:00:00.000Z',
    postCount: 0,
  },
  posts: [],
};

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
describe('useCollection', () => {
  it('goes from loading to a result', async () => {
    const pending = deferred();
    const getFeed = vi.fn(() => pending.promise);
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => result.current.submit('ubisoft', false));
    expect(result.current.view.kind).toBe('loading');
    await act(async () => pending.resolve(response));
    expect(result.current.view).toEqual({ kind: 'empty', data: response });
  });
  it('sends one request when submit is called twice quickly', async () => {
    const getFeed = vi.fn(() => new Promise(() => {}));
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => {
      result.current.submit('ubisoft', false);
      result.current.submit('ubisoft', false);
    });
    expect(getFeed).toHaveBeenCalledTimes(1);
  });
  it('shows a server error with its last good feed', async () => {
    const error = new ApiError(
      { code: 'UPSTREAM_TIMEOUT', message: 'slow', retryable: true },
      response,
    );
    const getFeed = vi.fn(() => Promise.reject(error));
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => result.current.submit('ubisoft', false));
    await waitFor(() => expect(result.current.view.kind).toBe('error'));
    expect(result.current.view).toMatchObject({
      error: { code: 'UPSTREAM_TIMEOUT' },
      lastGood: response,
    });
  });
  it('retries with the same term and without force', async () => {
    const error = new ApiError({ code: 'UPSTREAM_ERROR', message: 'down', retryable: true });
    const getFeed = vi.fn().mockRejectedValueOnce(error).mockResolvedValueOnce(response);
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => result.current.submit('ubisoft', true));
    await waitFor(() => expect(result.current.view.kind).toBe('error'));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.view.kind).toBe('empty'));
    expect(getFeed).toHaveBeenLastCalledWith('ubisoft', 'auto', expect.anything());
  });
  it('does not retry an error that is not retryable', async () => {
    const error = new ApiError({ code: 'NOT_FOUND_SUBREDDIT', message: 'nope', retryable: false });
    const getFeed = vi.fn(() => Promise.reject(error));
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => result.current.submit('nope', false));
    await waitFor(() => expect(result.current.view.kind).toBe('error'));
    act(() => result.current.retry());
    expect(getFeed).toHaveBeenCalledTimes(1);
  });
  it('treats an unexpected exception as a network error', async () => {
    const getFeed = vi.fn(() => Promise.reject(new Error('weird')));
    const { result } = renderHook(() => useCollection({ getFeed }));
    act(() => result.current.submit('ubisoft', false));
    await waitFor(() => expect(result.current.view).toMatchObject({ error: { code: 'NETWORK' } }));
  });
});
