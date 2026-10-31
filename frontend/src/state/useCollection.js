import { useCallback, useEffect, useReducer, useRef } from 'react';
import { ApiError, getFeed, NETWORK_ERROR } from '../api/client';
import { collectionReducer } from './collectionReducer';
const INITIAL = { kind: 'idle' };

export function useCollection(api = { getFeed }) {
  const [view, dispatch] = useReducer(collectionReducer, INITIAL);
  const viewRef = useRef(view);
  viewRef.current = view;
  // A ref, not state: two clicks in the same frame must not both see "not busy".
  const busy = useRef(false);
  const controller = useRef(null);
  useEffect(() => () => controller.current?.abort(), []);
  const run = useCallback(
    async (term, force) => {
      busy.current = true;
      controller.current = new AbortController();
      try {
        const freshness = force ? 'live' : 'auto';
        const data = await api.getFeed(term, freshness, { signal: controller.current.signal });
        dispatch({ type: 'resolved', data });
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (error instanceof ApiError) {
          dispatch({
            type: 'failed',
            error: error.body,
            ...(error.lastGood && { lastGood: error.lastGood }),
          });
        } else {
          dispatch({ type: 'failed', error: NETWORK_ERROR });
        }
      } finally {
        busy.current = false;
      }
    },
    [api],
  );
  const submit = useCallback(
    (term, force) => {
      if (busy.current) return;
      dispatch({ type: 'submit', term, force });
      void run(term, force);
    },
    [run],
  );
  const retry = useCallback(() => {
    const current = viewRef.current;
    if (busy.current || current.kind !== 'error' || !current.error.retryable) return;
    dispatch({ type: 'retry' });
    void run(current.term, false);
  }, [run]);
  const restore = useCallback((data) => {
    dispatch({ type: 'restored', data });
  }, []);
  return { view, submit, retry, restore };
}
