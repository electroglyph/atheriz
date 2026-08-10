const loadedPreviews = new Set<string>();
const loadedFull = new Set<string>();

import { toCssFontFamily } from './cssFont';

const CACHE_BASE = import.meta.env.BASE_URL + 'gfonts/css';
const CDN_BASE = 'https://fonts.googleapis.com/css2';

let cacheManifest: Set<string> | null = null;
let manifestPromise: Promise<Set<string>> | null = null;

function slugify(family: string): string {
    return family.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function cssEscapedFamily(family: string): string {
    return family.replace(/ /g, '+');
}

export function fontNameToCSS(family: string): string {
    return toCssFontFamily(family);
}

function loadManifest(): Promise<Set<string>> {
    if (cacheManifest !== null) return Promise.resolve(cacheManifest);
    if (manifestPromise) return manifestPromise;
    manifestPromise = (async () => {
        try {
            const res = await fetch(import.meta.env.BASE_URL + 'gfonts/manifest.json');
            if (!res.ok) throw new Error();
            const data = await res.json();
            cacheManifest = new Set(data.fonts.map((f: { slug: string }) => f.slug));
        } catch {
            cacheManifest = new Set();
        }
        return cacheManifest!;
    })();
    return manifestPromise;
}

export function preloadManifest(): void {
    loadManifest();
}

function hasCache(slug: string): boolean {
    return cacheManifest !== null && cacheManifest.has(slug);
}

function injectStylesheet(href: string, fallbackHref?: string): void {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    if (fallbackHref) {
        link.onerror = () => {
            link.href = fallbackHref;
        };
    }
    document.head.appendChild(link);
}

function cdnPreviewUrl(family: string): string {
    return `${CDN_BASE}?family=${cssEscapedFamily(family)}&text=${encodeURIComponent(family)}`;
}

function cdnFullUrl(family: string): string {
    return `${CDN_BASE}?family=${cssEscapedFamily(family)}:wght@400;700`;
}

export function loadFontPreview(family: string): void {
    if (loadedPreviews.has(family)) return;
    loadedPreviews.add(family);

    const slug = slugify(family);

    if (hasCache(slug)) {
        injectStylesheet(`${CACHE_BASE}/preview-${slug}.css`, cdnPreviewUrl(family));
    } else {
        loadManifest().then(manifest => {
            if (manifest.has(slug)) {
                injectStylesheet(`${CACHE_BASE}/preview-${slug}.css`, cdnPreviewUrl(family));
            } else {
                injectStylesheet(cdnPreviewUrl(family));
            }
        });
    }
}

export async function loadFontFull(family: string): Promise<void> {
    if (loadedFull.has(family)) return;
    loadedFull.add(family);

    const slug = slugify(family);

    if (hasCache(slug)) {
        injectStylesheet(`${CACHE_BASE}/full-${slug}.css`, cdnFullUrl(family));
    } else {
        const manifest = await loadManifest();
        if (manifest.has(slug)) {
            injectStylesheet(`${CACHE_BASE}/full-${slug}.css`, cdnFullUrl(family));
        } else {
            injectStylesheet(cdnFullUrl(family));
        }
    }

    try {
        await document.fonts.load(`400px ${fontNameToCSS(family)}`);
        await document.fonts.load(`bold 40px ${fontNameToCSS(family)}`);
    } catch (_) {}
    await document.fonts.ready;
}
