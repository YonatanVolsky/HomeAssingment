import type { CollectionResponse } from '@reddit-collector/contracts';
import type { UiErrorBody } from '../api/client';

export type View =
  | { kind: 'idle' }
  | { kind: 'loading'; term: string; force: boolean; previous?: CollectionResponse }
  | { kind: 'success'; data: CollectionResponse }
  | { kind: 'empty'; data: CollectionResponse }
  | { kind: 'error'; term: string; error: UiErrorBody; lastGood?: CollectionResponse };

export type Action =
  | { type: 'submit'; term: string; force: boolean }
  | { type: 'retry' }
  | { type: 'resolved'; data: CollectionResponse }
  | { type: 'failed'; error: UiErrorBody; lastGood?: CollectionResponse }
  | { type: 'restored'; data: CollectionResponse };

/** The feed the user is looking at now, kept visible (dimmed) while the next one loads. */
export function visibleFeed(view: View): CollectionResponse | undefined {
  switch (view.kind) {
    case 'success':
    case 'empty':
      return view.data;
    case 'error':
      return view.lastGood;
    case 'loading':
      return view.previous;
    case 'idle':
      return undefined;
  }
}

function loadingFrom(view: View, term: string, force: boolean): View {
  const previous = visibleFeed(view);
  return { kind: 'loading', term, force, ...(previous && { previous }) };
}

function resultView(data: CollectionResponse): View {
  return data.posts.length > 0 ? { kind: 'success', data } : { kind: 'empty', data };
}

export function collectionReducer(view: View, action: Action): View {
  switch (action.type) {
    case 'submit':
      return view.kind === 'loading' ? view : loadingFrom(view, action.term, action.force);
    case 'retry':
      return view.kind === 'error' && view.error.retryable
        ? loadingFrom(view, view.term, false)
        : view;
    case 'resolved':
      return view.kind === 'loading' ? resultView(action.data) : view;
    case 'failed': {
      if (view.kind !== 'loading') return view;
      const lastGood = action.lastGood ?? view.previous;
      return { kind: 'error', term: view.term, error: action.error, ...(lastGood && { lastGood }) };
    }
    case 'restored':
      return view.kind === 'idle' && action.data.collection ? resultView(action.data) : view;
  }
}
