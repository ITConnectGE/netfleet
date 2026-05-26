import type { Metadata } from "next";
import { Providers } from "@/components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "NetFleet",
    template: "%s · NetFleet",
  },
  description: "Multi-vendor network fleet management for MSPs.",
  applicationName: "NetFleet",
  authors: [{ name: "ITConnectGE", url: "https://itconnectge.ge" }],
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
