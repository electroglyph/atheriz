export function closeOtherModals(currentId: string): void {
    const modalIds = [
        'new-canvas-modal',
        'resize-canvas-modal',
        'image-import-modal',
        'char-map-modal',
        'text-tool-modal',
        'google-font-picker-modal',
        'color-picker-modal',
        'type-tool-modal',
        'move-denied-modal',
        'color-adjust-modal',
    ];
    for (const id of modalIds) {
        if (id === currentId) continue;
        document.getElementById(id)?.classList.add('hidden');
    }
    const preview = document.getElementById('preview-window');
    if (preview && currentId !== 'preview-window' && preview.style.display !== 'none' && preview.style.display !== '') {
        preview.style.display = 'none';
    }
}
