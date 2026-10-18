import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata:Metadata={title:{default:"OtoClinic — Marketplace Spare Part Otomotif",template:"%s · OtoClinic"},description:"Temukan spare part mobil dan motor dengan informasi kondisi dan kecocokan kendaraan yang jelas.",applicationName:"OtoClinic",manifest:"/manifest.webmanifest",appleWebApp:{capable:true,statusBarStyle:"default",title:"OtoClinic"},formatDetection:{telephone:false}};
export const viewport:Viewport={themeColor:"#101b2b",width:"device-width",initialScale:1,maximumScale:5,viewportFit:"cover"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="id"><head><meta name="mobile-web-app-capable" content="yes"/><link rel="apple-touch-icon" href="/icons/icon-192.svg"/></head><body>{children}</body></html>}
