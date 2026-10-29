/** The subset of pino's API the app uses, so modules do not depend on Fastify. */
export interface Logger {
  error(obj: object, msg: string): void;
  warn(obj: object, msg: string): void;
  info(obj: object, msg: string): void;
}
