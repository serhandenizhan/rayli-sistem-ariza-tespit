import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Raylı Sistem — Canlı Arıza İzleme",
  description: "Raylı sistem dingillerinde canlı arıza tespiti ve doğrulama panosu",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
