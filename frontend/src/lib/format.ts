// Number / date formatting. Arabic UI keeps Latin digits for trading data.

let locale = "en-US";
export function setFormatLocale(lang: string) {
  locale = lang === "ar" ? "ar-u-nu-latn" : "en-US";
}

const cache = new Map<string, Intl.NumberFormat>();
function nf(opts: Intl.NumberFormatOptions) {
  const key = locale + JSON.stringify(opts);
  let f = cache.get(key);
  if (!f) {
    f = new Intl.NumberFormat(locale, opts);
    cache.set(key, f);
  }
  return f;
}

const isNum = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/** Adaptive precision for prices: 67,412.50 · 3.5218 · 0.00002413 */
export function fmtPrice(n: number | null | undefined, opts: { min?: number } = {}): string {
  if (!isNum(n)) return "—";
  const a = Math.abs(n);
  let digits: number;
  if (a >= 1000) digits = 2;
  else if (a >= 1) digits = 4;
  else if (a >= 0.01) digits = 5;
  else if (a === 0) digits = 2;
  else digits = Math.min(10, Math.max(6, -Math.floor(Math.log10(a)) + 3));
  return nf({ minimumFractionDigits: opts.min ?? Math.min(2, digits), maximumFractionDigits: digits }).format(n);
}

export function fmtNum(n: number | null | undefined, digits = 2): string {
  if (!isNum(n)) return "—";
  return nf({ minimumFractionDigits: 0, maximumFractionDigits: digits }).format(n);
}

export function fmtFixed(n: number | null | undefined, digits = 2): string {
  if (!isNum(n)) return "—";
  return nf({ minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

export function fmtUsd(n: number | null | undefined, digits = 2): string {
  if (!isNum(n)) return "—";
  return nf({ style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
}

export function fmtCompact(n: number | null | undefined, prefix = ""): string {
  if (!isNum(n)) return "—";
  return prefix + nf({ notation: "compact", maximumFractionDigits: 2 }).format(n);
}

export function fmtPct(n: number | null | undefined, digits = 2, signed = true): string {
  if (!isNum(n)) return "—";
  const s = nf({ minimumFractionDigits: digits, maximumFractionDigits: digits }).format(Math.abs(n));
  const sign = !signed ? (n < 0 ? "-" : "") : n > 0 ? "+" : n < 0 ? "-" : "";
  return `${sign}${s}%`;
}

export function fmtAmount(n: number | null | undefined): string {
  if (!isNum(n)) return "—";
  const a = Math.abs(n);
  const digits = a >= 1000 ? 2 : a >= 1 ? 4 : 8;
  return nf({ maximumFractionDigits: digits }).format(n);
}

export function trendClass(n: number | null | undefined) {
  if (!isNum(n) || n === 0) return "text-muted";
  return n > 0 ? "text-up" : "text-down";
}

export function toDate(v: string | number | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === "") return null;
  if (v instanceof Date) return v;
  if (typeof v === "number") return new Date(v < 1e12 ? v * 1000 : v);
  // backend sends naive UTC ISO strings (and RFC 822 "… GMT" from raw datetimes)
  const s = /[zZ]|[+-]\d\d:?\d\d$|GMT$/.test(v) ? v : `${v}Z`;
  let d = new Date(s);
  if (Number.isNaN(d.getTime())) d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDateTime(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

export function fmtDate(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(d);
}

export function fmtTime(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "—";
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(d);
}

export function timeAgo(v: string | number | Date | null | undefined): string {
  const d = toDate(v);
  if (!d) return "—";
  const sec = Math.round((d.getTime() - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale.startsWith("ar") ? "ar" : "en", { numeric: "auto" });
  const abs = Math.abs(sec);
  if (abs < 60) return rtf.format(sec, "second");
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  if (abs < 2592000) return rtf.format(Math.round(sec / 86400), "day");
  return fmtDate(d);
}

export function baseOf(symbol: string) {
  return (symbol || "").split("/")[0];
}

export function quoteOf(symbol: string) {
  return (symbol || "").split("/")[1] ?? "USDT";
}

/** URL-safe symbol: BTC/USDT <-> BTC-USDT */
export const symbolToSlug = (s: string) => s.replace("/", "-");
export const slugToSymbol = (s: string) => s.replace("-", "/").toUpperCase();
