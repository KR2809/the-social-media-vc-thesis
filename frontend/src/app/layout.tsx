import type { Metadata, Viewport } from "next";
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

// metadataBase lets Next resolve the generated OG image to an absolute URL.
// Override per-environment via NEXT_PUBLIC_SITE_URL (Vercel project URL).
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3001";

const title = "From Social Signals to Pre-Seed Allocation — Thesis Demo";
const description =
  "A systematic framework for pre-seed venture capital, built from free public social-media signals. Replay any date, score the picks against naïve baselines, and drill into the evidence. Kristian Ratkov · EDHEC BSc Global Business.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title,
  description,
  applicationName: "Thesis Demo",
  authors: [{ name: "Kristian Ratkov" }],
  openGraph: {
    type: "website",
    title,
    description,
    siteName: "From Social Signals to Pre-Seed Allocation",
    locale: "en_GB",
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAFAF8" },
    { media: "(prefers-color-scheme: dark)", color: "#0B0F1C" },
  ],
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
