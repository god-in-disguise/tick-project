export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function signedMoney(value: number): string {
  return `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`;
}

export function price(value: number, compact = false): string {
  if (!Number.isFinite(value)) return "--";
  const digits = value >= 1000 ? 2 : value >= 1 ? (compact ? 2 : 3) : 5;
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value);
}

export function percent(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function distance(from: number, to: number | null): string {
  if (!from || !to || !Number.isFinite(from) || !Number.isFinite(to)) return "--";
  return `${(Math.abs(from - to) / from * 100).toFixed(3)}%`;
}

export function shortAddress(address: string | undefined): string {
  if (!address) return "--";
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}
