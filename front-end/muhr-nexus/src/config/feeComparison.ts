/**
 * Fee comparison shown on the Overview ("What a seller keeps from a Rs 1,000 job").
 *
 * TODO(author): the comparison rows below are PLACEHOLDERS, not measured fees. They use
 * generic labels on purpose. Before showing this to anyone, replace each row with a real,
 * sourced figure (name the service, put the fee percentage from its published pricing in
 * `feePercent`, and the pricing page in `sourceUrl`), or delete the row.
 * The UI labels the whole card "Illustrative, check current fees" until that is done.
 */

export interface FeeRow {
  name: string;
  /** Percentage of the job price taken as fees. */
  feePercent: number;
  note: string;
  /** Where the number comes from. Empty while the row is a placeholder. */
  sourceUrl: string;
}

/** The job price the card is drawn for, in rupees. */
export const JOB_PRICE_PKR = 1000;

/** Muhr's own fee: the registry's PLATFORM_FEE_PERCENT (shared/constants.py). */
export const MUHR_FEE_PERCENT = 2;

export const MUHR_ROW: FeeRow = {
  name: "Muhr",
  feePercent: MUHR_FEE_PERCENT,
  note: "Platform fee on each settled job. Lightning routing costs are not included.",
  sourceUrl: "",
};

// TODO(author): placeholder percentages, see the note at the top of this file.
export const COMPARISON_ROWS: FeeRow[] = [
  {
    name: "Typical card payment processor",
    feePercent: 3,
    note: "Placeholder. Percentage plus a fixed fee per charge on most plans.",
    sourceUrl: "",
  },
  {
    name: "Typical international payout service",
    feePercent: 5,
    note: "Placeholder. Often adds currency conversion on top.",
    sourceUrl: "",
  },
];

export function keeps(row: Pick<FeeRow, "feePercent">, price = JOB_PRICE_PKR): number {
  return Math.round((price * (100 - row.feePercent)) / 100);
}
