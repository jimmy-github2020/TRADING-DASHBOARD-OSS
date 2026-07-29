"use client";

import { LineChart, Moon, RefreshCw, Sun } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useTheme } from "./theme-provider";

type Health = {
  status: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8011";
const wsBaseUrl = apiBaseUrl.replace(/^http/, "ws");

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/strategies", label: "策略中心" },
  { href: "/analysis", label: "量化分析" },
  { href: "/universe", label: "股票庫" },
  { href: "/backtest", label: "Backtest" },
  { href: "/ai", label: "AI 摘要" },
  { href: "/notifications", label: "通知設定" }
];

export function Header() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const [clockText, setClockText] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    function updateClock() {
      setClockText(new Date().toLocaleTimeString("zh-TW", { hour12: false }));
    }

    updateClock();
    const timer = window.setInterval(updateClock, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let mounted = true;

    async function loadHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, { cache: "no-store" });
        const data = (await response.json()) as Health;
        if (mounted) setHealth(data);
      } catch {
        if (mounted) setHealth(null);
      }
    }

    loadHealth();
    const timer = window.setInterval(loadHealth, 15000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const socket = new WebSocket(`${wsBaseUrl}/ws/quotes`);
    socket.addEventListener("open", () => {
      setWsConnected(true);
      socket.send("ping");
    });
    socket.addEventListener("close", () => setWsConnected(false));
    socket.addEventListener("error", () => setWsConnected(false));
    return () => socket.close();
  }, []);

  const connected = health?.status === "ok" && wsConnected;

  return (
    <header className="terminal-header global-header">
      <div className="brand-lockup">
        <div className="brand-mark">
          <LineChart size={20} />
        </div>
        <div>
          <p>TRADING DASHBOARD</p>
          <span>Market monitor</span>
        </div>
      </div>
      <nav className="header-nav" aria-label="Primary navigation">
        {navItems.map((item) => (
          <a className={pathname === item.href ? "active" : ""} href={item.href} key={item.href}>
            {item.label}
          </a>
        ))}
      </nav>
      <div className="header-tools">
        <div className="time-chip">{clockText}</div>
        <div className="connection-chip" title={connected ? "connected" : "disconnected"}>
          <span className={`connection-dot ${connected ? "connected" : "disconnected"}`} />
          {connected ? "Connected" : "Disconnected"}
        </div>
        <button
          className="theme-toggle-btn"
          aria-label={theme === "dark" ? "切換日間模式" : "切換夜間模式"}
          onClick={toggleTheme}
          title={theme === "dark" ? "切換日間模式" : "切換夜間模式"}
          type="button"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button className="icon-button" aria-label="Refresh" onClick={() => window.location.reload()}>
          <RefreshCw size={16} />
        </button>
      </div>
    </header>
  );
}
