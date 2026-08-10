const DRAW_PATH = '/atheriz_draw/';

let lastLaunchAt = 0;

export function launchDraw(): boolean {
    const now = Date.now();
    if (now - lastLaunchAt < 1000) return true;
    lastLaunchAt = now;

    const drawUrl = new URL(DRAW_PATH, window.location.origin).href;
    const opened = window.open(drawUrl, '_blank', 'noopener,noreferrer');
    if (opened) return true;

    const link = document.createElement('a');
    link.href = drawUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open AtheriZ Draw in a new tab';
    link.style.color = '#7dd3fc';
    const container = document.getElementById('left-terminal');
    container?.append(document.createTextNode('\nPopup blocked. '), link, document.createTextNode('\n'));
    return false;
}
