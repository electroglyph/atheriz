// Full Ring Mappings for 90-degree rotations
// Corner-oriented rings (Top-Left, Top-Right, Bottom-Right, Bottom-Left)
const RINGS_CORNER = [
    // Box Light
    ['┌', '┐', '┘', '└'],
    ['┬', '┤', '┴', '├'],
    // Box Heavy
    ['┏', '┓', '┛', '┗'],
    ['┳', '┫', '┻', '┣'],
    // Box Double
    ['╔', '╗', '╝', '╚'],
    ['╦', '╣', '╩', '╠'],
    // Box Mixed Combos (Light/Heavy/Double)
    ['┎', '┒', '┚', '┖'],
    ['┍', '┑', '┙', '┕'],
    // Arcs
    ['╭', '╮', '╯', '╰'],
    // Quadrants
    ['▘', '▝', '▗', '▖'],
    // 1/4 Block Corners
    ['𜺨', '𜺫', '𜺠', '𜺣'],
    // 1/8 Block Corners
    ['🭽', '🭾', '🭿', '🭼'],
    // Wedges
    ['◤', '◥', '◢', '◣'],
    ['▽', '▼', '▾', '▿'], // Quadrant edges
    // Circle variants
    ['◜', '◝', '◞', '◟'],
    // Oval Circle Tool specific legacy symbols
    // Quarters
    ['𜰵', '𜰶', '𜰺', '𜰹'],
    // Twelfths corners
    ['𜰰', '𜰳', '𜰿', '𜰼'],
    // Twelfths clockwise inner sequence 1
    ['𜰱', '𜰷', '𜰾', '𜰸'],
    // Twelfths clockwise inner sequence 2
    ['𜰲', '𜰻', '𜰽', '𜰴'],
];

// Edge-oriented rings (Top, Right, Bottom, Left)
const RINGS_EDGE = [
    // Fractional Blocks (1/8 to 7/8)
    ['▔', '▕', '▁', '▏'],  // 1/8th blocks
    ['🮂', '🮇', '▂', '▎'],   // 2/8 (1/4)
    ['🮃', '🮈', '▃', '▍'],   // 3/8
    ['▀', '▐', '▄', '▌'],   // 4/8 (Half)
    ['🮄', '🮉', '▅', '▋'],   // 5/8
    ['🮅', '🮊', '▆', '▊'],   // 6/8 (3/4)
    ['🮆', '🮋', '▇', '▉'],   // 7/8
    // Circle variants
    ['◡', '◐', '◠', '◑'],
    // Triangles
    ['▲', '▶', '▼', '◀'],
    ['△', '▷', '▽', '◁'],
    ['▴', '▸', '▾', '◂'],
];

// Toggles (Lines that 180 don't change, but 90 swaps)
const TOGGLES = [
    ['─', '│'],
    ['━', '┃'],
    ['═', '║'],
    ['/', '\\'],
    ['╱', '╲'],
    ['-', '|']
];

// Explicit Flips that don't rotate cleanly or are 180 only
// For Horizontal flipping
const FLIP_H: Record<string, string> = {
    '(': ')', ')': '(',
    '[': ']', ']': '[',
    '{': '}', '}': '{',
    '<': '>', '>': '<',
    '◿': '◺', '◺': '◿',
    '◸': '◹', '◹': '◸',
    '▱': '▱',
};

// For Vertical flipping
const FLIP_V: Record<string, string> = {
    '◿': '◸', '◸': '◿',
    '◺': '◹', '◹': '◺',
    'v': '^', '^': 'v',
    'V': 'Λ', 'Λ': 'V',
    'W': 'M', 'M': 'W',
};

// Build maps for O(1) lookups
const cwMap = new Map<string, string>();
const ccwMap = new Map<string, string>();
const rot180Map = new Map<string, string>();
const hMap = new Map<string, string>();
const vMap = new Map<string, string>();

for (const ring of RINGS_CORNER) {
    for (let i = 0; i < ring.length; i++) {
        const char = ring[i];
        const nextCW = ring[(i + 1) % ring.length];
        const nextCCW = ring[(i + ring.length - 1) % ring.length];
        const next180 = ring[(i + 2) % ring.length];

        cwMap.set(char, nextCW);
        ccwMap.set(char, nextCCW);
        rot180Map.set(char, next180);
        
        // Horizontal flip: Top-Left(0) flips with Top-Right(1). Bottom-Left(3) flips with Bottom-Right(2).
        if (i === 0) hMap.set(char, ring[1]);
        if (i === 1) hMap.set(char, ring[0]);
        if (i === 2) hMap.set(char, ring[3]);
        if (i === 3) hMap.set(char, ring[2]);

        // Vertical flip: Top-Left(0) flips with Bottom-Left(3). Top-Right(1) flips with Bottom-Right(2).
        if (i === 0) vMap.set(char, ring[3]);
        if (i === 3) vMap.set(char, ring[0]);
        if (i === 1) vMap.set(char, ring[2]);
        if (i === 2) vMap.set(char, ring[1]);
    }
}

for (const ring of RINGS_EDGE) {
    for (let i = 0; i < ring.length; i++) {
        const char = ring[i];
        const nextCW = ring[(i + 1) % ring.length];
        const nextCCW = ring[(i + ring.length - 1) % ring.length];
        const next180 = ring[(i + 2) % ring.length];

        cwMap.set(char, nextCW);
        ccwMap.set(char, nextCCW);
        rot180Map.set(char, next180);
        
        // Horizontal flip: Top(0) stays Top, Bottom(2) stays Bottom. Left(3) flips with Right(1).
        if (i === 0) hMap.set(char, ring[0]);
        if (i === 2) hMap.set(char, ring[2]);
        if (i === 1) hMap.set(char, ring[3]);
        if (i === 3) hMap.set(char, ring[1]);

        // Vertical flip: Left(3) stays Left, Right(1) stays Right. Top(0) flips with Bottom(2).
        if (i === 3) vMap.set(char, ring[3]);
        if (i === 1) vMap.set(char, ring[1]);
        if (i === 0) vMap.set(char, ring[2]);
        if (i === 2) vMap.set(char, ring[0]);
    }
}

for (const toggle of TOGGLES) {
    cwMap.set(toggle[0], toggle[1]);
    cwMap.set(toggle[1], toggle[0]);
    ccwMap.set(toggle[0], toggle[1]);
    ccwMap.set(toggle[1], toggle[0]);

    // Flip H
    hMap.set(toggle[0], toggle[0]); // Horizontals stay horizontal
    hMap.set(toggle[1], toggle[1]); // Verticals stay vertical 
    // Except diagonals!
    if (toggle[0] === '/' || toggle[0] === '╱') {
        hMap.set(toggle[0], toggle[1]);
        hMap.set(toggle[1], toggle[0]);
        vMap.set(toggle[0], toggle[1]);
        vMap.set(toggle[1], toggle[0]);
    } else {
        vMap.set(toggle[0], toggle[0]);
        vMap.set(toggle[1], toggle[1]);
    }
}

for (const [k, v] of Object.entries(FLIP_H)) {
    hMap.set(k, v);
}
for (const [k, v] of Object.entries(FLIP_V)) {
    vMap.set(k, v);
}

// Off-angle Diagonals Sequences
const OFF_ANGLE_1 = ['🯐', '🯔', '🯑', '🯕']; // Ring of 4
const OFF_ANGLE_2 = ['🯒', '🯖', '🯓', '🯗']; // Ring of 4
const OFF_ANGLE_V = ['🯘', '🯙', '🯚', '🯛']; // Edge-centered bridges (UL-UR, UR-LR, LR-LL, LL-UL)

for (const ring of [OFF_ANGLE_1, OFF_ANGLE_2, OFF_ANGLE_V]) {
    for (let i = 0; i < ring.length; i++) {
        cwMap.set(ring[i], ring[(i + 1) % ring.length]);
        ccwMap.set(ring[i], ring[(i + ring.length - 1) % ring.length]);
        rot180Map.set(ring[i], ring[(i + 2) % ring.length]);
    }
}
// H-Flip for Off-angles
hMap.set('🯐', '🯓'); hMap.set('🯓', '🯐');
hMap.set('🯑', '🯒'); hMap.set('🯒', '🯑');
hMap.set('🯔', '🯖'); hMap.set('🯖', '🯔');
hMap.set('🯕', '🯗'); hMap.set('🯗', '🯕');
hMap.set('🯘', '🯘'); hMap.set('🯚', '🯚');
hMap.set('🯙', '🯛'); hMap.set('🯛', '🯙');

// V-Flip for Off-angles
vMap.set('🯐', '🯑'); vMap.set('🯑', '🯐');
vMap.set('🯓', '🯒'); vMap.set('🯒', '🯓');
vMap.set('🯔', '🯗'); vMap.set('🯗', '🯔');
vMap.set('🯕', '🯖'); vMap.set('🯖', '🯕');
vMap.set('🯘', '🯚'); vMap.set('🯚', '🯘');
vMap.set('🯙', '🯙'); vMap.set('🯛', '🯛');

// Block Diagonals (Legacy Computing U+1FB3C - U+1FB67)
const blockDiagonalsPairs = [
    ['🬼', '🭇', '🭗', '🭙'], ['🬽', '🭈', '🭘', '🭛'], ['🬾', '🭉', '🭙', '🭙'], ['🬿', '🭊', '🭚', '🭛'],
    ['🭀', '🭋', '🭛', '🭚'], ['🭁', '🭌', '🭒', '🭌'], ['🭂', '🭍', '🭓', '🭐'], ['🭃', '🭎', '🭔', '🭌'],
    ['🭄', '🭏', '🭕', '🭐'], ['🭅', '🭐', '🭖', '🭍'], ['🭆', '🭑', '🭧', '🭆'], ['🭇', '🬼', '🭢', '🬼'],
    ['🭈', '🬽', '🭣', '🭀'], ['🭉', '🬾', '🭤', '🬼'], ['🭊', '🬿', '🭥', '🭀'], ['🭋', '🭀', '🭦', '🬽'],
    ['🭌', '🭁', '🭝', '🭟'], ['🭍', '🭂', '🭞', '🭡'], ['🭎', '🭃', '🭟', '🭟'], ['🭏', '🭄', '🭠', '🭡'],
    ['🭐', '🭅', '🭡', '🭠'], ['🭑', '🭆', '🭜', '🭑'], ['🭒', '🭝', '🭁', '🭃'], ['🭓', '🭞', '🭂', '🭅'],
    ['🭔', '🭟', '🭃', '🭃'], ['🭕', '🭠', '🭄', '🭅'], ['🭖', '🭡', '🭅', '🭄'], ['🭗', '🭢', '🬼', '🭢'],
    ['🭘', '🭣', '🬽', '🭦'], ['🭙', '🭤', '🬾', '🭢'], ['🭚', '🭥', '🬿', '🭦'], ['🭛', '🭦', '🭀', '🭣'],
    ['🭜', '🭧', '🭑', '🭜'], ['🭝', '🭒', '🭌', '🭒'], ['🭞', '🭓', '🭍', '🭖'], ['🭟', '🭔', '🭎', '🭒'],
    ['🭠', '🭕', '🭏', '🭖'], ['🭡', '🭖', '🭐', '🭓'], ['🭢', '🭗', '🭇', '🭉'], ['🭣', '🭘', '🭈', '🭋'],
    ['🭤', '🭙', '🭉', '🭉'], ['🭥', '🭚', '🭊', '🭋'], ['🭦', '🭛', '🭋', '🭊'], ['🭧', '🭜', '🭆', '🭧']
];

for (const [char, hFlip, vFlip, cw90] of blockDiagonalsPairs) {
    hMap.set(char, hFlip);
    vMap.set(char, vFlip);
    cwMap.set(char, cw90);
    // ccw is implicit by tracing cw logic reverse
}

for (const [char, _, __, cw90] of blockDiagonalsPairs) {
    // Find ccw90 (what character maps to 'char' via cw90)
    for (const [ccwChar, ___, ____, cw] of blockDiagonalsPairs) {
        if (cw === char) {
            ccwMap.set(char, ccwChar);
            break;
        }
    }
    // Set 180 as cw90 applied twice
    let cwNext = cw90;
    if (cwMap.has(cwNext)) {
        rot180Map.set(char, cwMap.get(cwNext)!);
    }
}

// Complex Sextant Mapping (U+1FB00 - U+1FB3B) block
function getSextantBits(char: string): number {
    if (char === ' ') return 0;
    if (char === '▌') return 21; // 010101
    if (char === '▐') return 42; // 101010
    if (char === '█') return 63; // 111111
    
    const cp = char.codePointAt(0);
    if (!cp || cp < 0x1FB00 || cp > 0x1FB3B) return -1;
    
    let val = cp - 0x1FB00 + 1;
    if (val >= 21) val++;
    if (val >= 42) val++;
    return val;
}

function getSextantChar(val: number): string {
    if (val === 0) return ' ';
    if (val === 21) return '▌';
    if (val === 42) return '▐';
    if (val === 63) return '█';
    
    let offset = val - 1;
    if (offset >= 20) offset--;
    if (offset >= 40) offset--;
    
    return String.fromCodePoint(0x1FB00 + offset);
}

function flipSextantH(char: string): string {
    const val = getSextantBits(char);
    if (val === -1) return char;
    // Swap 1<->2, 3<->4, 5<->6
    const b1 = val & 1; const b2 = (val >> 1) & 1;
    const b3 = (val >> 2) & 1; const b4 = (val >> 3) & 1;
    const b5 = (val >> 4) & 1; const b6 = (val >> 5) & 1;
    
    const newVal = (b2) | (b1 << 1) | (b4 << 2) | (b3 << 3) | (b6 << 4) | (b5 << 5);
    return getSextantChar(newVal);
}

function flipSextantV(char: string): string {
    const val = getSextantBits(char);
    if (val === -1) return char;
    // Swap 1<->5, 2<->6
    const b1 = val & 1; const b2 = (val >> 1) & 1;
    const b3 = (val >> 2) & 1; const b4 = (val >> 3) & 1;
    const b5 = (val >> 4) & 1; const b6 = (val >> 5) & 1;
    
    const newVal = (b5) | (b6 << 1) | (b3 << 2) | (b4 << 3) | (b1 << 4) | (b2 << 5);
    return getSextantChar(newVal);
}

export function transformCharacter(char: string, mode: 'cw90' | 'ccw90' | '180' | 'flip-h' | 'flip-v' | 'free'): string {
    if (mode === 'cw90' && cwMap.has(char)) return cwMap.get(char)!;
    if (mode === 'ccw90' && ccwMap.has(char)) return ccwMap.get(char)!;
    if (mode === '180' && rot180Map.has(char)) return rot180Map.get(char)!;
    if (mode === 'flip-h') {
        if (hMap.has(char)) return hMap.get(char)!;
        return flipSextantH(char);
    }
    if (mode === 'flip-v') {
        if (vMap.has(char)) return vMap.get(char)!;
        return flipSextantV(char);
    }
    return char;
}
