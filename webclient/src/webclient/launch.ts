const DRAW_PATH = '/static/atheriz_draw/';
const GRANT_KEY = 'atheriz_draw_grant';
const GRANT_TS_KEY = 'atheriz_draw_grant_ts';
const GRANT_TTL_MS = 60000;

let lastLaunchAt = 0;

export function __resetLaunchThrottleForTests(): void {
    lastLaunchAt = 0;
}

export interface DrawGrant {
    key: string;
    payload: unknown;
}

export function launchDraw(key?: string, payload?: unknown): boolean {
    // The grant is stored before the throttle gate so a throttled retry never
    // orphans the newest server-minted key; the tab opens the stored grant.
    if (key && payload) {
        try {
            localStorage.setItem(GRANT_KEY, JSON.stringify({ key, payload }));
            localStorage.setItem(GRANT_TS_KEY, String(Date.now()));
        } catch {
            // Storage is optional (private mode, quota, etc.) – launch still proceeds.
        }
    }

    const now = Date.now();
    if (now - lastLaunchAt < 1000) return false;
    lastLaunchAt = now;

    const drawUrl = new URL(DRAW_PATH, window.location.origin).href;
    const opened = window.open(drawUrl, '_blank', 'noopener,noreferrer');
    if (opened) {
        return true;
    }

    const link = document.createElement('a');
    link.href = drawUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Open AtheriZ Draw in a new tab';
    link.style.color = '#7dd3fc';
    const fallback = document.createElement('div');
    fallback.className = 'popup-fallback';
    fallback.setAttribute('role', 'alert');
    fallback.append(document.createTextNode('Popup blocked. '), link);
    document.body.append(fallback);
    return false;
}

export function readDrawGrant(): DrawGrant | null {
    const raw = localStorage.getItem(GRANT_KEY);
    if (!raw) return null;
    const tsRaw = localStorage.getItem(GRANT_TS_KEY);
    if (tsRaw === null || Number.isNaN(Number(tsRaw)) || Date.now() - Number(tsRaw) > GRANT_TTL_MS) {
        clearDrawGrant();
        return null;
    }
    try {
        const parsed = JSON.parse(raw) as unknown;
        if (!isDrawGrant(parsed)) {
            clearDrawGrant();
            return null;
        }
        return parsed;
    } catch {
        clearDrawGrant();
        return null;
    }
}

export function clearDrawGrant(): void {
    localStorage.removeItem(GRANT_KEY);
    localStorage.removeItem(GRANT_TS_KEY);
}

function isDrawGrant(value: unknown): value is DrawGrant {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return false;
    const candidate = value as Record<string, unknown>;
    return typeof candidate.key === 'string' && typeof candidate.payload === 'object' && candidate.payload !== null && !Array.isArray(candidate.payload);
}