import type { Metadata } from "next";
import { Carlito, JetBrains_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import "./globals.css";

// Carlito is the libre, metric-compatible substitute for Calibri. We expose
// it through --font-sans so the stack in globals.css can prefer the real
// Calibri on systems that have it (Windows / Office) and fall back to
// Carlito everywhere else.
const carlito = Carlito({
  subsets: ["latin", "latin-ext", "cyrillic"],
  weight: ["400", "700"],
  style: ["normal", "italic"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "NetFleet",
    template: "%s · NetFleet",
  },
  description: "Multi-vendor network fleet management for MSPs.",
  applicationName: "NetFleet",
  authors: [{ name: "ITConnect", url: "https://itconnect.ge" }],
  // Explicit icon mapping: Next.js auto-picks /app/icon.svg, but some
  // browsers still hit /favicon.ico first. Point them straight at the
  // SVG so the 404 noise stops.
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    shortcut: "/icon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${carlito.variable} ${mono.variable}`} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
