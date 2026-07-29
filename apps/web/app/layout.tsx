import type { Metadata } from "next";
import "./globals.css";
import { Header } from "./header";
import { Providers } from "./providers";
import { ThemeProvider } from "./theme-provider";

export const metadata: Metadata = {
  title: "Trading Dashboard",
  description: "Personal professional trading dashboard"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant" data-theme="dark">
      <body>
        <ThemeProvider>
          <Header />
          <Providers>{children}</Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
