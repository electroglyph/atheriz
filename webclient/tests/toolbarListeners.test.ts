// @ts-nocheck
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { Toolbar } from '../src/ui/Toolbar';
import { UndoStack } from '../src/state/UndoStack';
import { AppState, RectMode, OvalMode, LineMode, GradientTarget, TypeStyle, SelectMode, RotateMode, FillMode, EyedropperTarget } from '../src/types';

const TOOL_IDS = [
  'tool-brush', 'tool-erase', 'tool-type', 'tool-text', 'tool-rect',
  'tool-oval', 'tool-line', 'tool-gradient', 'tool-fill', 'tool-eyedropper',
  'tool-select', 'tool-move', 'tool-rotate',
];

const SELECT_IDS = [
  'type-style-select', 'rect-mode-select', 'oval-mode-select', 'line-mode-select',
  'gradient-target-select', 'fill-mode-select', 'eyedropper-target-select',
  'select-mode-select', 'rotate-mode-select', 'font-select',
];

function makeAppState(): AppState {
  return {
    activeToolId: 'brush',
    rectMode: 'stroke' as RectMode,
    ovalMode: 'stroke' as OvalMode,
    lineMode: 'normal' as LineMode,
    gradientTarget: 'background' as GradientTarget,
    typeStyle: 'normal' as TypeStyle,
    selectedChar: '█',
    fgColor: [255, 255, 255],
    bgColor: [0, 0, 0],
    fontFamily: 'Unifont',
    gradientStops: [[0, 0, 0], [255, 255, 255]],
    selectMode: 'rect' as SelectMode,
    rotateMode: 'free' as RotateMode,
    fillMode: 'all' as FillMode,
    lineDiagonal: false,
    eyedropperTarget: 'fg' as EyedropperTarget,
  };
}

function setupDom() {
  const els: Record<string, HTMLElement> = {};
  for (const id of TOOL_IDS) {
    const el = document.createElement('button');
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  for (const id of SELECT_IDS) {
    const el = document.createElement('select');
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  for (const id of ['btn-undo', 'btn-redo', 'btn-export']) {
    const el = document.createElement('button');
    el.id = id;
    document.body.appendChild(el);
    els[id] = el;
  }
  return els;
}

describe('Toolbar window keydown listener lifecycle', () => {
  let els: Record<string, HTMLElement>;
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    els = setupDom();
    removeSpy = vi.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  it('removes its window keydown listener on destroy()', () => {
    const toolbar = new Toolbar(
      makeAppState(),
      new UndoStack(),
      () => {},
      () => {},
      () => {},
    );

    toolbar.destroy();

    const keydownRemovals = removeSpy.mock.calls.filter((call) => call[0] === 'keydown');
    expect(keydownRemovals.length).toBe(1);
  });
});
