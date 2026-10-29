const PATHS = {
  comment: 'M4 4h16v11H8l-4 4V4z',
  arrowUp: 'M12 4l7 8h-4v8H9v-8H5l7-8z',
  external: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
};

/** Decorative icon; the text next to it carries the meaning. */
export function Icon({ name }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
