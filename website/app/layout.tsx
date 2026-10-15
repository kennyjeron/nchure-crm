import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "NCHURE Technologies — From Circuits to Intelligence", description: "NCHURE Technologies connects AI, automation, digital platforms and intelligent business systems.", applicationName: "NCHURE Technologies", metadataBase: new URL("https://nchure.tech"), openGraph: { title: "NCHURE Technologies — From Circuits to Intelligence", description: "We engineer what comes next.", type: "website" } };
export const viewport: Viewport = { themeColor: "#171a19", width: "device-width", initialScale: 1 };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
