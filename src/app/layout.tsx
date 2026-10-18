import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "OtoClinic — Spare Part Otomotif", template: "%s · OtoClinic" },
  description: "Temukan spare part mobil dan motor dengan informasi kondisi dan kecocokan kendaraan yang jelas.",
  applicationName: "OtoClinic",
  manifest: "/manifest.webmanifest",
};
export const viewport: Viewport = { themeColor: "#101b2b", width: "device-width", initialScale: 1, maximumScale: 5 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body>{children}</body></html>;
}
