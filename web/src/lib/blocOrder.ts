/** Vänsterblocket visas alltid till vänster om Högerblocket, oavsett vem som sitter i regering. */
const RANK: Record<string, number> = { "Vänsterblocket": 0, "Högerblocket": 1 };
export const blocRank = (name: string) => RANK[name] ?? 2;
export const sortBlocs = <T>(items: readonly T[], nameOf: (t: T) => string): T[] =>
  [...items].sort((a, b) => blocRank(nameOf(a)) - blocRank(nameOf(b)));
export const sortBlocKeys = <V>(obj: Record<string, V>): Record<string, V> =>
  Object.fromEntries(sortBlocs(Object.entries(obj), ([k]) => k));
