import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Clavis Terminal - The key to understand F&O markets",
  description: "Clavis Terminal: real-time open interest build-up screener for F&O stocks. Detects big-player positioning via live OI flows.",
};

export const viewport: Viewport = {
  themeColor: "#0a0a0a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col bg-bg text-text antialiased">
        {children}
      </body>
    </html>
  );
}
