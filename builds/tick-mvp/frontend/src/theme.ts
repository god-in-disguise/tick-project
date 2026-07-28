import type { Theme } from "./types";

const surface = { top: "#050606", bottom: "#070808" };

const themes: Theme[] = [
  { accent: "#d7ad4f", glow: "#e7c979", ...surface },
  { accent: "#5b9dff", glow: "#86b8ff", ...surface },
  { accent: "#47d7cf", glow: "#81e7e1", ...surface },
  { accent: "#9d7cff", glow: "#beaaff", ...surface },
  { accent: "#b9a7d6", glow: "#d2c5e5", ...surface },
  { accent: "#d8b84c", glow: "#e8cf7b", ...surface },
  { accent: "#8fcfc5", glow: "#b4e0d9", ...surface }
];

export function themeFor(market: string): Theme {
  const normalized = market.toUpperCase();
  if (normalized.includes("BTC")) return themes[0];
  if (normalized.includes("ETH")) return themes[1];
  if (normalized.includes("SOL")) return themes[2];
  if (normalized.includes("HYPE")) return themes[3];
  if (normalized.includes("ZEC")) return themes[4];
  if (normalized.includes("BNB")) return themes[5];
  if (normalized.includes("USD") || normalized.includes("EUR")) return themes[6];
  let hash = 0;
  for (const character of market) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return themes[Math.abs(hash) % themes.length];
}
