export function toCssFontFamily(value: string): string {
  const trimmed = value.trim();
  if (trimmed.includes(',')) return trimmed;
  if (trimmed.startsWith("'") || trimmed.startsWith('"')) return trimmed;
  if (/\s/.test(trimmed)) return `"${trimmed}"`;
  return trimmed;
}