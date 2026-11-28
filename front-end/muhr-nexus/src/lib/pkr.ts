/** Rupee display for sat amounts. Display only: nothing is priced or settled in rupees. */

export interface Rates {
  btc_pkr: number;
  sats_pkr: number;
  source: string;
  fetched_at: string;
  stale: boolean;
}

/**
 * "Rs 2.80" under Rs 10 (two decimals), "Rs 280" and "Rs 280,000" from Rs 10 up.
 * `satsPkr` is rupees per satoshi.
 */
export function formatPkr(sats: number | null | undefined, satsPkr: number | null | undefined): string {
  if (sats == null || satsPkr == null || !Number.isFinite(sats) || !Number.isFinite(satsPkr)) return "–";
  const value = Math.abs(sats) * satsPkr;
  const sign = sats < 0 ? "-" : "";
  const twoDp = Math.round(value * 100) / 100;
  if (twoDp < 10) return `${sign}Rs ${twoDp.toFixed(2)}`;
  return `${sign}Rs ${Math.round(value).toLocaleString("en-US")}`;
}

/** Rupees for a sat amount, or null while no rate is known. */
export function toPkr(sats: number | null | undefined, rates: Pick<Rates, "sats_pkr"> | null | undefined): number | null {
  if (sats == null || !rates || !Number.isFinite(sats)) return null;
  return sats * rates.sats_pkr;
}
