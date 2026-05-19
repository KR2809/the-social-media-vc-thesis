import type { Metadata } from "next";
import "./globals.css";

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
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;0,8..60,700;1,8..60,400;1,8..60,500&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
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
