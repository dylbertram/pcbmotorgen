/** Minimal storage fake for tests that exercise one key. */
export function singleValueStorage() {
  let saved: string | null = null;
  return {
    storage: {
      getItem: () => saved,
      setItem: (_key: string, value: string) => { saved = value; },
    },
    get value() { return saved; },
  };
}
