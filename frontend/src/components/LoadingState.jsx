export function LoadingState({ term }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>Collecting posts from r/{term}… this can take up to ~25 s.</span>
    </div>
  );
}
