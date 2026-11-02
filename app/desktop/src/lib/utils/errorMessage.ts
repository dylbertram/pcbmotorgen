/** Preserve Error messages and stringify other thrown values, including IPC errors. */
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
