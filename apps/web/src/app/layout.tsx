import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aster makes every experiment count",
  description:
    "Aster is a research prototype that helps researchers prioritize which compounds to test next, combining activity predictions, uncertainty estimates and assay results.",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className="antialiased"
    >
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
