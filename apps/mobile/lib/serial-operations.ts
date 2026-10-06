/** Keep singleton native SDK identity stable until each operation fully settles. */
export function createSerialOperations() {
  let tail: Promise<unknown> = Promise.resolve();
  return function run<T>(operation: () => Promise<T>): Promise<T> {
    const result = tail.then(operation);
    tail = result.catch(() => undefined);
    return result;
  };
}
