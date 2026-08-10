export function createRequire(): never {
    throw new Error('Node module loading is unavailable in the browser');
}
