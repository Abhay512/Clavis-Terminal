import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg:        "#0a0a0a",
        surface:   "#101010",
        card:      "#131313",
        cardHover: "#1b1b1b",
        border:    "#2a2a2a",
        borderGlow:"#3a3a3a",

        text:      "#e8e8e8",
        muted:     "#a3a3a3",   // neutral-400 - readable secondary numbers
        faint:     "#737373",   // neutral-500 - de-emphasized labels/dividers

        green: {
          DEFAULT: "#4af6c3",
          dim:     "#4af6c30d",
          glow:    "#4af6c333",
          soft:    "#4af6c31a",
        },
        red: {
          DEFAULT: "#ff433d",
          dim:     "#ff433d0d",
          glow:    "#ff433d33",
          soft:    "#ff433d1a",
        },
        amber: {
          DEFAULT: "#ffa028",
          soft:    "#ffa0281a",
        },

        // accent - info only
        blue: {
          DEFAULT: "#6db3f2",
          soft:    "#6db3f21a",
          glow:    "#6db3f233",
        },
      },
      borderRadius: {
        none: "0",
        sm:   "1px",
        DEFAULT: "2px",
        md:   "2px",
        lg:   "2px",
        xl:   "2px",
        "2xl": "2px",
        "3xl": "2px",
        full: "9999px",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Fira Code'", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.7rem", { lineHeight: "1rem" }],
      },
      backgroundImage: {
        "green-glow": "none",
        "red-glow":   "none",
        "card-shine": "none",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.16, 1, 0.3, 1)",
        snap:   "cubic-bezier(0.4, 0, 0.2, 1)",
      },
      animation: {
        "pulse-dot":    "pulse-dot 2s ease-in-out infinite",
        "glow-in":      "glow-in 0.4s ease-out forwards",
        "slide-right":  "slide-right 0.35s cubic-bezier(0.16,1,0.3,1) both",
        "flash-green":  "flash-green 0.5s ease-out",
        "flash-red":    "flash-red 0.5s ease-out",
        "fade-in":      "fade-in 0.5s ease-out both",
        "count-up":     "count-up 0.3s ease-out",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1",   transform: "scale(1)" },
          "50%":      { opacity: "0.5", transform: "scale(0.8)" },
        },
        "glow-in": {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-right": {
          "0%":   { opacity: "0", transform: "translateX(24px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "flash-green": {
          "0%":   { backgroundColor: "rgba(0,220,130,0.25)" },
          "100%": { backgroundColor: "transparent" },
        },
        "flash-red": {
          "0%":   { backgroundColor: "rgba(255,77,109,0.25)" },
          "100%": { backgroundColor: "transparent" },
        },
        "fade-in": {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "count-up": {
          "0%":   { transform: "translateY(4px)", opacity: "0" },
          "100%": { transform: "translateY(0)",   opacity: "1" },
        },
      },
      boxShadow: {
        "card":       "none",
        "card-hover": "none",
        "green":      "none",
        "red":        "none",
        "blue":       "none",
      },
    },
  },
  plugins: [],
};

export default config;
