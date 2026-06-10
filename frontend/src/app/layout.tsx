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

const title = "Founder Radar — an AI that spots founders before they launch";
const description =
  "An AI that spots future startup founders from their public posts — before they launch. Watch it replay the real test in the Time Machine: flagged a median of ~a year early, built only from free public data. Kristian Ratkov · EDHEC BBA thesis.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title,
  description,
  applicationName: "Founder Radar",
  authors: [{ name: "Kristian Ratkov" }],
  openGraph: {
    type: "website",
    title,
    description,
    siteName: "Founder Radar",
    locale: "en_GB",
  },
  twitter: {
    card: "summary_large_image",
    title,
    description,
  },
};

export const viewport: Viewport = {
  // Explicit mobile viewport. No maximumScale/userScalable — preserve
  // pinch-zoom (accessibility + useful for the dense graphs).
  width: "device-width",
  initialScale: 1,
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
