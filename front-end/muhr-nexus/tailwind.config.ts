import type { Config } from "tailwindcss";

/*
 * Muhr "settlement office" palette.
 *   paper    #E9ECE6  cool ledger paper (page)
 *   sheet    #F6F7F3  raised sheet (panels)
 *   ink      #172034  navy ink (text, primary marks)
 *   graphite #5E6675  secondary text
 *   rule     #CDD2C8  hairlines
 *   seal     #9E2A1F  wax seal: used only for sealed/locked things and the main action
 *   settled  #2E6B4E  money arrived
 *   pending  #A86E12  waiting on someone
 */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  prefix: "",
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1240px" } },
    extend: {
      colors: {
        border: "hsl(var(--border) / <alpha-value>)",
        input: "hsl(var(--input) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        primary: { DEFAULT: "hsl(var(--primary) / <alpha-value>)", foreground: "hsl(var(--primary-foreground) / <alpha-value>)" },
        secondary: { DEFAULT: "hsl(var(--secondary) / <alpha-value>)", foreground: "hsl(var(--secondary-foreground) / <alpha-value>)" },
        destructive: { DEFAULT: "hsl(var(--destructive) / <alpha-value>)", foreground: "hsl(var(--destructive-foreground) / <alpha-value>)" },
        muted: { DEFAULT: "hsl(var(--muted) / <alpha-value>)", foreground: "hsl(var(--muted-foreground) / <alpha-value>)" },
        accent: { DEFAULT: "hsl(var(--accent) / <alpha-value>)", foreground: "hsl(var(--accent-foreground) / <alpha-value>)" },
        popover: { DEFAULT: "hsl(var(--popover) / <alpha-value>)", foreground: "hsl(var(--popover-foreground) / <alpha-value>)" },
        card: { DEFAULT: "hsl(var(--card) / <alpha-value>)", foreground: "hsl(var(--card-foreground) / <alpha-value>)" },
        paper: "hsl(var(--paper) / <alpha-value>)",
        sheet: "hsl(var(--sheet) / <alpha-value>)",
        ink: { DEFAULT: "hsl(var(--ink) / <alpha-value>)", soft: "hsl(var(--ink-soft) / <alpha-value>)" },
        graphite: "hsl(var(--graphite) / <alpha-value>)",
        rule: { DEFAULT: "hsl(var(--rule) / <alpha-value>)", strong: "hsl(var(--rule-strong) / <alpha-value>)" },
        seal: { DEFAULT: "hsl(var(--seal) / <alpha-value>)", deep: "hsl(var(--seal-deep) / <alpha-value>)", tint: "hsl(var(--seal-tint) / <alpha-value>)" },
        settled: { DEFAULT: "hsl(var(--settled) / <alpha-value>)", tint: "hsl(var(--settled-tint) / <alpha-value>)" },
        pending: { DEFAULT: "hsl(var(--pending) / <alpha-value>)", tint: "hsl(var(--pending-tint) / <alpha-value>)" },
      },
      fontFamily: {
        sans: ['"Archivo"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // Modular scale (1.25) anchored at a 15px body.
        "2xs": ["0.75rem", { lineHeight: "1.1rem" }],
        xs: ["0.8125rem", { lineHeight: "1.2rem" }],
        sm: ["0.875rem", { lineHeight: "1.35rem" }],
        base: ["0.9375rem", { lineHeight: "1.55rem" }],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
