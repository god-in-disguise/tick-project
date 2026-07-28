import type { Theme } from "./types";

const assetThemes: Record<string, Theme> = {
  BTC: { accent: "#f7931a", glow: "#ffb45c", top: "#0b0804", bottom: "#080706" },
  ZEC: { accent: "#ecb244", glow: "#ffd56f", top: "#0b0904", bottom: "#080706" },
  ETH: { accent: "#aeb7c6", glow: "#d6dce5", top: "#08090b", bottom: "#070809" },
  SOL: { accent: "#9945ff", glow: "#c08aff", top: "#09060b", bottom: "#070608" },
  HYPE: { accent: "#50e3c2", glow: "#8aefd8", top: "#050a09", bottom: "#060807" },
  BNB: { accent: "#f3ba2f", glow: "#f8d56f", top: "#0b0904", bottom: "#080706" },
  XAU: { accent: "#d8ac4c", glow: "#e8cd78", top: "#0a0805", bottom: "#080706" },
  XAG: { accent: "#aeb9c2", glow: "#d7dfe5", top: "#080a0b", bottom: "#070809" },
  FX: { accent: "#8fcfc5", glow: "#b4e0d9", top: "#050908", bottom: "#060807" }
};

const fallbackThemes = Object.values(assetThemes);

export function themeFor(market: string): Theme {
  const normalized = market.toUpperCase();
  for (const symbol of ["BTC", "ZEC", "ETH", "SOL", "HYPE", "BNB", "XAU", "XAG"]) {
    if (normalized.includes(symbol)) return assetThemes[symbol];
  }
  if (normalized.includes("USD") || normalized.includes("EUR")) return assetThemes.FX;
  let hash = 0;
  for (const character of market) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return fallbackThemes[Math.abs(hash) % fallbackThemes.length];
}
