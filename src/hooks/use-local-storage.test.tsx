import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, renderHook, render, screen } from '@testing-library/react';
import { ErrorBoundary } from 'react-error-boundary';
import { useLocalStorage } from './use-local-storage';

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Browser-local calculator settings', () => {
  it('saves settings under a calculator-specific key and restores them after remount', () => {
    const hook = renderHook(() => useLocalStorage('volume', 1000));
    expect(hook.result.current[0]).toBe(1000);
    act(() => hook.result.current[1](2500));
    expect(localStorage.getItem('cu-pricing:volume')).toBe('2500');
    hook.unmount();
    expect(renderHook(() => useLocalStorage('volume', 1000)).result.current[0]).toBe(2500);
  });

  it('supports functional updates without losing earlier changes', () => {
    const hook = renderHook(() => useLocalStorage<Record<string, number>>('rates', {}));
    act(() => {
      hook.result.current[1](previous => ({ ...previous, input: 2 }));
      hook.result.current[1](previous => ({ ...previous, output: 0 }));
    });
    expect(JSON.parse(localStorage.getItem('cu-pricing:rates')!)).toEqual({ input: 2, output: 0 });
  });

  it.each([0, false, null])('restores an explicitly saved %j instead of the default', stored => {
    localStorage.setItem('cu-pricing:setting', JSON.stringify(stored));
    expect(renderHook(() => useLocalStorage<unknown>('setting', 'default')).result.current[0]).toBe(stored);
  });

  it('surfaces write failures through the error boundary instead of claiming settings were saved', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});
    function Settings() {
      useLocalStorage('volume', 1000);
      return <p>Saved settings</p>;
    }
    render(<ErrorBoundary fallbackRender={({ error }) => <p role="alert">{error.message}</p>}><Settings /></ErrorBoundary>);
    expect(screen.getByRole('alert').textContent).toContain('Unable to save calculator settings');
    expect(screen.queryByText('Saved settings')).toBeNull();
    expect(console.error).toHaveBeenCalled();
  });
});
