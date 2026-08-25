export function createRequire(_specifier: string): never {
    throw new Error('Node module loading is unavailable in the browser');
}
