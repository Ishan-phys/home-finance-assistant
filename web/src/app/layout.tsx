import type { Metadata } from "next";
import { Fraunces, Geist_Mono, Hanken_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/common/providers";

// Hanken Grotesk for the interface, Fraunces for headings and the figures that matter.
const sans = Hanken_Grotesk({
  variable: "--font-ui",
  subsets: ["latin"],
});

const display = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI CFO",
  description: "A local personal finance ledger and assistant.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${display.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-background text-foreground">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
