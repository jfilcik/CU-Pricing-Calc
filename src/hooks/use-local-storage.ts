import { useEffect, useState } from 'react';

export function useLocalStorage<T>(key: string, initialValue: T) {
  const storageKey = `cu-pricing:${key}`;
  const [value, setValue] = useState<T>(() => {
    const stored = localStorage.getItem(storageKey);
    return stored === null ? initialValue : JSON.parse(stored) as T;
  });
  const [storageError, setStorageError] = useState<Error | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(value));
    } catch (error) {
      console.error('Unable to save calculator settings in this browser.', error);
      setStorageError(new Error('Unable to save calculator settings in this browser. Check your browser storage permissions and available space.'));
    }
  }, [storageKey, value]);

  if (storageError) throw storageError;
  return [value, setValue] as const;
}
