import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import { Backdrop } from "@/components/Backdrop";
import { ShellProvider } from "@/components/Shell";
import { Sidebar } from "@/components/Sidebar";
import { THEME_INIT_SCRIPT } from "@/components/ThemeToggle";
import { TopBar } from "@/components/TopBar";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Ledgerwatch · XRPL Transaction Monitoring",
  description: "Suspicious transaction detection on the XRP Ledger (LightGBM v2)",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full text-ink">
        <Backdrop />
        <ShellProvider>
          <div className="flex min-h-screen">
            <Suspense fallback={<aside className="hidden w-60 shrink-0 border-r border-line bg-panel lg:block" />}>
              <Sidebar />
            </Suspense>
            <div className="flex min-w-0 flex-1 flex-col">
              <TopBar />
              <main className="mx-auto w-full min-w-0 max-w-[1440px] flex-1 px-3 py-5 sm:px-5 lg:px-8 lg:py-6">{children}</main>
            </div>
          </div>
        </ShellProvider>
      </body>
    </html>
  );
}
