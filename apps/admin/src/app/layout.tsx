import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "OtoClinic Admin — Operasional", template: "%s · OtoClinic" },
  description: "Workspace operasional OtoClinic.",
  applicationName: "OtoClinic",
  manifest: "/manifest.webmanifest",
};
export const viewport: Viewport = { themeColor: "#101b2b", width: "device-width", initialScale: 1, maximumScale: 5 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="id"><body>{children}</body></html>;
}
