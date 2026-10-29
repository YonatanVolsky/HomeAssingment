import { useId, useState } from 'react';
/**
 * @param {object} props
 * @param {(term: string) => void} props.onSubmit
 * @param {boolean} props.loading
 * @param {() => void} [props.onRefresh]  present only when there is a result to refresh
 * @param {string} [props.initialTerm]
 */
export function SearchForm({ onSubmit, loading, onRefresh, initialTerm = '' }) {
  const [term, setTerm] = useState(initialTerm);
  const [blank, setBlank] = useState(false);
  const inputId = useId();
  const hintId = useId();
  const handleSubmit = (event) => {
    event.preventDefault();
    const trimmed = term.trim();
    setBlank(trimmed === '');
    if (trimmed !== '') onSubmit(trimmed);
  };
  return (
    <form className="search" onSubmit={handleSubmit} noValidate>
      <label htmlFor={inputId}>Subreddit</label>
      <div className="search-row">
        <input
          id={inputId}
          type="text"
          value={term}
          onChange={(event) => {
            setTerm(event.target.value);
            if (blank) setBlank(false);
          }}
          placeholder="r/ubisoft"
          autoComplete="off"
          spellCheck={false}
          aria-invalid={blank}
          aria-describedby={hintId}
        />
        <button type="submit" className="button primary" disabled={loading} aria-busy={loading}>
          {loading ? 'Collecting…' : 'Collect posts'}
        </button>
        {onRefresh && (
          <button type="button" className="button secondary" onClick={onRefresh} disabled={loading}>
            Refresh
          </button>
        )}
      </div>
      <p id={hintId} className={blank ? 'hint invalid' : 'hint'}>
        {blank
          ? 'Enter a subreddit name, like r/ubisoft.'
          : 'A subreddit name or link, e.g. ubisoft, r/ubisoft or reddit.com/r/ubisoft.'}
      </p>
    </form>
  );
}
