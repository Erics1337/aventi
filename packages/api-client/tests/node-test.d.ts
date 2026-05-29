declare module 'node:assert/strict' {
  const assert: {
    equal(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    rejects(
      block: Promise<unknown>,
      error?: (error: unknown) => boolean,
      message?: string,
    ): Promise<void>;
  };
  export default assert;
}

declare module 'node:test' {
  interface TestFn {
    (name: string, fn: () => unknown | Promise<unknown>): void;
    afterEach(fn: () => unknown | Promise<unknown>): void;
  }

  const test: TestFn;
  export default test;
}
