import { describe, expect, it } from "vitest";
import { formatPkr, toPkr } from "./pkr";

const RATE = 0.28; // Rs per sat (about Rs 28,000,000 per BTC)

describe("formatPkr", () => {
  it("shows two decimals under Rs 10", () => {
    expect(formatPkr(0, RATE)).toBe("Rs 0.00");
    expect(formatPkr(1, RATE)).toBe("Rs 0.28");
    expect(formatPkr(10, RATE)).toBe("Rs 2.80");
  });
  it("drops decimals from Rs 10 up and adds thousands separators", () => {
    expect(formatPkr(999, RATE)).toBe("Rs 280");
    expect(formatPkr(1_000_000, RATE)).toBe("Rs 280,000");
  });
  it("does not print Rs 10.00 for a value that rounds up to ten", () => {
    expect(formatPkr(35.71, 0.28)).toBe("Rs 10");
  });
  it("is blank when there is no rate or amount", () => {
    expect(formatPkr(null, RATE)).toBe("–");
    expect(formatPkr(5, null)).toBe("–");
    expect(formatPkr(NaN, RATE)).toBe("–");
  });
  it("keeps the sign of a negative amount", () => {
    expect(formatPkr(-100, RATE)).toBe("-Rs 28");
  });
});

describe("toPkr", () => {
  it("multiplies by the sat rate", () => {
    expect(toPkr(100, { sats_pkr: 0.5 })).toBe(50);
    expect(toPkr(100, null)).toBeNull();
  });
});
