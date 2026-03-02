class HistoryManager {
    constructor(storageKey, maxHistorySize = 2048) {
        this.storageKey = storageKey;
        this.maxSize = maxHistorySize;
        this.history = this.loadHistory();
        this.index = -1;
        this.currentInput = '';
        this.playerCommands = [];
        this.completionMatches = [];
        this.completionIndex = -1;
        this.potentialCompletions = [];
        this.updatePotentialCompletions();
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) return parsed;
            }
        } catch (e) {
            console.error("Could not load command history:", e);
        }
        return [];
    }

    saveHistory() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.history));
    }

    add(command) {
        if (!command) return;
        const idx = this.history.indexOf(command);
        if (idx !== -1) {
            this.history.splice(idx, 1);
        }
        this.history.unshift(command);
        if (this.history.length > this.maxSize) {
            this.history.pop();
        }
        this.saveHistory();
        this.updatePotentialCompletions();
        this.resetNavigation();
    }

    setPlayerCommands(commands) {
        const uniqueCommands = [...new Set([...this.playerCommands, ...commands])];
        if (uniqueCommands.length !== this.playerCommands.length) {
            this.playerCommands = uniqueCommands;
            this.updatePotentialCompletions();
        }
    }

    updatePotentialCompletions() {
        this.potentialCompletions = [...new Set([...this.history, ...this.playerCommands])];
    }

    resetNavigation() {
        this.index = -1;
        this.currentInput = '';
    }

    navigate(direction, currentVal) {
        if (this.index === -1) {
            this.currentInput = currentVal;
        }

        if (direction === 'up') {
            if (this.index < this.history.length - 1) {
                this.index++;
            }
        } else if (direction === 'down') {
            if (this.index >= 0) {
                this.index--;
            }
        }

        if (this.index === -1) {
            return this.currentInput;
        } else {
            return this.history[this.index];
        }
    }

    findCompletions(text) {
        if (text === '') {
            this.completionMatches = [];
            this.completionIndex = -1;
            return [];
        }
        this.completionMatches = this.potentialCompletions.filter(cmd =>
            cmd.startsWith(text) && cmd.length > text.length
        );

        if (this.completionMatches.length > 0) {
            this.completionIndex = 0;
        } else {
            this.completionIndex = -1;
        }
        return this.completionMatches;
    }

    getSuggestion() {
        if (this.completionIndex !== -1) {
            return this.completionMatches[this.completionIndex];
        }
        return '';
    }

    clearHistory() {
        this.history = [];
        this.saveHistory();
        this.updatePotentialCompletions();
        this.resetNavigation();
    }
}

window.addEventListener('load', () => {
    const revision = 13;
    const font = new FontFaceObserver('Fira Custom');
    font.load().then(() => {
        console.log('Font loaded.');
        // try to get options from localstorage, otherwise set the defaults
        let fsize = localStorage.getItem('fontsize');
        if (fsize === null) {
            fsize = 19;
        } else {
            fsize = parseInt(fsize);
        }
        const cstyle = localStorage.getItem('cursorstyle') || 'block';
        let cblink = localStorage.getItem('cursorblink');
        if (cblink === null) {
            cblink = true;
        } else {
            cblink = cblink === 'true';
        }
        let min_contrast = localStorage.getItem('contrast');
        if (min_contrast === null) {
            min_contrast = 1;
        } else {
            min_contrast = parseFloat(min_contrast);
        }
        let screen_reader = localStorage.getItem('reader');
        if (screen_reader === null) {
            screen_reader = false;
        } else {
            screen_reader = screen_reader === 'true';
        }
        let sback = localStorage.getItem('scrollback');
        if (sback === null) {
            sback = 8192;
        } else {
            sback = parseInt(sback);
        }
        let custom_glyphs = localStorage.getItem('glyphs');
        if (custom_glyphs === null) {
            custom_glyphs = true;
        } else {
            custom_glyphs = custom_glyphs === 'true';
        }
        let autosave_setting = localStorage.getItem('autosave');
        if (autosave_setting === null) {
            autosave_setting = false;
        } else {
            autosave_setting = autosave_setting === 'true';
        }
        const font_family = localStorage.getItem('font') || '"Fira Custom", Menlo, monospace';
        const leftTerminalEl = document.getElementById('left-terminal');
        const rightTerminalEl = document.getElementById('right-terminal');
        const dividerEl = document.getElementById('divider');
        const inputBox = document.getElementById('input-box'); // Now a textarea
        const inputContainer = document.createElement('div');
        const inputBoxGhost = document.createElement('textarea');

        function syncInputStyles() {
            const computedStyle = window.getComputedStyle(inputBox);
            ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'lineHeight', 'padding', 'borderWidth', 'textTransform', 'textIndent', 'whiteSpace', 'wordSpacing', 'backgroundColor'].forEach(prop => {
                const val = computedStyle[prop];
                if (prop === 'backgroundColor' && (val === 'transparent' || val === 'rgba(0, 0, 0, 0)')) {
                    return;
                }
                inputBoxGhost.style[prop] = val;
            });
            inputBoxGhost.style.boxSizing = 'border-box';
            inputBox.style.backgroundColor = 'transparent';
            inputBox.style.position = 'relative';
            inputBox.style.zIndex = 2; // Main input on top
            inputBoxGhost.style.position = 'absolute';
            inputBoxGhost.style.top = '0';
            inputBoxGhost.style.left = '0';
            inputBoxGhost.style.width = '100%';
            inputBoxGhost.style.height = '100%';
            inputBoxGhost.style.zIndex = 1; // Ghost input behind
            inputBoxGhost.style.pointerEvents = 'none';
            inputBoxGhost.style.resize = 'none';
        }

        inputContainer.id = 'input-container';
        inputContainer.style.position = 'relative';
        inputBox.parentNode.insertBefore(inputContainer, inputBox);
        inputContainer.appendChild(inputBox);
        inputBoxGhost.id = 'input-box-ghost';
        inputBoxGhost.setAttribute('readonly', true);
        inputBoxGhost.setAttribute('aria-hidden', 'true');
        inputBoxGhost.style.color = 'grey';
        inputContainer.appendChild(inputBoxGhost);
        syncInputStyles();

        const COMMAND_HISTORY_KEY = 'xtermia2CommandHistory';
        const historyManager = new HistoryManager(COMMAND_HISTORY_KEY);

        const terminalContainer = document.getElementById('terminal-container');

        const DIVIDER_POSITION_KEY = 'xtermDividerPos';
        let initialTextareaHeight;
        const termLeft = new Terminal({
            convertEol: true,
            cursorInactiveStyle: "none",
            allowProposedApi: true,
            disableStdin: false,
            fontFamily: font_family,
            fontSize: fsize,
            cursorBlink: cblink,
            customGlyphs: custom_glyphs,
            cursorStyle: cstyle,
            rescaleOverlappingGlyphs: false,
            scrollback: sback,
            minimumContrastRatio: min_contrast,
            screenReaderMode: screen_reader, // theme: {background: '#1e1e1e', foreground: '#d4d4d4'}
        });
        const termRight = new Terminal({
            convertEol: true,
            cursorInactiveStyle: "none",
            allowProposedApi: true,
            disableStdin: false,
            fontFamily: font_family,
            fontSize: fsize,
            cursorBlink: false,
            customGlyphs: custom_glyphs,
            cursorStyle: 'bar',
            rescaleOverlappingGlyphs: false,
            scrollback: sback,
            minimumContrastRatio: min_contrast,
            screenReaderMode: screen_reader, // theme: {background: '#1e1e1e', foreground: '#d4d4d4'}
        });

        function throttle(func, limit) {
            let inThrottle;
            return function executedFunction(...args) {
                if (!inThrottle) {
                    func.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            }
        }

        function debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }

        const throttledFit = throttle(() => {
            fitTerminals();
        }, 16);

        function redrawEverything() {
            fitTerminals();
            if (ws_ready) {
                ws.send(JSON.stringify(['term_size', [termLeft.cols, termLeft.rows], {}]));
                if (rightTerminalEl.style.display !== 'none' && map_enabled) {
                    ws.send(JSON.stringify(['map_size', [termRight.cols, termRight.rows - 1], {}]));
                }
            }
            setTimeout(() => {
                if (rightTerminalEl.style.display !== 'none' && map_enabled) {
                    composeMap();
                }
            }, 0);
        }

        const debouncedRedrawEverything = debounce(redrawEverything, 100);

        function fitTerminals() {
            try {
                if (leftTerminalEl.offsetParent !== null) {
                    fitAddonLeft.fit();
                }
                if (rightTerminalEl.offsetParent !== null) {
                    fitAddonRight.fit();
                }
            } catch (e) {
                console.error("Error fitting terminals:", e);
            }
        }

        function setInitialTextarea() {
            const oldValue = inputBox.value;
            const oldHeight = inputBox.style.height;
            inputBox.value = "X";
            inputBox.style.height = "auto";
            initialTextareaHeight = inputBox.scrollHeight;
            inputBox.value = oldValue;
            inputBox.style.height = oldHeight;
            inputBox.style.height = initialTextareaHeight + 'px';
        }


        function adjustTextareaHeight() {
            const oldHeight = inputBox.clientHeight;
            inputBox.style.height = 'auto';
            const newScrollHeight = Math.max(inputBox.scrollHeight, initialTextareaHeight);
            inputBox.style.height = newScrollHeight + 'px';
            if (inputBoxGhost) {
                inputBoxGhost.style.height = inputBox.style.height;
            }
            const newHeight = inputBox.clientHeight;
            if (newHeight !== oldHeight) {
                redrawEverything();
            }
        }

        function loadDividerPosition() {
            const savedPercentage = localStorage.getItem(DIVIDER_POSITION_KEY);
            if (savedPercentage) {
                const percent = parseFloat(savedPercentage);
                if (!isNaN(percent) && percent > 5 && percent < 95) {
                    leftTerminalEl.style.width = percent + '%';
                } else {
                    leftTerminalEl.style.width = '50%';
                }
            } else {
                leftTerminalEl.style.width = '50%';
            }
        }

        function saveDividerPos() {
            if (rightTerminalEl.style.display !== 'none') {
                const containerWidth = terminalContainer.offsetWidth;
                const leftWidth = leftTerminalEl.offsetWidth;
                if (containerWidth > 0) {
                    const percentage = (leftWidth / containerWidth) * 100;
                    localStorage.setItem(DIVIDER_POSITION_KEY, percentage.toFixed(2));
                }
            }
        }

        function showRightPane() {
            if (rightTerminalEl.style.display === 'none') {
                rightTerminalEl.style.display = '';
                dividerEl.style.display = '';
                loadDividerPosition();
                redrawEverything();
            }
        }

        function hideRightPane() {
            if (rightTerminalEl.style.display !== 'none') {
                rightTerminalEl.style.display = 'none';
                dividerEl.style.display = 'none';
                leftTerminalEl.style.width = '100%';
                redrawEverything();
            }
        }

        setInitialTextarea();
        loadDividerPosition();

        let isCommandSubmitted = false;
        inputBox.addEventListener('input', () => {
            isCommandSubmitted = false;
            adjustTextareaHeight();
            historyManager.resetNavigation();
            historyManager.findCompletions(inputBox.value);
            updateCompletionHint();
        });

        inputBox.addEventListener('scroll', () => {
            if (inputBoxGhost) {
                inputBoxGhost.scrollTop = inputBox.scrollTop;
                inputBoxGhost.scrollLeft = inputBox.scrollLeft;
            }
        });

        let isResizing = false;
        dividerEl.addEventListener('mousedown', function (e) {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            document.body.style.pointerEvents = 'none';
            leftTerminalEl.style.pointerEvents = 'none';
            rightTerminalEl.style.pointerEvents = 'none';
            e.preventDefault();
        });

        document.addEventListener('mousemove', function (e) {
            if (!isResizing) return;
            let newLeftWidth = e.clientX - terminalContainer.getBoundingClientRect().left;
            const containerWidth = terminalContainer.offsetWidth;
            const dividerWidth = dividerEl.offsetWidth;
            const minTerminalWidth = 50;

            if (newLeftWidth < minTerminalWidth) newLeftWidth = minTerminalWidth;
            if (newLeftWidth > containerWidth - minTerminalWidth - dividerWidth) {
                newLeftWidth = containerWidth - minTerminalWidth - dividerWidth;
            }
            if (newLeftWidth > 0 && newLeftWidth < (containerWidth - dividerWidth)) {
                leftTerminalEl.style.width = newLeftWidth + 'px';
                throttledFit();
            }
        });

        document.addEventListener('mouseup', function () {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
                document.body.style.userSelect = 'auto';
                document.body.style.pointerEvents = 'auto';
                leftTerminalEl.style.pointerEvents = 'auto';
                rightTerminalEl.style.pointerEvents = 'auto';
                saveDividerPos();
                redrawEverything();
            }
        });

        let recording_start = 0;
        let recording_buffer = '';
        let recording = false;
        let recording_header = {
            "version": 2, "width": 80, "height": 24, "timestamp": 0, "duration": 0, "title": "xtermia2 recording"
        };
        wrapWrite('\x1b[1;97mxtermia2\x1b[0m terminal emulator (made with xterm.js)\n');
        wrapWrite('revision \x1b[1;97m' + revision + '\x1b[0m\n');
        wrapWrite('Enter :help for a list of \x1b[1;97mxtermia2\x1b[0m commands')
        let player_commands = [];
        const commands = new Map();
        commands.set(':help', [help, ':help = This lists all available commands']);
        commands.set(':fontsize', [fontsize, ':fontsize [size] = Change font size to [size]. Default = 19']);
        commands.set(':fontfamily', [fontfamily, ':fontfamily [font] = Change font family. Default = "Fira Custom"']);
        commands.set(':contrast', [contrast, ':contrast [ratio] = Change minimum contrast ratio, 21 = black and white. Default = 1']);
        commands.set(':reader', [reader, ':reader = Toggle screenreader mode for NVDA or VoiceOver. Default = off']);
        // commands.set(':cursorstyle', [cursorstyle, ':cursorstyle [block,underline,bar] = Change cursor style. Default = block']);
        // commands.set(':cursorblink', [cursorblink, ':cursorblink = Toggle cursor blink. Default = on']);
        commands.set(':glyphs', [glyphs, ':glyphs = Toggle custom glyphs (fixes some box-drawing glyphs). Default = on']);
        commands.set(':scrollback', [scrollback, ':scrollback [rows] = Rows of terminal history. Default = 8192']);
        commands.set(':record', [record, ':record = Begin asciinema recording (share at http://terminoid.com/).']);
        commands.set(':stop', [stop, ':stop = Stop asciinema recording and save JSON file.']);
        commands.set(':save', [save, ':save = Save terminal history to history.txt']);
        commands.set(':autosave', [autosave, ':autosave = Toggle autosave. If enabled, history will be saved on connection close. Default = off']);
        commands.set(':reset', [reset_command, ':reset = Clear local storage and reset settings to default']);
        for (const [key, value] of commands) {
            historyManager.setPlayerCommands([key]);
        }

        function help(arg) {
            let update = 'Available commands:\n';
            for (const [key, value] of commands) {
                update += value[1] + '\n';
            }
            wrapWrite(update);
        }

        function reset_command(arg) {
            localStorage.clear();
            historyManager.clearHistory();
            termLeft.options.fontSize = 19;
            termLeft.options.cursorStyle = 'block';
            termLeft.options.cursorBlink = true;
            termLeft.options.screenReaderMode = false;
            termLeft.options.minimumContrastRatio = 1;
            termLeft.options.scrollback = 8192;
            termLeft.options.customGlyphs = true;
            autosave_setting = false;
            termLeft.options.fontFamily = '"Fira Code", Menlo, monospace';
            termRight.options.fontSize = 19;
            termRight.options.cursorStyle = 'block';
            termRight.options.cursorBlink = true;
            termRight.options.screenReaderMode = false;
            termRight.options.minimumContrastRatio = 1;
            termRight.options.scrollback = 8192;
            termRight.options.customGlyphs = true;
            termRight.options.fontFamily = '"Fira Code", Menlo, monospace';
            fitTerminals()
        }

        function fontfamily(arg) {
            try {
                termLeft.options.fontFamily = arg;
                termRight.options.fontFamily = arg;
                fitTerminals()
                localStorage.setItem("font", arg);
                syncInputStyles();
                wrapWriteln('Font changed to: ' + arg + '.');
                wrapWriteln('If this looks terrible, enter :reset to go back to default font.');
            } catch (e) {
                console.error(e);
                wrapWriteln(e);
                termLeft.options.fontFamily = '"Fira Code", Menlo, monospace';
                termRight.options.fontFamily = '"Fira Code", Menlo, monospace';
            }
        }

        function glyphs(arg) {
            custom_glyphs = !custom_glyphs;
            termLeft.options.customGlyphs = custom_glyphs;
            termRight.options.customGlyphs = custom_glyphs;
            if (custom_glyphs) {
                wrapWriteln('Custom glyphs are ON.');
                localStorage.setItem("glyphs", "true");
            } else {
                wrapWriteln('Custom glyphs are OFF.');
                localStorage.setItem("glyphs", "false");
            }
        }

        function scrollback(arg) {
            termLeft.options.scrollback = parseInt(arg);
            termRight.options.scrollback = parseInt(arg);
            localStorage.setItem("scrollback", arg);
        }

        function reader(arg) {
            if (ws_ready) {
                screen_reader = !screen_reader;
                if (screen_reader) {
                    termLeft.options.screenReaderMode = true;
                    termRight.options.screenReaderMode = true;
                    localStorage.setItem("reader", "true");
                } else {
                    termLeft.options.screenReaderMode = false;
                    termRight.options.screenReaderMode = false;
                    localStorage.setItem("reader", "false");
                }
                ws.send(JSON.stringify(['screenreader', [screen_reader], {}]));
            } else {
                wrapWriteln("Not connected to server.");
            }
        }

        function contrast(arg) {
            termLeft.options.minimumContrastRatio = parseFloat(arg);
            termRight.options.minimumContrastRatio = parseFloat(arg);
            localStorage.setItem("contrast", arg);
            wrapWriteln('Minimum contrast ratio is: ' + arg + '.');
        }

        function fontsize(arg) {
            termLeft.options.fontSize = parseInt(arg);
            termRight.options.fontSize = parseInt(arg);
            fitTerminals()
            syncInputStyles();
            localStorage.setItem("fontsize", arg);
            wrapWriteln('Font size is: ' + arg + '.');
        }

        function save(arg) {
            let h = '';
            for (let i = 0; i < termLeft.buffer.active.length; i++) {
                h += termLeft.buffer.active.getLine(i).translateToString() + '\n';
            }
            saveBlob('history.txt', h);
            wrapWriteln('Terminal history saved.');
        }

        function autosave(arg) {
            autosave_setting = !autosave_setting;
            if (autosave_setting) {
                localStorage.setItem('autosave', 'true');
                wrapWriteln('Autosave is ON.');
            } else {
                localStorage.setItem('autosave', 'false');
                wrapWriteln('Autosave is OFF.');
            }
        }

        function record(arg) {
            // #TODO: reimplement for both terminals, make custom recording format
            recording_start = Date.now();
            recording_header.width = term.cols;
            recording_header.height = term.rows;
            recording_header.timestamp = Math.round(recording_start / 1000);
            recording = true;
        }

        function addRecord(str) {
            const time = (Date.now() - recording_start) / 1000;
            recording_buffer += JSON.stringify([time, "o", str]) + '\n';
        }

        function wrapWrite(d, f) {
            // wrap all term.write() calls with this to enable recording
            termLeft.write(d, f);
            if (recording) {
                addRecord(d);
            }
        }

        function wrapWriteln(d, f) {
            // wrap all term.writeln() calls with this to enable recording
            termLeft.writeln(d, f);
            if (recording) {
                addRecord(d);
            }
        }

        function stop(arg) {
            if (recording) {
                recording = false;
                recording_header.duration = (Date.now() - recording_start) / 1000;
                saveBlob('recording.cast', JSON.stringify(recording_header) + '\n' + recording_buffer);
            } else {
                wrapWriteln("Recording hasn't begun!");
            }
        }

        function handle_command(command) {
            for (const [key, value] of commands) {
                if (command.startsWith(key)) {
                    if (command.includes(' ')) {
                        value[0](command.substring(command.indexOf(' ') + 1));
                    } else {
                        value[0]();
                    }
                    return true;
                }
            }
            return false;
        }

        function saveBlob(filename, data) {
            const blob = new Blob([data], { type: 'text/csv' });
            if (window.navigator.msSaveOrOpenBlob) {
                window.navigator.msSaveBlob(blob, filename);
            } else {
                const elem = window.document.createElement('a');
                elem.href = window.URL.createObjectURL(blob);
                elem.download = filename;
                document.body.appendChild(elem);
                elem.click();
                document.body.removeChild(elem);
            }
        }

        let ws_ready = false;
        let ws = new WebSocket(wsurl + '?' + csessid);
        // const unicode11Addon = new Unicode11Addon.Unicode11Addon();
        // term.loadAddon(unicode11Addon);
        // term.unicode.activeVersion = '11';
        const webglAddonLeft = new WebglAddon.WebglAddon();
        webglAddonLeft.onContextLoss(e => {
            webglAddonLeft.dispose();
        });
        const webglAddonRight = new WebglAddon.WebglAddon();
        webglAddonRight.onContextLoss(e => {
            webglAddonRight.dispose();
        });
        termLeft.loadAddon(webglAddonLeft);
        termRight.loadAddon(webglAddonRight);
        const weblinksAddonLeft = new WebLinksAddon.WebLinksAddon();
        const weblinksAddonRight = new WebLinksAddon.WebLinksAddon();
        termLeft.loadAddon(weblinksAddonLeft);
        termRight.loadAddon(weblinksAddonRight);
        const fitAddonLeft = new FitAddon.FitAddon();
        const fitAddonRight = new FitAddon.FitAddon();
        termLeft.loadAddon(fitAddonLeft);
        termRight.loadAddon(fitAddonRight);
        termLeft.open(leftTerminalEl);
        termRight.open(rightTerminalEl);
        let audio = new Audio();
        let map_enabled = false;
        // let map_column = 0;
        // let map_max_width = 0;
        hideRightPane();

        setTimeout(redrawEverything, 0);

        let prompt = '';
        let prompt_len = 0;
        let prompt_is_printed = false;
        // let index = -1;
        // let last_dir = 0; // 0 = none, 1 = down, 2 = up
        // let interactive_mode = false;
        // let cursor_x = 0;  // these are used during interactive mode to keep track of relative cursor position
        // let cursor_y = 0;
        // let self_paste = false; // did we send the paste? or is the right-click menu being used?
        // let self_write = false; // if true, don't do onData events
        let enter_pressed = false;
        let censor_input = true; // until login, don't echo input commands so that password isn't leaked
        let map = [];  // current map, split into lines
        let plain_map = []; // cached plain map from server (no dynamic items)
        let map_min_x = 0; // map viewport offset X
        let map_max_y = 0; // map viewport offset Y
        let current_area_name = "Legend"; // Current area name for legend header
        let player_symbol = ''; // current player symbol
        let legend_entries = []; // cached legend entries
        let new_map = []; // map after resize, or the original map if resize not needed
        let pos = [];  // last position sent for map
        let legend = [];  // current map legend, split into lines
        let show_legend = true;  // whether to render the legend box
        let map_width = 0;
        let map_height = 0;
        let new_map_width = 0;
        let new_map_height = 0;
        const ansi_color_regex = /\x1B\[[0-9;]+m/g;
        const grey = '\x1B[38;5;243m';
        const reset = '\x1B[0m';
        const command_color = '\x1B[38;5;220m';
        const highlight = '\x1B[48;5;24m';
        const default_color = '\x1B[38;2;190;190;190m';
        const default_color_reset = '\x1B[0m\x1B[38;2;190;190;190m';
        const white = '\x1B[37m';
        let cursor_pos = 0;
        let command = '';

        function updateCompletionHint() {
            const suggestion = historyManager.getSuggestion();
            if (suggestion) {
                const currentInput = inputBox.value;
                if (suggestion.startsWith(currentInput) && suggestion.length > currentInput.length) {
                    inputBoxGhost.value = suggestion;
                    inputBoxGhost.scrollTop = inputBox.scrollTop;
                    inputBoxGhost.scrollLeft = inputBox.scrollLeft;
                } else {
                    inputBoxGhost.value = '';
                }
            } else {
                inputBoxGhost.value = '';
            }
        }

        function acceptCompletion() {
            const suggestion = historyManager.getSuggestion();
            if (suggestion) {
                inputBox.value = suggestion;
                historyManager.resetNavigation();
                historyManager.findCompletions(inputBox.value);
                updateCompletionHint();
                adjustTextareaHeight();
                inputBox.focus();
                inputBox.setSelectionRange(inputBox.value.length, inputBox.value.length);
            }
        }

        inputBox.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
                const isFullySelected = inputBox.selectionStart === 0 && inputBox.selectionEnd === inputBox.value.length && inputBox.value.length > 0;
                const isAtStart = inputBox.selectionStart === 0 && inputBox.selectionEnd === 0;

                // If input is empty, fully selected, or we are already navigating history, scroll history
                // OR if it's ArrowUp and we are NOT yet navigating but are at the start of the input
                if (inputBox.value === '' || isFullySelected || historyManager.index !== -1 || (e.key === 'ArrowUp' && isAtStart)) {
                    e.preventDefault();
                    inputBox.value = historyManager.navigate(e.key === 'ArrowUp' ? 'up' : 'down', inputBox.value);
                    inputBoxGhost.value = '';
                    adjustTextareaHeight();
                    requestAnimationFrame(() => {
                        inputBox.setSelectionRange(inputBox.value.length, inputBox.value.length);
                    });
                    return;
                }
            }

            const hasCompletion = historyManager.getSuggestion() !== '';
            if (hasCompletion) {
                if (e.key === 'Tab' || (e.key === 'ArrowRight' && inputBox.selectionStart === inputBox.value.length)) {
                    e.preventDefault();
                    acceptCompletion();
                    return;
                }
                if (e.key === 'Escape') {
                    e.preventDefault();
                    historyManager.resetNavigation(); // Reset navigation if escaping
                    historyManager.findCompletions(''); // Clear completions
                    updateCompletionHint();
                    return;
                }
            }

            if (isCommandSubmitted && e.key.length === 1 && !e.ctrlKey && !e.altKey) {
                isCommandSubmitted = false;
                inputBox.value = '';
                historyManager.resetNavigation();
                historyManager.findCompletions('');
                updateCompletionHint();
                return;
            }

            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                command = inputBox.value;
                if (command && !censor_input) {
                    historyManager.add(command);
                }

                historyManager.resetNavigation();
                historyManager.findCompletions('');
                updateCompletionHint();

                enter_pressed = true;
                if (command) {
                    let internal = false;
                    if (command[0] === ':') {
                        // wrapWriteln(command_color + command + reset);
                        internal = handle_command(command);
                    }
                    if (!internal) {
                        ws.send(JSON.stringify(['text', [command], {}]));
                        if (!censor_input) {
                            wrapWriteln(command_color + command + reset);
                        }
                        inputBox.select();
                        isCommandSubmitted = true;
                    }
                } else {
                    ws.send(JSON.stringify(['text', ['\n'], {}]));
                }
                adjustTextareaHeight();
            }
        });

        function writeMap() {
            termRight.write('\x1b[2J\x1b[3J\x1b[H');
            if (!new_map || new_map.length === 0 || termRight.rows === 0) {
                return;
            }
            const has_legend = legend && legend.length > 0 && legend[0] !== '';
            let legend_height = 0;
            let legend_max_width = 0;

            if (has_legend) {
                legend_height = legend.length;
                for (const line of legend) {
                    const stripped_len = line.replace(ansi_color_regex, '').length;
                    if (stripped_len > legend_max_width) {
                        legend_max_width = stripped_len;
                    }
                }
            }

            const content_height = new_map_height + (has_legend ? 1 + legend_height : 0);
            let start_row = Math.floor((termRight.rows - content_height) / 2) + 1;
            start_row = Math.max(1, start_row);
            let update = '';
            let current_row = start_row;
            let map_horizontal_padding = Math.floor((termRight.cols - new_map_width) / 2) + 1;
            map_horizontal_padding = Math.max(1, map_horizontal_padding);

            for (const line of new_map) {
                update += `\x1b[${current_row};${map_horizontal_padding}H` + line;
                current_row++;
            }

            if (has_legend) {
                current_row++;
                let legend_horizontal_padding = Math.floor((termRight.cols - legend_max_width) / 2) + 1;
                legend_horizontal_padding = Math.max(1, legend_horizontal_padding);

                for (const line of legend) {
                    update += `\x1b[${current_row};${legend_horizontal_padding}H` + line;
                    current_row++;
                }
            }
            termRight.write(reset + update);
        }

        ws.onopen = function () {
            wrapWrite('\n======== Connected.\n');
            ws_ready = true;
            ws.send(JSON.stringify(['term_size', [termLeft.cols, termLeft.rows], {}]));
            ws.send(JSON.stringify(['screenreader', [screen_reader], {}]));
            ws.send(JSON.stringify(['client_ready', [], {}]));
        };

        ws.onclose = function () {
            wrapWrite('\n======== Connection lost.\n');
            ws_ready = false;
            if (autosave_setting) {
                save();
            }
        };

        function getRawIndex(text, visualIndex) {
            let idx = 0;
            let vIdx = 0;
            let isAnsi = false;
            while (idx < text.length && vIdx < visualIndex) {
                if (text[idx] === '\x1b') {
                    isAnsi = true;
                    idx++;
                } else if (isAnsi) {
                    if (text[idx] === 'm' || text[idx] === 'K') {
                        isAnsi = false;
                    }
                    idx++;
                } else {
                    vIdx++;
                    idx++;
                }
            }
            // Skip any ANSI codes immediately preceding the character
            while (idx < text.length) {
                if (text[idx] === '\x1b') {
                    // Check if it's a color code start
                    let end = idx + 1;
                    while (end < text.length && text[end] !== 'm' && text[end] !== 'K') end++;
                    if (end < text.length) {
                        // It's an ansi code, we can include it in the "before" part (by incrementing idx)? 
                        // No, getRawIndex returns the start of the "visual character".
                        // If we skip codes here, we are effectively saying the visual character starts AFTER the codes.
                        // Which implies we WANT to insert AFTER the codes. 
                        // e.g. [Red]A. If we insert X, we want [Red]XA -> Red X, Red A?
                        // Or if X has its own color: [Red][Blue]X[Reset]A.
                        // So we should step over them.
                        idx = end + 1;
                    } else {
                        break; // Malformed or incomplete
                    }
                } else {
                    break;
                }
            }
            return idx;
        }

        function composeMap() {
            if (!plain_map || plain_map.length === 0) return;

            // Allow plain_map to be used as is if no composition needed
            let working_map = [...plain_map];

            // Helper: get raw index for visual position, WITHOUT skipping preceding ANSI codes
            const getRawIndexNoSkip = (text, visualIndex) => {
                let idx = 0;
                let vIdx = 0;
                let isAnsi = false;
                while (idx < text.length && vIdx < visualIndex) {
                    if (text[idx] === '\x1b') {
                        isAnsi = true;
                        idx++;
                    } else if (isAnsi) {
                        if (text[idx] === 'm' || text[idx] === 'K') {
                            isAnsi = false;
                        }
                        idx++;
                    } else {
                        vIdx++;
                        idx++;
                    }
                }
                return idx;
            };

            // Helper to place char
            const placeChar = (x, y, sym) => {
                if (y >= 0 && y < working_map.length) {
                    let line = working_map[y];
                    // We need to find the raw string index corresponding to visual x
                    // Since lines might contain ANSI from the server (walls etc)

                    // strip ANSI to check bounds
                    const stripped = line.replace(ansi_color_regex, '');
                    if (x >= 0 && x < stripped.length) {
                        // Find raw start index, skipping ANSI codes that precede the char
                        const startIdx = getRawIndex(line, x);
                        // Find raw end index WITHOUT skipping ANSI codes (so we don't eat the next char's codes)
                        const endIdx = getRawIndexNoSkip(line, x + 1);

                        // Reconstruct line
                        working_map[y] = line.substring(0, startIdx) + sym + line.substring(endIdx);
                    }
                }
            };

            // Group and Colorize Legend Entries by Coordinate
            let processedEntries = [];
            if (legend_entries && Array.isArray(legend_entries)) {
                // First pass: assign colors to entries based on symbol (duplicate symbols get unique colors)
                let seenSymbols = {}; // { stripped_symbol: next_hue }
                let colorizedEntries = [];

                for (const entry of legend_entries) {
                    let sym = entry[0];
                    const desc = entry[1];
                    const coords = entry[2];

                    if (!sym) {
                        console.warn("Invalid legend entry encountered (missing symbol):", entry);
                        continue;
                    }

                    const strippedSym = sym.replace(ansi_color_regex, '');

                    if (seenSymbols.hasOwnProperty(strippedSym)) {
                        // Duplicate symbol found - assign a unique color
                        let hue = seenSymbols[strippedSym];
                        let rgb = hslToRgb(hue / 360, 1.0, 0.5);
                        sym = wrapTrueColor(strippedSym, rgb[0], rgb[1], rgb[2]);

                        // Update next hue
                        let nextHue = hue + 57.0;
                        if (nextHue > 360) nextHue %= 360;
                        seenSymbols[strippedSym] = nextHue;
                    } else {
                        // First time seeing this symbol - initialize for next sighting
                        seenSymbols[strippedSym] = 131.0;

                        if (!sym.endsWith('\x1b[0m')) {
                            sym += '\x1b[0m';
                        }
                    }
                    colorizedEntries.push([sym, desc, coords]);
                }

                // Second pass: group colorized entries by coordinate
                const groups = {};
                const noCoordEntries = [];

                for (const entry of colorizedEntries) {
                    const coords = entry[2];

                    if (coords) {
                        const key = coords[0] + ',' + coords[1];
                        if (!groups[key]) groups[key] = [];
                        groups[key].push(entry);
                    } else {
                        noCoordEntries.push(entry);
                    }
                }

                // Process grouped entries
                for (const [key, entries] of Object.entries(groups)) {
                    if (entries.length === 1) {
                        // Single entry at this location - keep as is
                        processedEntries.push(entries[0]);
                    } else {
                        // Multiple entries at same location - combine them
                        const strippedSym = entries[0][0].replace(ansi_color_regex, '');

                        // Count descriptions
                        const descCounts = {};
                        for (const e of entries) {
                            descCounts[e[1]] = (descCounts[e[1]] || 0) + 1;
                        }

                        // Build combined description
                        const descParts = [];
                        for (const [desc, count] of Object.entries(descCounts)) {
                            if (count > 1) {
                                descParts.push(`${desc} (${count})`);
                            } else {
                                descParts.push(desc);
                            }
                        }
                        let combinedDesc = descParts.join(', ');

                        // Truncate if too long (half of terminal width)
                        const maxDescLen = Math.floor(termRight.cols / 2);
                        if (combinedDesc.length > maxDescLen) {
                            combinedDesc = combinedDesc.substring(0, maxDescLen - 3) + '...';
                        }

                        // Extract colors from colorized entries
                        let bgColor = null;
                        let fgColor = null;
                        for (const e of entries) {
                            const color = extractTrueColorFg(e[0]);
                            if (color) {
                                if (!bgColor) {
                                    bgColor = color;
                                } else if (!fgColor) {
                                    fgColor = color;
                                    break;
                                }
                            }
                        }

                        // Apply colors: first fg becomes bg, second fg (or grey) becomes fg
                        let newSym;
                        const bg = bgColor || { r: 30, g: 60, b: 120 }; // dark blue default
                        const fg = fgColor || { r: 190, g: 190, b: 190 }; // light grey default
                        newSym = wrapTrueColorFgBg(strippedSym, fg.r, fg.g, fg.b, bg.r, bg.g, bg.b);

                        processedEntries.push([newSym, combinedDesc, entries[0][2]]);
                    }
                }

                // Add entries without coordinates
                for (const entry of noCoordEntries) {
                    processedEntries.push(entry);
                }
            }


            // Place legend items (using processed colored symbols)
            if (processedEntries && Array.isArray(processedEntries)) {
                for (const entry of processedEntries) {
                    const sym = entry[0];
                    const coords = entry[2];
                    if (coords) {
                        const rel_x = coords[0] - map_min_x;
                        const rel_y = map_max_y - coords[1];
                        placeChar(rel_x, rel_y, sym);
                    }
                }
            }

            // Place Player
            if (pos && pos.length >= 2 && player_symbol) {
                let pSym = player_symbol;
                // If player symbol has no ANSI color codes, give it explicit white color
                // to prevent naked reset from affecting adjacent colored symbols
                if (!pSym.match(ansi_color_regex)) {
                    pSym = wrapTrueColor(pSym, 255, 255, 255);
                } else if (!pSym.endsWith('\x1b[0m')) {
                    pSym += '\x1b[0m';
                }
                placeChar(pos[0], pos[1], pSym);
            }

            map = working_map;

            // Calculate map dimensions
            map_height = map.length;
            let max_w = 0;
            for (const line of map) {
                const slen = line.replace(ansi_color_regex, '').length;
                if (slen > max_w) max_w = slen;
            }
            map_width = max_w;

            // Update Legend Display
            // We need to merge custom legend items with the player entry
            let displayItems = [];
            // player_symbol is passed as argument validation to renderLegend, which adds it.
            if (processedEntries && Array.isArray(processedEntries)) {
                for (const entry of processedEntries) {
                    displayItems.push({ symbol: entry[0], desc: entry[1] });
                }
            }

            // Adaptive legend height: try to use up to 1/3 of the terminal height
            if (show_legend) {
                const adaptiveLegendHeight = Math.max(5, Math.floor(termRight.rows / 3));
                const renderedLegend = window.renderLegend(current_area_name, displayItems, termRight.cols, adaptiveLegendHeight, player_symbol);
                legend = renderedLegend;
            } else {
                legend = [];
            }

            // Trigger redraw
            resizeMap(pos);
            writeMap();
        }

        function ANSIsubstring(input, start, end) {
            // get substring of ANSI string while ignoring control codes
            let pos = 0;
            let start_pos = 0;
            let end_pos = 0;
            let is_ansi = false;
            let ansi_seen = false;
            for (let i = 0; i < input.length; i++) {
                if (pos === end) {
                    break;
                }
                if (is_ansi) {
                    if (input[i] === 'm' || input[i] === 'K') {
                        is_ansi = false;
                    }
                } else {
                    if (input[i] === '\x1b') {
                        is_ansi = true;
                        ansi_seen = true;
                    } else {
                        if (pos < start) {
                            start_pos = i + 1;
                        }
                        if (pos < end) {
                            end_pos = i + 2;
                        }
                        pos++;
                    }
                }
            }
            if (start_pos <= end_pos) {
                if (ansi_seen) {
                    // append ansi reset in case we chop an ANSI string
                    return input.substring(start_pos, end_pos) + reset;
                } else {
                    return input.substring(start_pos, end_pos);
                }
            }
            return '';
        }

        function resizeMap(pos) {
            if (!map || map.length === 0 || !pos || pos.length < 2) {
                new_map = [];
                new_map_width = 0;
                new_map_height = 0;
                return;
            }
            const has_legend = legend && legend.length > 0 && legend[0] !== '';
            const view_width = termRight.cols;
            const legend_height = has_legend ? legend.length : 0;
            const separator_height = has_legend ? 1 : 0;
            const available_height = termRight.rows - legend_height - separator_height;
            const view_height = Math.max(1, available_height);

            // if whole map fits, no resizing needed
            if (map_width <= view_width && map_height <= view_height) {
                new_map = [...map];
                new_map_width = map_width;
                new_map_height = map_height;
                return;
            }

            const player_x = pos[0];
            const player_y = pos[1];
            // calculate vertical viewport centered on player
            let y_start = 0;
            let actual_view_height = Math.min(view_height, map_height);
            if (map_height > view_height) {
                const half_height = Math.floor(view_height / 2);
                y_start = player_y - half_height;
                // clamp to valid range
                y_start = Math.max(0, y_start);
                y_start = Math.min(y_start, map_height - view_height);
            }

            // calculate horizontal viewport centered on player
            let x_start = 0;
            let actual_view_width = Math.min(view_width, map_width);
            if (map_width > view_width) {
                const half_width = Math.floor(view_width / 2);
                x_start = player_x - half_width;
                // clamp to valid range
                x_start = Math.max(0, x_start);
                x_start = Math.min(x_start, map_width - view_width);
            }

            const y_end = y_start + actual_view_height;
            const vertically_sliced_map = map.slice(y_start, y_end);

            const temp_new_map = [];
            const x_end = x_start + actual_view_width;
            for (const line of vertically_sliced_map) {
                temp_new_map.push(ANSIsubstring(line, x_start, x_end));
            }
            new_map = temp_new_map;
            new_map_height = new_map.length;

            let max_len = 0;
            for (const line of new_map) {
                const stripped_line = line.replace(ansi_color_regex, '');
                if (stripped_line.length > max_len) {
                    max_len = stripped_line.length;
                }
            }
            new_map_width = max_len;
        }

        function wrapText(text, width) {
            if (!text) return text;
            let result = '';
            let currentLineLength = 0;
            let currentColor = '';
            const words = text.split(/(\s+)/);

            for (let i = 0; i < words.length; i++) {
                const word = words[i];
                if (word.length === 0) continue;

                let nextColor = currentColor;
                const codes = word.match(ansi_color_regex);
                if (codes) {
                    for (const code of codes) {
                        if (code === '\x1B[0m') {
                            nextColor = '';
                        } else {
                            nextColor = code;
                        }
                    }
                }

                if (word.includes('\n')) {
                    result += word;
                    const lastNewlineIndex = word.lastIndexOf('\n');
                    const afterNewline = word.substring(lastNewlineIndex + 1).replace(ansi_color_regex, '');
                    currentLineLength = afterNewline.length;
                    currentColor = nextColor;
                    continue;
                }

                const visibleWord = word.replace(ansi_color_regex, '');
                const wordLength = visibleWord.length;

                if (currentLineLength + wordLength > width) {
                    if (word.match(/^\s+$/)) {
                        if (currentLineLength > 0) {
                            result += reset + '\n' + currentColor;
                            currentLineLength = 0;
                        }
                    } else {
                        if (currentLineLength > 0) {
                            result += reset + '\n' + currentColor;
                            currentLineLength = 0;
                        }
                        result += word;
                        currentLineLength += wordLength;
                    }
                } else {
                    result += word;
                    currentLineLength += wordLength;
                }
                currentColor = nextColor;
            }
            return result;
        }

        function onText(input) {
            if (!screen_reader) {
                if (input.charAt(0) !== '\x1B') {
                    input = default_color + input;
                }
                input = wrapText(input, termLeft.cols);
                input = input.replaceAll(reset, default_color_reset);
                input = input.replaceAll(white, default_color);
            }

            if (prompt_is_printed) {
                wrapWrite('\r' + ' '.repeat(prompt_len) + '\r' + reset + input + reset + prompt);
            } else {
                wrapWrite(reset + input + reset + prompt);
            }
            prompt_is_printed = prompt !== '';
        }

        const sleep = (delay) => new Promise((resolve) => setTimeout(resolve, delay))

        async function onMessage(e) {
            let msg = JSON.parse(e.data);
            switch (msg[0]) {
                case 'text':
                    onText(msg[1][0]);
                    break;
                // case 'raw_text':  // default text messages get \n appended to them before being sent, this doesn't
                //     writeSelf(msg[1][0]);
                //     break;
                case 'prompt':
                    const old_prompt_len = prompt_len;
                    prompt = msg[1][0];
                    prompt_len = msg[1][0].replace(ansi_color_regex, '').length;
                    if (prompt_is_printed) { // replace prompt
                        wrapWrite('\r' + ' '.repeat(old_prompt_len) + '\r' + reset + prompt + reset);
                    } else {
                        wrapWrite(reset + prompt + reset);
                    }
                    break;
                case 'screenreader':
                    screen_reader = msg[1][0];
                    console.log('Received screenreader command:', screen_reader);
                    termLeft.options.screenReaderMode = screen_reader;
                    termRight.options.screenReaderMode = screen_reader;
                    if (screen_reader) {
                        wrapWriteln('Screen reader mode enabled.');
                        localStorage.setItem("reader", "true");
                        map_enabled = false;
                        hideRightPane();
                    } else {
                        wrapWriteln('Screen reader mode disabled.');
                        localStorage.setItem("reader", "false");
                    }
                    break;
                case 'audio':
                    audio.pause();
                    audio.src = msg[1][0];
                    audio.play();
                    break;
                case 'audio_pause':
                    audio.pause();
                    break;
                case 'logged_in':
                    censor_input = false;
                    ws.send(JSON.stringify(['term_size', [termLeft.cols, termLeft.rows], {}]));
                    break;
                case 'player_commands':
                    historyManager.setPlayerCommands(msg[1][0]);
                    break;
                case 'map_enable':
                    if (!screen_reader) {
                        map_enabled = true;
                        showRightPane();
                        ws.send(JSON.stringify(['map_size', [termRight.cols, termRight.rows - 1], {}]));
                    }
                    break;
                case 'map_disable':
                    map_enabled = false;
                    hideRightPane();
                    break;
                case 'get_map_size':
                    ws.send(JSON.stringify(['map_size', [termRight.cols, termRight.rows - 1], {}]));
                    break;
                case 'map':
                    if (map_enabled) {
                        // msg: ['map', [{map:..., pos:..., symbol:..., legend:..., min_x:..., max_y:..., show_legend:...}], {}]
                        const data = msg[1][0];
                        // Cache plain map rules
                        plain_map = data.map.split(/\r?\n/);
                        map_min_x = data.min_x;
                        map_max_y = data.max_y;
                        player_symbol = data.symbol;
                        pos = data.pos;
                        if (data.area) {
                            current_area_name = data.area;
                        }
                        legend_entries = data.legend; // Expecting list of tuples
                        if (data.show_legend !== undefined) {
                            show_legend = data.show_legend;
                        }

                        composeMap();
                    }
                    break;
                case 'legend':
                    if (map_enabled) {
                        // msg: ['legend', [{area: "name", legend: [...], show_legend: bool}, {}]]
                        const data = msg[1][0];
                        if (data && (data.area || data.legend)) {
                            if (data.area) current_area_name = data.area;
                            legend_entries = data.legend;
                            if (data.show_legend !== undefined) {
                                show_legend = data.show_legend;
                            }
                        } else {
                            // Fallback if message format differs or old format
                            legend_entries = msg[1];
                        }
                        composeMap();
                    }
                    break;
                case 'pos':
                    if (map_enabled) {
                        // msg: ['pos', [current_pos, symbol(opt)], {}]
                        pos = msg[1][0];
                        if (msg[1].length > 1) {
                            player_symbol = msg[1][1];
                        }
                        composeMap();
                    }
                    break;
                case 'buffer':
                    // this is for writing buffers with flow control
                    // this command expects an array of strings to write sequentially to the terminal
                    let x = 0;

                    async function next() {
                        x += 1;
                        if (x >= msg[1].length) {
                            wrapWrite(reset + '\x1B[?25h\n');
                        } else {
                            // slow down buffer playback if necessary
                            //await sleep(0);
                            wrapWrite(msg[1][x], next);
                        }
                    }
                    wrapWrite(msg[1][x], next)
                    break;
                default:
                    console.log('Unknown command: ' + msg);
            }
        }

        ws.addEventListener("message", e => onMessage(e));
        ws.onerror = function (e) {
            console.log(e);
            wrapWrite('\n======== Connection error: ' + e + '\n');
        };
        inputBox.focus();
        window.addEventListener('focus', (e) => {
            inputBox.focus();
        });
        // window.addEventListener('keydown', (e) => {
        //     inputBox.focus();
        // });
        window.addEventListener('resize', function (e) {
            // fitTerminals();
            debouncedRedrawEverything();
        }, true);
        window.addEventListener('beforeunload', () => {
            historyManager.saveHistory();
        });
    }).catch(() => {
        console.error('Font loading failed!');
    });

    // Expose renderLegend for testing
    window.renderLegend = renderLegend;
});

// function renderLegend(areaName, legendItems, availableWidth, availableHeight) {
function renderLegend(areaName, legendItems, availableWidth, availableHeight, playerSymbol) {
    const ansi_color_regex = /\x1B\[[0-9;]+m/g;
    const reset = '\x1B[0m';

    function visibleLength(str) {
        return str.replace(ansi_color_regex, '').length;
    }

    if (!legendItems) legendItems = [];

    // Create a working copy to avoid mutating the passed array
    // and add the player entry
    let workingItems = [...legendItems];
    if (playerSymbol) {
        workingItems.unshift({ symbol: playerSymbol, desc: "You" });
    }

    if (workingItems.length === 0) return [];

    let bestCols = workingItems.length;

    let minCols = 1;
    if (availableHeight > 2) {
        minCols = Math.ceil(workingItems.length / (availableHeight - 2));
    } else {
        minCols = workingItems.length;
    }
    minCols = Math.max(1, minCols);
    if (minCols > workingItems.length) minCols = workingItems.length;

    let chosenCols = -1;
    let finalColWidths = [];
    let headerText = "Legend";
    if (areaName) headerText = areaName;
    let headerTextLen = visibleLength(headerText);
    let minHeaderWidth = headerTextLen + 6;

    function calculateWidthForCols(c) {
        let rowsPerCol = Math.ceil(workingItems.length / c);
        let colWidths = new Array(c).fill(0);
        let idx = 0;
        for (let col = 0; col < c; col++) {
            let itemsInThisCol = [];
            for (let r = 0; r < rowsPerCol; r++) {
                if (idx < workingItems.length) {
                    itemsInThisCol.push(workingItems[idx++]);
                }
            }
            let maxW = 0;
            for (let item of itemsInThisCol) {
                let w = visibleLength(item.symbol) + visibleLength(item.desc) + 3;
                if (w > maxW) maxW = w;
            }
            colWidths[col] = maxW;
        }
        let w = 0;
        for (let cw of colWidths) w += cw;
        w += (3 * c) + 1;

        if (w < minHeaderWidth) {
            w = minHeaderWidth;
        }
        return { w, colWidths };
    }

    let startCols = minCols;
    let { w, colWidths } = calculateWidthForCols(startCols);
    if (w <= availableWidth) {
        chosenCols = startCols;
        finalColWidths = colWidths;
    } else {
        // Too wide! Reduce columns.
        for (let c = startCols - 1; c >= 1; c--) {
            let res = calculateWidthForCols(c);
            if (res.w <= availableWidth) {
                chosenCols = c;
                finalColWidths = res.colWidths;
                break;
            }
        }
        // If even 1 column is too wide, we default to 1 and let it overflow/truncate?
        if (chosenCols === -1) {
            chosenCols = 1;
            let res = calculateWidthForCols(1);
            finalColWidths = res.colWidths;
        }
    }

    let totalLayoutWidth = 0;
    for (let cw of finalColWidths) totalLayoutWidth += cw;
    totalLayoutWidth += (3 * chosenCols) + 1;

    if (totalLayoutWidth < minHeaderWidth) {
        let deficit = minHeaderWidth - totalLayoutWidth;
        if (chosenCols > 0) {
            finalColWidths[chosenCols - 1] += deficit;
            totalLayoutWidth += deficit;
        }
    }

    let lines = [];
    let rowsPerCol = Math.ceil(workingItems.length / chosenCols);

    let header = '╭─ ' + headerText + ' ─';
    let currentLen = 3 + headerTextLen + 2;

    if (currentLen < totalLayoutWidth - 1) {
        header += '─'.repeat(totalLayoutWidth - 1 - currentLen) + '╮';
    } else {
        header += '╮';
    }
    lines.push(header);

    for (let r = 0; r < rowsPerCol; r++) {
        let line = '│';
        for (let c = 0; c < chosenCols; c++) {
            let startIdxOfCol = c * rowsPerCol;
            let itemIdx = startIdxOfCol + r;

            let item = null;
            if (itemIdx < workingItems.length && itemIdx < (c + 1) * rowsPerCol) {
                item = workingItems[itemIdx];
            }

            let colW = finalColWidths[c];

            line += ' ';
            if (item) {
                let text = item.symbol + ' = ' + item.desc;
                let vLen = visibleLength(item.symbol) + visibleLength(item.desc) + 3;
                let padding = colW - vLen;
                line += text + ' '.repeat(padding);
            } else {
                line += ' '.repeat(colW);
            }
            line += ' │';
        }
        lines.push(line);
    }

    let footer = '╰';
    for (let c = 0; c < chosenCols; c++) {
        let cw = finalColWidths[c];
        footer += '─'.repeat(cw + 2);

        if (c < chosenCols - 1) {
            footer += '┴';
        } else {
            footer += '╯';
        }
    }
    lines.push(footer);

    return lines;
}

function hslToRgb(h, s, l) {
    let r, g, b;
    if (s === 0) {
        r = g = b = l; // achromatic
    } else {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };
        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1 / 3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1 / 3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

function wrapTrueColor(text, r, g, b) {
    return `\x1b[38;2;${r};${g};${b}m${text}\x1b[0m`;
}

function extractTrueColorFg(str) {
    const match = str.match(/\x1b\[38;2;(\d+);(\d+);(\d+)m/);
    if (match) {
        return { r: parseInt(match[1]), g: parseInt(match[2]), b: parseInt(match[3]) };
    }
    return null;
}

function wrapTrueColorFgBg(text, fgR, fgG, fgB, bgR, bgG, bgB) {
    return `\x1b[38;2;${fgR};${fgG};${fgB}m\x1b[48;2;${bgR};${bgG};${bgB}m${text}\x1b[0m`;
}