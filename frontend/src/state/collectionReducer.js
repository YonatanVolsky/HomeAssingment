/**
 * The five things the screen can show, and what moves between them.
 *
 * View (state):
 *   { kind: 'idle' }
 *   { kind: 'loading', term, force, previous? }   previous: the feed kept visible, dimmed
 *   { kind: 'success', data }                     data: a CollectionResponse with posts
 *   { kind: 'empty', data }                       a successful collection with zero posts
 *   { kind: 'error', term, error, lastGood? }     error: an ErrorBody
 *
 * Action (event):
 *   submit {term, force} | retry | resolved {data} | failed {error, lastGood?} | restored {data}
 */

/** The feed the user is looking at now, kept visible (dimmed) while the next one loads. */
export function visibleFeed(view) {
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

function loadingFrom(view, term, force) {
  const previous = visibleFeed(view);
  return { kind: 'loading', term, force, ...(previous && { previous }) };
}

function resultView(data) {
  return data.posts.length > 0 ? { kind: 'success', data } : { kind: 'empty', data };
}

export function collectionReducer(view, action) {
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
