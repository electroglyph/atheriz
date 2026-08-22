// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { MessageDialog } from '../src/ui/MessageDialog';

function mountModal(): void {
    document.body.innerHTML = `
      <div id="move-denied-modal" class="modal hidden">
        <div class="modal-content">
          <h3>Room Move Rejected</h3>
          <p id="move-denied-modal-message"></p>
          <div class="modal-actions">
            <button id="move-denied-modal-ok">OK</button>
          </div>
        </div>
      </div>`;
}

describe('MessageDialog', () => {
    it('throws when the container or its children are missing', () => {
        document.body.innerHTML = '';
        expect(() => new MessageDialog('move-denied-modal')).toThrow();
        mountModal();
        document.getElementById('move-denied-modal-message')?.remove();
        expect(() => new MessageDialog('move-denied-modal')).toThrow();
        mountModal();
        document.getElementById('move-denied-modal-ok')?.remove();
        expect(() => new MessageDialog('move-denied-modal')).toThrow();
    });

    it('show() sets the message text and reveals the modal', () => {
        mountModal();
        const dialog = new MessageDialog('move-denied-modal');
        expect(dialog.isVisible()).toBe(false);
        dialog.show('Room move rejected at (4, 3).');
        expect(dialog.isVisible()).toBe(true);
        expect(document.getElementById('move-denied-modal-message')!.textContent).toBe(
            'Room move rejected at (4, 3).'
        );
        expect(
            document.getElementById('move-denied-modal')!.classList.contains('hidden')
        ).toBe(false);
    });

    it('replaces a previous message on subsequent shows', () => {
        mountModal();
        const dialog = new MessageDialog('move-denied-modal');
        dialog.show('first');
        dialog.show('second');
        expect(document.getElementById('move-denied-modal-message')!.textContent).toBe('second');
        expect(dialog.isVisible()).toBe(true);
    });

    it('hides when the OK button is clicked', () => {
        mountModal();
        const dialog = new MessageDialog('move-denied-modal');
        dialog.show('Room move rejected.');
        document.getElementById('move-denied-modal-ok')!.click();
        expect(dialog.isVisible()).toBe(false);
        // message stays available until the next show
        expect(document.getElementById('move-denied-modal-message')!.textContent).toBe(
            'Room move rejected.'
        );
    });
});
