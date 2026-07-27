import type { Theme } from "./types";

const themes: Theme[] = [
  { accent: "#ff9f2e", glow: "#ffb54f", top: "#0d1717", bottom: "#111711" },
  { accent: "#42d7c0", glow: "#7aebda", top: "#0b1819", bottom: "#0b1517" },
  { accent: "#55a6ff", glow: "#84c0ff", top: "#0b151b", bottom: "#101722" },
  { accent: "#e9c55d", glow: "#ffe28b", top: "#16160f", bottom: "#121612" },
  { accent: "#ef7d6d", glow: "#ffab9d", top: "#181311", bottom: "#151112" }
];

export function themeFor(market: string): Theme {
  let hash = 0;
  for (const character of market) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  return themes[Math.abs(hash) % themes.length];
}
