import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import "./globals.css";

// Self-host the three font families via next/font/google. CSS variables
// (--font-serif / --font-sans / --font-mono) are exposed on <body>;
// demo.css picks them up. No external requests on first paint, no
// next/no-page-custom-font lint warning.
const sans = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-sans",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-mono",
});

const serif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-serif",
});

export const metadata: Metadata = {
  title: "From Social Signals to Pre-Seed Allocation — Thesis Demo",
  description:
    "Working artefact for thesis defence. Kristian Ratkov, supervised by George Tovstiga, EDHEC MSc Finance.",
};

// Inline before-interactive script that resolves the theme synchronously
// from localStorage / system preference and sets data-theme on <html>
// before React hydrates. Prevents a flash of wrong theme on reload.
const themeBoot = `(function(){try{var s=localStorage.getItem('thesis-theme');var t=(s==='dark'||s==='light')?s:((window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light');document.documentElement.setAttribute('data-theme',t);}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${serif.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script
          id="theme-boot"
          // Inlined synchronously so it runs before React hydrates and
          // before first paint, avoiding a flash of wrong theme.
          dangerouslySetInnerHTML={{ __html: themeBoot }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
