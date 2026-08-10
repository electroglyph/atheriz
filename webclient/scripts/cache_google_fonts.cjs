// Pre-downloads Google Fonts CSS + font files for offline/local use.
// Usage:
//   node scripts/cache_google_fonts.js            (preview only, ~15MB)
//   node scripts/cache_google_fonts.js --full      (preview + full fonts, VERY large)
//   node scripts/cache_google_fonts.js --limit 50  (only first 50 fonts)

const https = require('https');
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'public', 'gfonts');
const CSS_DIR = path.join(OUT_DIR, 'css');
const FONT_DIR = path.join(OUT_DIR, 'f');
const MANIFEST = path.join(OUT_DIR, 'manifest.json');
const FONTS_FILE = path.join(__dirname, '..', 'src', 'data', 'googleFonts.ts');

const CONCURRENCY = 20;
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const args = process.argv.slice(2);
const doFull = args.includes('--full');
const limitIdx = args.indexOf('--limit');
const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1], 10) : 0;

function parseFontFamilies() {
    const content = fs.readFileSync(FONTS_FILE, 'utf-8');
    const families = [];
    const re = /family:\s*"([^"]+)"/g;
    let m;
    while ((m = re.exec(content)) !== null) {
        families.push(m[1]);
    }
    return families;
}

function fetchUrl(url, retries = MAX_RETRIES) {
    return new Promise((resolve, reject) => {
        const attempt = (remaining) => {
            const parsed = new URL(url);
            const opts = {
                hostname: parsed.hostname,
                path: parsed.pathname + parsed.search,
                method: 'GET',
                headers: { 'User-Agent': UA },
            };
            const req = https.request(opts, (res) => {
                if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                    return fetchUrl(res.headers.location, remaining).then(resolve, reject);
                }
                if (res.statusCode !== 200) {
                    res.resume();
                    if (remaining > 0) return setTimeout(() => attempt(remaining - 1), RETRY_DELAY);
                    return reject(new Error(`HTTP ${res.statusCode}`));
                }
                const chunks = [];
                res.on('data', c => chunks.push(c));
                res.on('end', () => resolve(Buffer.concat(chunks)));
            });
            req.on('error', (e) => {
                if (remaining > 0) return setTimeout(() => attempt(remaining - 1), RETRY_DELAY);
                reject(e);
            });
            req.setTimeout(30000, () => {
                req.destroy();
                if (remaining > 0) return setTimeout(() => attempt(remaining - 1), RETRY_DELAY);
                reject(new Error('timeout'));
            });
            req.end();
        };
        attempt(retries);
    });
}

function slugify(family) {
    return family.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function progressBar(done, total, width = 30) {
    const pct = done / total;
    const filled = Math.round(pct * width);
    const empty = width - filled;
    return `[${'\u2588'.repeat(filled)}${'\u2591'.repeat(empty)}] ${Math.round(pct * 100)}%`;
}

function formatEta(ms) {
    if (!ms || ms < 0) return '--';
    const s = Math.round(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return `${m}m ${s % 60}s`;
}

let startTime = 0;
let totalBytes = 0;
let okCount = 0;
let skipCount = 0;
let failCount = 0;
let retryCount = 0;

function updateLine(done, total, current) {
    const elapsed = Date.now() - startTime;
    const eta = done > 0 ? (elapsed / done) * (total - done) : 0;
    const bar = progressBar(done, total);
    process.stdout.write(
        `\r${bar} ${done}/${total} | OK:${okCount} Skip:${skipCount} Fail:${failCount} Retry:${retryCount} | ${formatBytes(totalBytes)} | ETA: ${formatEta(eta)} | ${current}          `
    );
}

const crypto = require('crypto');

async function cacheFont(family, mode) {
    const slug = slugify(family);
    const cssName = mode === 'preview' ? `preview-${slug}.css` : `full-${slug}.css`;
    const cssPath = path.join(CSS_DIR, cssName);

    if (fs.existsSync(cssPath)) {
        skipCount++;
        return;
    }

    const cssParam = mode === 'preview'
        ? `family=${encodeURIComponent(family)}&text=${encodeURIComponent(family)}`
        : `family=${encodeURIComponent(family)}:wght@400;700`;

    const cssUrl = `https://fonts.googleapis.com/css2?${cssParam}`;

    let css = (await fetchUrl(cssUrl)).toString('utf-8');

    const urlRegex = /url\((https:\/\/fonts\.gstatic\.com\/[^)]+)\)/g;
    let match;
    const replacements = [];
    while ((match = urlRegex.exec(css)) !== null) {
        const fontUrl = match[1];
        const urlPath = fontUrl.split('?')[0];
        const baseName = urlPath.split('/').pop();
        const ext = baseName.includes('.') ? '.' + baseName.split('.').pop() : '.woff2';
        let fileName;

        if (baseName && baseName !== 'font' && baseName.length > 2) {
            fileName = baseName;
        } else {
            const hash = crypto.createHash('md5').update(fontUrl).digest('hex').substring(0, 10);
            fileName = `${slug}-${mode}${ext}`;
            if (fs.existsSync(path.join(FONT_DIR, fileName))) {
                fileName = `${slug}-${mode}-${hash}${ext}`;
            }
        }

        const localPath = path.join(FONT_DIR, fileName);

        if (!fs.existsSync(localPath)) {
            const data = await fetchUrl(fontUrl);
            fs.writeFileSync(localPath, data);
            totalBytes += data.length;
        } else {
            totalBytes += fs.statSync(localPath).size;
        }

        replacements.push({ from: fontUrl, to: `../f/${fileName}` });
    }

    for (const { from, to } of replacements) {
        css = css.replace(from, to);
    }

    fs.writeFileSync(cssPath, css);
    okCount++;
}

async function runPool(tasks, concurrency) {
    let nextIdx = 0;
    let doneCount = 0;

    async function worker() {
        while (nextIdx < tasks.length) {
            const idx = nextIdx++;
            const task = tasks[idx];
            const family = task.family;
            const mode = task.mode;
            updateLine(doneCount, tasks.length, family.substring(0, 30));
            let succeeded = false;
            for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
                try {
                    await cacheFont(family, mode);
                    succeeded = true;
                    break;
                } catch (e) {
                    if (attempt < MAX_RETRIES - 1) {
                        retryCount++;
                        await new Promise(r => setTimeout(r, RETRY_DELAY * (attempt + 1)));
                    }
                }
            }
            if (!succeeded) failCount++;
            doneCount++;
        }
    }

    const workers = Array(Math.min(concurrency, tasks.length)).fill(null).map(() => worker());
    await Promise.all(workers);
    updateLine(tasks.length, tasks.length, 'Done!');
    process.stdout.write('\n');
}

async function main() {
    const families = parseFontFamilies();
    const fonts = limit > 0 ? families.slice(0, limit) : families;

    console.log('Google Fonts Cache Downloader');
    console.log(`Fonts: ${fonts.length} | Concurrency: ${CONCURRENCY} | Mode: ${doFull ? 'preview + full' : 'preview only'}`);
    console.log(`Output: ${OUT_DIR}`);
    console.log('');

    fs.mkdirSync(CSS_DIR, { recursive: true });
    fs.mkdirSync(FONT_DIR, { recursive: true });

    const tasks = [];
    for (const family of fonts) {
        tasks.push({ family, mode: 'preview' });
    }
    if (doFull) {
        for (const family of fonts) {
            tasks.push({ family, mode: 'full' });
        }
    }

    startTime = Date.now();
    await runPool(tasks, CONCURRENCY);

    const manifest = {
        generated: new Date().toISOString(),
        fonts: fonts.map(f => ({ family: f, slug: slugify(f) })),
    };
    fs.writeFileSync(MANIFEST, JSON.stringify(manifest));

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\nDone in ${elapsed}s | ${formatBytes(totalBytes)} downloaded | OK:${okCount} Skip:${skipCount} Fail:${failCount} Retries:${retryCount}`);
}

main().catch(e => { console.error(e); process.exit(1); });
