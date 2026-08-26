import { closeOtherModals } from './modalHelper';
import { MapLegendEntry } from '../mapedit';
import { Color } from '../types';
import { cssColor } from '../utils/colors';
import { parseAnsiSymbol, stripAnsi, DEFAULT_FG, TRANSPARENT } from '../utils/ansiParser';
import { CharMapDialog } from './CharMapDialog';
import { ColorPickerModal } from './ColorPickerModal';

function toColor(value: unknown, fallback: Color): Color {
    if (Array.isArray(value) && value.length === 3) {
        const [r, g, b] = value as [unknown, unknown, unknown];
        if (typeof r === 'number' && typeof g === 'number' && typeof b === 'number') {
            return [r, g, b];
        }
    }
    return [...fallback] as Color;
}
function normalizeFg(value: unknown): Color {
    if (Array.isArray(value) && value.length === 3) return toColor(value, DEFAULT_FG);
    return [...DEFAULT_FG] as Color;
}
function normalizeBg(value: unknown): Color {
    if (Array.isArray(value) && value.length === 3) return toColor(value, TRANSPARENT);
    return [...TRANSPARENT] as Color;
}

export class LegendEditorDialog {
    private modal: HTMLElement;
    private listEl: HTMLElement;
    private btnAdd: HTMLButtonElement;
    private btnSave: HTMLButtonElement;
    private btnCancel: HTMLButtonElement;
    private onSave: (legend: MapLegendEntry[]) => void;
    private legend: MapLegendEntry[] = [];
    private playerSymbol: string = 'X';
    private charMapDialog: CharMapDialog | null = null;
    private getFontFamily: (() => string) | null = null;
    private boundBackdropClick = (e: MouseEvent) => {
        if (e.target === this.modal) this.close();
    };
    private boundKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && !this.modal.classList.contains('hidden')) this.close();
    };

    constructor(
        onSave: (legend: MapLegendEntry[]) => void,
        charMapDialog?: CharMapDialog,
        getFontFamily?: () => string,
    ) {
        const modal = document.getElementById('legend-editor-modal');
        if (!modal) throw new Error('Missing #legend-editor-modal');
        this.modal = modal as HTMLElement;
        const list = document.getElementById('legend-editor-list');
        if (!list) throw new Error('Missing #legend-editor-list');
        this.listEl = list as HTMLElement;
        this.btnAdd = document.getElementById('legend-add-btn') as HTMLButtonElement;
        this.btnSave = document.getElementById('legend-save-btn') as HTMLButtonElement;
        this.btnCancel = document.getElementById('legend-cancel-btn') as HTMLButtonElement;
        if (!this.btnAdd || !this.btnSave || !this.btnCancel) throw new Error('Missing legend dialog buttons');
        this.onSave = onSave;
        if (charMapDialog) this.charMapDialog = charMapDialog;
        if (getFontFamily) this.getFontFamily = getFontFamily;
        this.btnAdd.addEventListener('click', () => this.addRow({ symbol: 'X', desc: 'New entry', coord: null, show: true, fg: [...DEFAULT_FG] as Color, bg: [...TRANSPARENT] as Color }));
        this.btnSave.addEventListener('click', () => this.handleSave());
        this.btnCancel.addEventListener('click', () => this.close());
        this.modal.addEventListener('click', this.boundBackdropClick);
        window.addEventListener('keydown', this.boundKeyDown);
    }

    public setPicker(charMapDialog: CharMapDialog, getFontFamily: () => string): void {
        this.charMapDialog = charMapDialog;
        this.getFontFamily = getFontFamily;
    }

    public destroy(): void {
        this.modal.removeEventListener('click', this.boundBackdropClick);
        window.removeEventListener('keydown', this.boundKeyDown);
    }

    public open(initial: MapLegendEntry[], playerSymbol?: string): void {
        closeOtherModals('legend-editor-modal');
        if (playerSymbol !== undefined && playerSymbol !== null && playerSymbol !== '') this.playerSymbol = playerSymbol;
        this.legend = initial.map((e) => {
            const rawSym = e.symbol ?? 'X';
            let char = rawSym;
            let fg: Color = normalizeFg((e as unknown as { fg?: unknown }).fg);
            let bg: Color = normalizeBg((e as unknown as { bg?: unknown }).bg);
            if (typeof rawSym === 'string' && rawSym.includes('\x1b')) {
                const cell = parseAnsiSymbol(rawSym);
                char = cell.char || stripAnsi(rawSym) || 'X';
                fg = cell.fg ? ([...cell.fg] as Color) : fg;
                bg = cell.bg ? ([...cell.bg] as Color) : bg;
            } else if (typeof rawSym === 'string') {
                const vis = stripAnsi(rawSym);
                char = vis || rawSym || 'X';
            }
            // clamp 1-2 visible chars
            const vis2 = stripAnsi(char);
            if (vis2.length > 2) char = vis2.slice(0, 2);
            return { symbol: char, desc: e.desc ?? '', coord: e.coord ? [...e.coord] as [number, number] : null, show: e.show !== false, fg, bg } as MapLegendEntry;
        });
        this.render();
        this.modal.classList.remove('hidden');
    }

    public close(): void {
        this.modal.classList.add('hidden');
    }

    private render(): void {
        this.listEl.innerHTML = '';
        // Automatic "You" entry — always present on the rendered map, not editable
        const autoRow = document.createElement('div');
        autoRow.style.display = 'flex';
        autoRow.style.gap = '6px';
        autoRow.style.alignItems = 'center';
        autoRow.style.marginBottom = '8px';
        autoRow.style.padding = '6px 8px';
        autoRow.style.background = '#2a2a2a';
        autoRow.style.borderRadius = '4px';
        autoRow.style.opacity = '0.85';
        const autoSym = document.createElement('span');
        const autoVis = stripAnsi(this.playerSymbol || 'X') || 'X';
        let autoFg: Color = [...DEFAULT_FG] as Color;
        let autoBg: Color = [...TRANSPARENT] as Color;
        if ((this.playerSymbol || '').includes('\x1b')) {
            const c = parseAnsiSymbol(this.playerSymbol);
            autoFg = c.fg as Color;
            autoBg = c.bg as Color;
        }
        autoSym.textContent = stripAnsi(autoVis) || autoVis;
        autoSym.title = 'Your map symbol (automatic)';
        autoSym.style.width = '50px';
        autoSym.style.textAlign = 'center';
        autoSym.style.fontWeight = 'bold';
        autoSym.style.fontFamily = 'monospace';
        autoSym.style.padding = '2px 4px';
        autoSym.style.borderRadius = '3px';
        autoSym.style.color = cssColor(autoFg);
        autoSym.style.background = autoBg[0] === -1 ? '#333' : cssColor(autoBg);
        if (autoBg[0] === -1) {
            autoSym.style.border = '1px solid #555';
        }
        const autoDesc = document.createElement('span');
        autoDesc.textContent = 'You';
        autoDesc.style.flex = '1';
        autoDesc.style.fontSize = '12px';
        const autoBadge = document.createElement('span');
        autoBadge.textContent = 'automatic';
        autoBadge.style.fontSize = '10px';
        autoBadge.style.color = '#888';
        autoBadge.style.fontStyle = 'italic';
        autoRow.append(autoSym, autoDesc, autoBadge);
        this.listEl.appendChild(autoRow);

        const separator = document.createElement('div');
        separator.style.height = '1px';
        separator.style.background = '#444';
        separator.style.margin = '4px 0 8px 0';
        this.listEl.appendChild(separator);

        if (this.legend.length === 0) {
            const empty = document.createElement('div');
            empty.textContent = 'No custom legend entries. Click Add Entry to add one (e.g. shrine, shop).';
            empty.style.color = '#888';
            empty.style.fontSize = '12px';
            empty.style.padding = '8px';
            empty.style.fontStyle = 'italic';
            this.listEl.appendChild(empty);
        }
        this.legend.forEach((entry, idx) => {
            const row = document.createElement('div');
            row.className = 'legend-row';
            row.style.display = 'flex';
            row.style.gap = '6px';
            row.style.alignItems = 'center';
            row.style.marginBottom = '6px';
            row.style.flexWrap = 'wrap';

            const fg = normalizeFg((entry as unknown as { fg?: unknown }).fg);
            const bg = normalizeBg((entry as unknown as { bg?: unknown }).bg);
            const visSym = stripAnsi(entry.symbol ?? '') || 'X';

            const symbolBtn = document.createElement('button');
            symbolBtn.type = 'button';
            symbolBtn.textContent = visSym;
            symbolBtn.title = 'Click to pick symbol (Char Map)';
            symbolBtn.style.width = '44px';
            symbolBtn.style.height = '28px';
            symbolBtn.style.flexShrink = '0';
            symbolBtn.style.fontFamily = 'var(--main-font, monospace)';
            symbolBtn.style.fontSize = '16px';
            symbolBtn.style.display = 'flex';
            symbolBtn.style.alignItems = 'center';
            symbolBtn.style.justifyContent = 'center';
            symbolBtn.style.border = '1px solid #555';
            symbolBtn.style.borderRadius = '3px';
            symbolBtn.style.cursor = 'pointer';
            symbolBtn.style.color = cssColor(fg);
            symbolBtn.style.background = bg[0] === -1 ? '#222' : cssColor(bg);
            symbolBtn.addEventListener('click', () => {
                if (!this.charMapDialog || !this.getFontFamily) {
                    // fallback: allow direct text edit via prompt
                    const next = window.prompt('Symbol (1-2 chars):', visSym);
                    if (next !== null) {
                        const v = stripAnsi(next).slice(0, 2);
                        if (v) {
                            entry.symbol = v;
                            this.render();
                        }
                    }
                    return;
                }
                const font = this.getFontFamily!();
                // Hide legend, open picker, restore on close
                this.modal.classList.add('hidden');
                this.charMapDialog!.open(font, (chars) => {
                    if (chars.length > 0 && chars[0]) {
                        entry.symbol = chars[0];
                    }
                }, () => {
                    // reopen legend after picker closes (next tick to let modalHelper settle)
                    setTimeout(() => {
                        this.modal.classList.remove('hidden');
                        this.render();
                    }, 0);
                });
            });

            const makeColorBtn = (color: Color, title: string, isBg: boolean, onPick: (c: Color) => void): HTMLButtonElement => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.title = title;
                btn.style.width = '18px';
                btn.style.height = '18px';
                btn.style.borderRadius = '3px';
                btn.style.flexShrink = '0';
                btn.style.cursor = 'pointer';
                btn.style.padding = '0';
                if (isBg && color[0] === -1) {
                    btn.style.background = 'repeating-conic-gradient(#666 0% 25%, #333 0% 50%) 50% / 8px 8px';
                    btn.style.border = '1px dashed #888';
                } else {
                    btn.style.background = cssColor(color);
                    btn.style.border = '1px solid #fff';
                    btn.style.boxShadow = '0 0 0 1px #000 inset';
                }
                btn.addEventListener('click', async () => {
                    // ensure legend hidden while color picker open
                    const current: Color = isBg && color[0] === -1 ? [0, 0, 0] as Color : color;
                    this.modal.classList.add('hidden');
                    // brief delay to allow modalHelper to hide correctly
                    await new Promise((r) => setTimeout(r, 0));
                    const picked = await ColorPickerModal.getInstance().open(current);
                    // picker closed, reopen legend
                    this.modal.classList.remove('hidden');
                    if (picked) {
                        onPick(picked);
                    } else if (isBg) {
                        // cancel keeps as is; allow clearing bg via right-click
                    }
                    this.render();
                });
                // right-click bg clears to transparent
                if (isBg) {
                    btn.addEventListener('contextmenu', (e) => {
                        e.preventDefault();
                        (entry as unknown as { bg: Color }).bg = [...TRANSPARENT] as Color;
                        this.render();
                    });
                    btn.title += ' (right-click to clear)';
                } else {
                    btn.addEventListener('contextmenu', (e) => {
                        e.preventDefault();
                        (entry as unknown as { fg: Color }).fg = [...DEFAULT_FG] as Color;
                        this.render();
                    });
                    btn.title += ' (right-click to reset)';
                }
                return btn;
            };

            const fgBtn = makeColorBtn(fg, 'Foreground color', false, (c) => {
                (entry as unknown as { fg: Color }).fg = c;
            });
            const bgBtn = makeColorBtn(bg, 'Background color', true, (c) => {
                (entry as unknown as { bg: Color }).bg = c;
            });
            // Small labels
            fgBtn.setAttribute('aria-label', 'FG color');
            bgBtn.setAttribute('aria-label', 'BG color');

            const descInput = document.createElement('input');
            descInput.type = 'text';
            descInput.placeholder = 'description';
            descInput.value = entry.desc ?? '';
            descInput.style.flex = '1';
            descInput.style.minWidth = '90px';
            descInput.addEventListener('input', () => {
                entry.desc = descInput.value;
            });

            const coordX = document.createElement('input');
            coordX.type = 'number';
            coordX.placeholder = 'x';
            coordX.style.width = '60px';
            coordX.value = entry.coord ? String(entry.coord[0]) : '';
            const coordY = document.createElement('input');
            coordY.type = 'number';
            coordY.placeholder = 'y';
            coordY.style.width = '60px';
            coordY.value = entry.coord ? String(entry.coord[1]) : '';
            const updateCoord = () => {
                const xStr = coordX.value.trim();
                const yStr = coordY.value.trim();
                if (xStr === '' && yStr === '') {
                    entry.coord = null;
                } else if (xStr !== '' && yStr !== '') {
                    const x = Number(xStr);
                    const y = Number(yStr);
                    if (Number.isInteger(x) && Number.isInteger(y)) entry.coord = [x, y];
                }
            };
            coordX.addEventListener('input', updateCoord);
            coordY.addEventListener('input', updateCoord);

            const showCheck = document.createElement('input');
            showCheck.type = 'checkbox';
            showCheck.checked = entry.show !== false;
            showCheck.title = 'Show in legend';
            showCheck.addEventListener('change', () => {
                entry.show = showCheck.checked;
            });
            const showLabel = document.createElement('label');
            showLabel.textContent = 'show';
            showLabel.style.fontSize = '11px';
            showLabel.style.display = 'flex';
            showLabel.style.alignItems = 'center';
            showLabel.style.gap = '2px';
            showLabel.appendChild(showCheck);
            // reorder: checkbox first then text
            showLabel.insertBefore(showCheck, showLabel.firstChild);

            const delBtn = document.createElement('button');
            delBtn.textContent = '✕';
            delBtn.title = 'Remove';
            delBtn.style.padding = '2px 6px';
            delBtn.addEventListener('click', () => {
                this.legend.splice(idx, 1);
                this.render();
            });

            row.appendChild(symbolBtn);
            row.appendChild(fgBtn);
            row.appendChild(bgBtn);
            row.appendChild(descInput);
            row.appendChild(coordX);
            row.appendChild(coordY);
            row.appendChild(showLabel);
            row.appendChild(delBtn);
            this.listEl.appendChild(row);
        });
    }

    private addRow(entry: MapLegendEntry): void {
        this.legend.push(entry);
        this.render();
    }

    private handleSave(): void {
        // validate
        for (let i = 0; i < this.legend.length; i++) {
            const e = this.legend[i];
            const vis = stripAnsi(e.symbol ?? '');
            if (!vis || vis.length === 0 || vis.length > 2) {
                alert(`Row ${i + 1}: symbol must be 1-2 characters`);
                return;
            }
            if (e.desc == null || e.desc.trim().length === 0) {
                alert(`Row ${i + 1}: description is required`);
                return;
            }
            if (e.coord !== null) {
                if (!Array.isArray(e.coord) || e.coord.length !== 2 || !e.coord.every((v) => Number.isInteger(v))) {
                    alert(`Row ${i + 1}: coord must be two integers or empty`);
                    return;
                }
            }
        }
        if (this.legend.length > 200) {
            alert('Too many legend entries (max 200)');
            return;
        }
        this.onSave(this.legend.map((e) => ({ ...e, coord: e.coord ? [...e.coord] as [number, number] : null })));
        this.close();
    }
}
