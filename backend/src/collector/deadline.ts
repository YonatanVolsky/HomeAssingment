import { AppError } from '../errors.js';

/** One time budget for a whole collection. Its signal aborts every request still running. */
export class Deadline {
  private readonly controller = new AbortController();
  private readonly timer: NodeJS.Timeout;
  private readonly endsAt: number;

  constructor(ms: number) {
    this.endsAt = Date.now() + ms;
    this.timer = setTimeout(() => this.controller.abort(Deadline.error()), ms);
    this.timer.unref();
  }

  static error(cause?: unknown): AppError {
    return new AppError('UPSTREAM_TIMEOUT', undefined, { cause, autoRetry: false });
  }

  get signal(): AbortSignal {
    return this.controller.signal;
  }

  get expired(): boolean {
    return this.controller.signal.aborted;
  }

  remainingMs(): number {
    return Math.max(0, this.endsAt - Date.now());
  }

  dispose(): void {
    clearTimeout(this.timer);
  }
}
