// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { SelectionTool } from '../src/tools/SelectionTool';

describe('SelectionTool does not accumulate window listeners', () => {
  it('does not register a duplicate Escape handler per instance', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');

    // Re-instantiation must not accumulate window keydown handlers.
    new SelectionTool();
    new SelectionTool();

    const keydownRegistrations = addSpy.mock.calls.filter(
      (call) => call[0] === 'keydown',
    );

    // Proper behavior: a single shared handler (or each instance cleans up),
    // never one handler per instance that is never removed.
    expect(keydownRegistrations.length).toBeLessThanOrEqual(1);
  });
});