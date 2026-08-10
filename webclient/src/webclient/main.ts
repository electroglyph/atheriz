import { FitAddon } from '@xterm/addon-fit';
import { Unicode11Addon } from '@xterm/addon-unicode11';
import { WebglAddon } from '@xterm/addon-webgl';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import '../../fonts/FiraCode.css';
import { WebSocketConnection } from './connection';
import { CommandHistory } from './history';
import { launchDraw } from './launch';
import { MapPayload, WebClientElements, WireMessage } from './types';
import { SessionRecorder } from './recorder';
import { MAP_CLEAR_SEQUENCE, mergeBackgrounds, parseBackground, renderMap as renderMapText } from './map';
import { mapLayout, recordingDividerPct, resizeWidth } from './layout';
import { inputHeight, shouldClearSubmittedInput, shouldNavigateHistory, submissionFeedback } from './input';
import { formatPrompt, formatTextOutput } from './text';
import { BUFFER_FINAL_SEQUENCE } from './buffer';
import { playAudio as playAudioElement } from './audio';
import { screenReaderFeedback, settingFeedback } from './feedback';
import { shouldResetSession } from './session';
import './style.css';

const elements = getElements();
if (elements.rightTerminal.hidden) {
    elements.divider.hidden = true;
    elements.leftTerminal.style.width = '100%';
}
const history = new CommandHistory();
let screenReaderEnabled = readBooleanSetting('reader', false);
const terminalOptions = {
    convertEol: true,
    allowProposedApi: true,
    cursorInactiveStyle: 'none' as const,
    cursorStyle: readSetting('cursorstyle', 'block') as 'block' | 'underline' | 'bar',
    fontFamily: readSetting('font', '"Fira Custom", Menlo, monospace'),
    fontSize: readNumberSetting('fontsize', 19),
    cursorBlink: readBooleanSetting('cursorblink', true),
    customGlyphs: readBooleanSetting('glyphs', true),
    scrollback: readNumberSetting('scrollback', 8192),
    minimumContrastRatio: readNumberSetting('contrast', 1),
    screenReaderMode: screenReaderEnabled,
};

const left = new Terminal(terminalOptions);
const right = new Terminal({ ...terminalOptions, cursorBlink: false, cursorStyle: 'bar', screenReaderMode: screenReaderEnabled });
const leftFit = new FitAddon();
const rightFit = new FitAddon();
let mapEnabled = false;
let prompt = '';
let promptPrinted = false;
let censorInput = true;
let connected = false;
let mapPayload: MapPayload | null = null;
let pendingBackground: MapPayload['background'];
let audio: HTMLAudioElement | null = null;
let bufferQueue: string[] = [];
let bufferWriting = false;
let autosaveSetting = readBooleanSetting('autosave', false);
let commandSubmitted = false;
const recorder = new SessionRecorder();
const DIVIDER_POSITION_KEY = 'xtermDividerPos';
let lastRecordedLayout = '';

left.loadAddon(leftFit);
right.loadAddon(rightFit);
left.loadAddon(new WebLinksAddon());
right.loadAddon(new WebLinksAddon());
left.loadAddon(new Unicode11Addon());
right.loadAddon(new Unicode11Addon());
left.open(elements.leftTerminal);
right.open(elements.rightTerminal);
installWebgl(left);
installWebgl(right);
write('\x1b[1;97mxtermia2\x1b[0m terminal emulator (made with xterm.js)\n');
write('revision \x1b[1;97m14\x1b[0m\n');
write('Enter :help for a list of \x1b[1;97mxtermia2\x1b[0m commands');

const connection = new WebSocketConnection({
    onMessage: handleMessage,
    onStateChange: (state) => {
        const wasConnected = connected;
        connected = state === 'open';
        if (shouldResetSession(wasConnected, state)) resetSessionState();
        if (state === 'connecting') write('\n======== Connecting...\n');
        if (state === 'closed') {
            write('\n======== Connection lost. Retrying...\n');
            if (autosaveSetting) saveTerminalHistory();
        }
        if (state === 'open') {
            write('\n======== Connected.\n');
            fitAndReportSize();
            connection.send('screenreader', [screenReaderEnabled]);
            connection.send('client_ready');
        }
    },
    onInvalidMessage: () => write('\n======== Invalid server message.\n'),
    onError: (event) => {
        console.error('WebSocket error', event);
        write('\n======== Connection error.\n');
    },
});

const startConnection = () => {
    fitAndReportSize();
    connection.connect();
};
if (document.fonts) void document.fonts.ready.then(startConnection);
else startConnection();
installInputHandlers();
installResizeHandlers();
window.addEventListener('focus', () => elements.input.focus());
window.addEventListener('beforeunload', () => history.save());
elements.input.focus();

function getElements(): WebClientElements {
    const leftTerminal = document.getElementById('left-terminal');
    const rightTerminal = document.getElementById('right-terminal');
    const divider = document.getElementById('divider');
    const input = document.getElementById('input-box');
    if (!(leftTerminal instanceof HTMLElement) || !(rightTerminal instanceof HTMLElement) ||
        !(divider instanceof HTMLElement) || !(input instanceof HTMLTextAreaElement)) {
        throw new Error('Webclient markup is incomplete');
    }
    return { leftTerminal, rightTerminal, divider, input };
}

function readSetting(key: string, fallback: string): string {
    try {
        return window.localStorage.getItem(key) ?? fallback;
    } catch {
        return fallback;
    }
}

function readNumberSetting(key: string, fallback: number): number {
    const value = Number.parseFloat(readSetting(key, String(fallback)));
    return Number.isFinite(value) ? value : fallback;
}

function readBooleanSetting(key: string, fallback: boolean): boolean {
    const value = readSetting(key, String(fallback));
    return value === 'true' ? true : value === 'false' ? false : fallback;
}

function resetSessionState(): void {
    censorInput = true;
    prompt = '';
    promptPrinted = false;
    mapPayload = null;
    pendingBackground = undefined;
    commandSubmitted = false;
    history.reset();
    elements.input.value = '';
    elements.input.style.height = '';
    setMapVisibility(false);
}

function installInputHandlers(): void {
    const hint = document.createElement('textarea');
    hint.id = 'input-box-ghost';
    hint.readOnly = true;
    hint.tabIndex = -1;
    hint.setAttribute('aria-hidden', 'true');
    elements.input.parentElement?.insertBefore(hint, elements.input);
    const resizeInput = () => {
        elements.input.style.height = 'auto';
        elements.input.style.height = `${inputHeight(elements.input.scrollHeight)}px`;
        hint.style.height = elements.input.style.height;
        window.setTimeout(fitAndReportSize, 0);
    };
    const updateHint = () => {
        hint.value = history.getSuggestion();
        hint.scrollTop = elements.input.scrollTop;
        hint.scrollLeft = elements.input.scrollLeft;
    };
    elements.input.addEventListener('keydown', (event) => {
        if (shouldClearSubmittedInput(event.key, commandSubmitted, event.ctrlKey, event.altKey, event.metaKey)) {
            commandSubmitted = false;
            elements.input.value = '';
            history.reset();
            resizeInput();
            updateHint();
            return;
        }
        const suggestion = history.getSuggestion();
        if (suggestion && (event.key === 'Tab' || (event.key === 'ArrowRight' && elements.input.selectionStart === elements.input.value.length))) {
            event.preventDefault();
            elements.input.value = suggestion;
            history.reset();
            resizeInput();
            updateHint();
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            commandSubmitted = false;
            history.reset();
            updateHint();
            return;
        }
        if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
            if (shouldNavigateHistory(
                event.key,
                elements.input.value,
                elements.input.selectionStart,
                elements.input.selectionEnd,
                history.isNavigating(),
            )) {
                event.preventDefault();
                elements.input.value = history.navigate(event.key === 'ArrowUp' ? 'up' : 'down', elements.input.value);
                resizeInput();
                updateHint();
            }
            return;
        }
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;

        event.preventDefault();
        const command = elements.input.value;
        if (!command) {
            elements.input.value = '';
            resizeInput();
            history.reset();
            updateHint();
            const feedback = submissionFeedback(connection.send('text', ['\n']));
            if (feedback) write(feedback);
            return;
        }
        if (!censorInput) history.add(command);
        if (command.startsWith(':') && handleInternalCommand(command)) {
            elements.input.value = '';
            resizeInput();
            history.reset();
            updateHint();
            return;
        }
        const feedback = submissionFeedback(connection.send('text', [command]));
        if (feedback) {
            write(feedback);
            commandSubmitted = false;
            return;
        }
        if (!censorInput) writeSelf(command);
        elements.input.select();
        commandSubmitted = true;
    });
    elements.input.addEventListener('input', () => {
        commandSubmitted = false;
        history.reset();
        history.findCompletions(elements.input.value);
        resizeInput();
        updateHint();
    });
    elements.input.addEventListener('scroll', () => {
        hint.scrollTop = elements.input.scrollTop;
        hint.scrollLeft = elements.input.scrollLeft;
    });
    resizeInput();
}

function installResizeHandlers(): void {
    const resize = () => window.setTimeout(fitAndReportSize, 0);
    window.addEventListener('resize', resize);
    elements.divider.addEventListener('pointerdown', (event) => {
        event.preventDefault();
        const startX = event.clientX;
        const startWidth = elements.leftTerminal.getBoundingClientRect().width;
        const parentWidth = elements.leftTerminal.parentElement?.getBoundingClientRect().width ?? 1;
        const dividerWidth = elements.divider.getBoundingClientRect().width || 5;
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        document.body.style.pointerEvents = 'none';
        elements.leftTerminal.style.pointerEvents = 'none';
        elements.rightTerminal.style.pointerEvents = 'none';
        const move = (moveEvent: PointerEvent) => {
            const next = resizeWidth(startWidth, parentWidth, moveEvent.clientX - startX, dividerWidth);
            elements.leftTerminal.style.width = `${next}px`;
            leftFit.fit();
            rightFit.fit();
        };
        const stop = () => {
            window.removeEventListener('pointermove', move);
            window.removeEventListener('pointerup', stop);
            window.removeEventListener('pointercancel', stop);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            document.body.style.pointerEvents = '';
            elements.leftTerminal.style.pointerEvents = '';
            elements.rightTerminal.style.pointerEvents = '';
            saveDividerPosition();
            fitAndReportSize();
        };
        window.addEventListener('pointermove', move);
        window.addEventListener('pointerup', stop);
        window.addEventListener('pointercancel', stop);
    });
}

function fitAndReportSize(): void {
    try {
        leftFit.fit();
        if (!elements.rightTerminal.hidden) rightFit.fit();
    } catch {
        return;
    }
    if (mapEnabled) renderMap();
    recordLayout();
    if (!connected) return;
    connection.send('term_size', [left.cols, left.rows]);
    if (mapEnabled) connection.send('map_size', [right.cols, Math.max(1, right.rows - 1)]);
}

function write(text: string): void {
    left.write(text);
    recorder.output('o', text);
}

function writeSelf(text: string): void {
    write(`\x1b[38;5;220m${text}\x1b[0m\r\n`);
}

function handleMessage(message: WireMessage): void {
    switch (message.command) {
        case 'text':
            writeText(asString(message.args[0]));
            break;
        case 'prompt':
            setPrompt(asString(message.args[0]));
            break;
        case 'logged_in':
            censorInput = false;
            fitAndReportSize();
            break;
        case 'screenreader':
            applyScreenReader(asBoolean(message.args[0]), true);
            break;
        case 'map_enable':
            setMapVisibility(!screenReaderEnabled);
            if (mapEnabled) fitAndReportSize();
            break;
        case 'map_disable':
            setMapVisibility(false);
            fitAndReportSize();
            break;
        case 'get_map_size':
            if (mapEnabled) connection.send('map_size', [right.cols, Math.max(1, right.rows - 1)]);
            break;
        case 'map':
            mapPayload = asMapPayload(message.args[0]);
            if (pendingBackground) {
                mapPayload.background = mergeBackgrounds(mapPayload.background, pendingBackground);
                pendingBackground = undefined;
            }
            renderMap();
            break;
        case 'legend':
            if (mapPayload) {
                const legendData = message.args[0];
                if (typeof legendData === 'object' && legendData !== null && !Array.isArray(legendData)) {
                    const data = legendData as { area?: unknown; legend?: unknown; show_legend?: unknown };
                    mapPayload.legend = asLegend(data.legend);
                    if (typeof data.area === 'string') mapPayload.area = data.area;
                    if (typeof data.show_legend === 'boolean') mapPayload.show_legend = data.show_legend;
                } else {
                    mapPayload.legend = asLegend(legendData);
                }
                renderMap();
            }
            break;
        case 'pos':
            if (mapPayload) {
                mapPayload.pos = asPosition(message.args[0]);
                if (typeof message.args[1] === 'string') mapPayload.symbol = message.args[1];
                renderMap();
            }
            break;
        case 'buffer':
            writeBuffer(message.args);
            break;
        case 'audio':
            playAudio(asString(message.args[0]));
            break;
        case 'audio_pause':
            audio?.pause();
            break;
        case 'player_commands':
            history.setPlayerCommands(Array.isArray(message.args[0])
                ? message.args[0].filter((value): value is string => typeof value === 'string')
                : []);
            break;
        case 'launch_draw':
            launchDraw();
            break;
        case 'background':
            applyBackground(message.args[0]);
            break;
        case 'unbackground':
            pendingBackground = undefined;
            if (mapPayload) {
                mapPayload.background = undefined;
                renderMap();
            }
            break;
        default:
            write(`\r\nUnknown server command: ${message.command}\r\n`);
    }
}

function writeText(text: string): void {
    write(formatTextOutput(text, left.cols, screenReaderEnabled, prompt, promptPrinted));
    promptPrinted = prompt.length > 0;
}

function setPrompt(value: string): void {
    const oldPrompt = prompt;
    prompt = value;
    write(formatPrompt(prompt, oldPrompt, promptPrinted));
    promptPrinted = true;
}

function writeBuffer(args: unknown[]): void {
    const chunks = args.filter((value): value is string => typeof value === 'string');
    if (chunks.length === 0) return;
    bufferQueue.push(...chunks);
    flushBuffer();
}

function applyScreenReader(enabled: boolean, announce: boolean): void {
    screenReaderEnabled = enabled;
    left.options.screenReaderMode = enabled;
    right.options.screenReaderMode = enabled;
    if (enabled) {
        setMapVisibility(false);
        fitAndReportSize();
    }
    try {
        window.localStorage.setItem('reader', String(enabled));
    } catch {
        // Storage is optional.
    }
    if (announce) write(screenReaderFeedback(enabled));
}

function handleInternalCommand(command: string): boolean {
    const [name, ...args] = command.trim().split(/\s+/);
    switch (name) {
        case ':fontsize': {
            const size = Number.parseInt(args[0] ?? '', 10);
            if (!Number.isFinite(size) || size < 6 || size > 72) return reportInvalidCommand(':fontsize <6-72>');
            left.options.fontSize = size;
            right.options.fontSize = size;
            safeSet('fontsize', String(size));
            fitAndReportSize();
            write(settingFeedback('fontsize', String(size)));
            return true;
        }
        case ':help':
            write(`\r\nAvailable commands:\r\n${internalCommandHelp.join('\r\n')}\r\n`);
            return true;
        case ':reader':
            if (!connected) {
                write('\r\nNot connected to server.\r\n');
                return true;
            }
            screenReaderEnabled = !screenReaderEnabled;
            applyScreenReader(screenReaderEnabled, false);
            connection.send('screenreader', [screenReaderEnabled]);
            return true;
        case ':glyphs': {
            const enabled = !(left.options.customGlyphs ?? true);
            left.options.customGlyphs = enabled;
            right.options.customGlyphs = enabled;
            safeSet('glyphs', String(enabled));
            write(`\r\nCustom glyphs are ${enabled ? 'ON' : 'OFF'}.\r\n`);
            return true;
        }
        case ':contrast': {
            const contrast = Number.parseFloat(args[0] ?? '');
            if (!Number.isFinite(contrast) || contrast < 1 || contrast > 21) return reportInvalidCommand(':contrast <1-21>');
            left.options.minimumContrastRatio = contrast;
            right.options.minimumContrastRatio = contrast;
            safeSet('contrast', String(contrast));
            write(settingFeedback('contrast', String(contrast)));
            return true;
        }
        case ':scrollback': {
            const scrollback = Number.parseInt(args[0] ?? '', 10);
            if (!Number.isFinite(scrollback) || scrollback < 0) return reportInvalidCommand(':scrollback <number>');
            left.options.scrollback = scrollback;
            right.options.scrollback = scrollback;
            safeSet('scrollback', String(scrollback));
            write(settingFeedback('scrollback', String(scrollback)));
            return true;
        }
        case ':fontfamily':
            if (!args[0]) return reportInvalidCommand(':fontfamily <family>');
            left.options.fontFamily = args.join(' ');
            right.options.fontFamily = args.join(' ');
            safeSet('font', args.join(' '));
            fitAndReportSize();
            write(settingFeedback('fontfamily', args.join(' ')));
            return true;
        case ':save':
            saveTerminalHistory();
            return true;
        case ':record': {
            if (recorder.active) {
                write('\r\nRecording is already active.\r\n');
                return true;
            }
            const containerWidth = elements.leftTerminal.parentElement?.getBoundingClientRect().width ?? 0;
            const leftWidth = elements.leftTerminal.getBoundingClientRect().width;
            recorder.start(
                { cols: left.cols, rows: left.rows },
                { cols: right.cols, rows: right.rows },
                recordingDividerPct(mapEnabled, containerWidth, leftWidth),
                mapEnabled,
            );
            write('\r\nRecording started.\r\n');
            return true;
        }
        case ':stop': {
            const recording = recorder.stop();
            if (!recording) {
                write("\r\nRecording hasn't begun!\r\n");
            } else {
                downloadText('recording.cast', recording, 'application/json');
                write('\r\nRecording saved.\r\n');
            }
            return true;
        }
        case ':autosave':
            autosaveSetting = !autosaveSetting;
            safeSet('autosave', String(autosaveSetting));
            write(`\r\nAutosave is ${autosaveSetting ? 'ON' : 'OFF'}.\r\n`);
            return true;
        case ':reset':
            try {
                window.localStorage.clear();
            } catch {
                // Storage is optional.
            }
            history.clear();
            window.location.reload();
            return true;
        case ':draw':
            launchDraw();
            return true;
        default:
            return false;
    }
}

function reportInvalidCommand(help: string): true {
    write(`\r\nUsage: ${help}\r\n`);
    return true;
}

const internalCommandHelp = [
    ':help = This lists all available commands',
    ':fontsize <size> = Change font size. Default = 19',
    ':fontfamily <font> = Change font family. Default = "Fira Custom"',
    ':contrast <ratio> = Change minimum contrast ratio. Default = 1',
    ':reader = Toggle screen reader mode',
    ':glyphs = Toggle custom box-drawing glyphs',
    ':scrollback <rows> = Change terminal history size',
    ':save = Save terminal history',
    ':record = Start session recording',
    ':stop = Stop session recording',
    ':autosave = Toggle automatic history saving',
    ':reset = Reset client settings',
    ':draw = Open AtheriZ Draw',
];

function saveTerminalHistory(): void {
    let output = '';
    for (let index = 0; index < left.buffer.active.length; index += 1) {
        output += `${left.buffer.active.getLine(index)?.translateToString() ?? ''}\n`;
    }
    downloadText('history.txt', output, 'text/plain');
    write('\r\nTerminal history saved.\r\n');
}

function downloadText(filename: string, value: string, type: string): void {
    const blob = new Blob([value], { type });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
}

function safeSet(key: string, value: string): void {
    try {
        window.localStorage.setItem(key, value);
    } catch {
        // Storage is optional.
    }
}

function asString(value: unknown): string {
    return typeof value === 'string' ? value : '';
}

function asBoolean(value: unknown): boolean {
    return typeof value === 'boolean' ? value : value === 'true';
}

function asPosition(value: unknown): [number, number] | undefined {
    return Array.isArray(value) && typeof value[0] === 'number' && typeof value[1] === 'number' ? [value[0], value[1]] : undefined;
}

function asLegend(value: unknown): MapPayload['legend'] {
    if (!Array.isArray(value)) return [];
    return value.flatMap((entry) => {
        if (Array.isArray(entry) && typeof entry[0] === 'string' && typeof entry[1] === 'string') {
            const coords = asPosition(entry[2]);
            return [{ symbol: entry[0], desc: entry[1], coords }];
        }
        if (typeof entry === 'object' && entry !== null &&
            typeof (entry as { symbol?: unknown }).symbol === 'string' &&
            typeof (entry as { desc?: unknown }).desc === 'string') {
            const data = entry as { symbol: string; desc: string; coords?: unknown };
            return [{ symbol: data.symbol, desc: data.desc, coords: asPosition(data.coords) }];
        }
        return [];
    });
}

function asMapPayload(value: unknown): MapPayload {
    if (typeof value !== 'object' || value === null) return { map: '' };
    const data = value as Partial<MapPayload>;
    return {
        map: typeof data.map === 'string' ? data.map : '',
        pos: asPosition(data.pos),
        symbol: typeof data.symbol === 'string' ? data.symbol : undefined,
        legend: asLegend(data.legend),
        min_x: typeof data.min_x === 'number' ? data.min_x : 0,
        max_y: typeof data.max_y === 'number' ? data.max_y : 0,
        area: typeof data.area === 'string' ? data.area : undefined,
        show_legend: data.show_legend !== false,
        background: parseBackground(data.background),
    };
}

function renderMap(): void {
    if (!mapEnabled || !mapPayload) return;
    right.clear();
    recorder.output('r', MAP_CLEAR_SEQUENCE);
    const output = renderMapText(mapPayload, right.cols, right.rows);
    right.write(output);
    recorder.output('r', output);
}

function playAudio(source: string): void {
    if (!source) return;
    audio ??= new Audio();
    void playAudioElement(audio, source);
}

function flushBuffer(): void {
    if (bufferWriting || bufferQueue.length === 0) return;
    bufferWriting = true;
    const chunk = bufferQueue.shift();
    if (!chunk) {
        bufferWriting = false;
        return;
    }
    left.write(chunk, () => {
        bufferWriting = false;
        if (bufferQueue.length > 0) flushBuffer();
        else write(BUFFER_FINAL_SEQUENCE);
    });
    recorder.output('o', chunk);
}

function applyBackground(value: unknown): void {
    const background = parseBackground(value);
    if (!background) return;
    if (mapPayload) {
        mapPayload.background = mergeBackgrounds(mapPayload.background, background);
        renderMap();
    } else {
        pendingBackground = mergeBackgrounds(pendingBackground, background);
    }
}

function setMapVisibility(enabled: boolean): void {
    const changed = mapEnabled !== enabled;
    mapEnabled = enabled;
    const layout = mapLayout(enabled, readSetting(DIVIDER_POSITION_KEY, '50'));
    elements.rightTerminal.hidden = layout.rightHidden;
    elements.divider.hidden = layout.dividerHidden;
    elements.leftTerminal.style.width = layout.leftWidth;
    if (changed && recorder.active) recorder.layoutEvent(enabled ? 'show_right' : 'hide_right');
}

function saveDividerPosition(): void {
    if (!mapEnabled) return;
    const parentWidth = elements.leftTerminal.parentElement?.getBoundingClientRect().width ?? 0;
    if (parentWidth <= 0) return;
    const percentage = (elements.leftTerminal.getBoundingClientRect().width / parentWidth) * 100;
    safeSet(DIVIDER_POSITION_KEY, percentage.toFixed(2));
}

function recordLayout(): void {
    if (!recorder.active) return;
    const parentWidth = elements.leftTerminal.parentElement?.getBoundingClientRect().width ?? 0;
    const dividerPct = parentWidth > 0
        ? (elements.leftTerminal.getBoundingClientRect().width / parentWidth) * 100
        : 50;
    const layout = JSON.stringify({
        left: { cols: left.cols, rows: left.rows },
        right: { cols: right.cols, rows: right.rows },
        divider_pct: Number(dividerPct.toFixed(2)),
        right_visible: mapEnabled,
    });
    if (layout !== lastRecordedLayout) {
        recorder.resize(JSON.parse(layout));
        lastRecordedLayout = layout;
    }
}

function installWebgl(terminal: Terminal): WebglAddon | null {
    let addon: WebglAddon | null = null;
    try {
        addon = new WebglAddon();
        addon.onContextLoss(() => {
            addon?.dispose();
            addon = null;
            window.setTimeout(() => {
                try {
                    addon = new WebglAddon();
                    terminal.loadAddon(addon);
                } catch {
                    // Xterm's DOM renderer remains available as a fallback.
                }
            }, 0);
        });
        terminal.loadAddon(addon);
        return addon;
    } catch {
        return null;
    }
}
