import { closeOtherModals } from './modalHelper';
import { MapLegendEntry } from '../mapedit';

export class LegendEditorDialog {
    private modal: HTMLElement;
    private listEl: HTMLElement;
    private btnAdd: HTMLButtonElement;
    private btnSave: HTMLButtonElement;
    private btnCancel: HTMLButtonElement;
    private onSave: (legend: MapLegendEntry[]) => void;
    private legend: MapLegendEntry[] = [];
    private playerSymbol: string = 'X';
    private boundBackdropClick = (e: MouseEvent) => {
        if (e.target === this.modal) this.close();
    };
    private boundKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape' && !this.modal.classList.contains('hidden')) this.close();
    };

    constructor(onSave: (legend: MapLegendEntry[]) => void) {
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
        this.btnAdd.addEventListener('click', () => this.addRow({ symbol: 'X', desc: 'New entry', coord: null, show: true }));
        this.btnSave.addEventListener('click', () => this.handleSave());
        this.btnCancel.addEventListener('click', () => this.close());
        this.modal.addEventListener('click', this.boundBackdropClick);
        window.addEventListener('keydown', this.boundKeyDown);
    }

    public destroy(): void {
        this.modal.removeEventListener('click', this.boundBackdropClick);
        window.removeEventListener('keydown', this.boundKeyDown);
    }

    public open(initial: MapLegendEntry[], playerSymbol?: string): void {
        closeOtherModals('legend-editor-modal');
        if (playerSymbol !== undefined && playerSymbol !== null && playerSymbol !== '') this.playerSymbol = playerSymbol;
        this.legend = initial.map((e) => ({ ...e, coord: e.coord ? [...e.coord] as [number, number] : null }));
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
        autoSym.textContent = this.playerSymbol || 'X';
        autoSym.title = 'Your map symbol (automatic)';
        autoSym.style.width = '50px';
        autoSym.style.textAlign = 'center';
        autoSym.style.fontWeight = 'bold';
        autoSym.style.fontFamily = 'monospace';
        autoSym.style.background = '#333';
        autoSym.style.padding = '2px 4px';
        autoSym.style.borderRadius = '3px';
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

            const symbolInput = document.createElement('input');
            symbolInput.type = 'text';
            symbolInput.maxLength = 2;
            symbolInput.placeholder = 'sym';
            symbolInput.value = entry.symbol ?? '';
            symbolInput.title = 'Symbol (1-2 chars)';
            symbolInput.style.width = '50px';
            symbolInput.addEventListener('input', () => {
                entry.symbol = symbolInput.value;
            });

            const descInput = document.createElement('input');
            descInput.type = 'text';
            descInput.placeholder = 'description';
            descInput.value = entry.desc ?? '';
            descInput.style.flex = '1';
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

            row.appendChild(symbolInput);
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
            if (!e.symbol || e.symbol.length === 0 || e.symbol.length > 2) {
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
        this.onSave(this.legend.map((e) => ({ ...e })));
        this.close();
    }
}
