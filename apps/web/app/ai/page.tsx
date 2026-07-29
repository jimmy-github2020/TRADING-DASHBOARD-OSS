"use client";

import { useMemo, useRef, useState } from "react";
import { twMarketData } from "./mockData/tw";
import { usMarketData } from "./mockData/us";
import { Screen1 } from "./screens/Screen1";
import { Screen2 } from "./screens/Screen2";
import { Screen3 } from "./screens/Screen3";
import type { MarketScope } from "./types";

const screens = [
  { id: "brief", eyebrow: "Screen 01", title: "第一屏：AI 摘要" },
  { id: "support", eyebrow: "Screen 02", title: "第二屏：支撐數據" },
  { id: "sentiment", eyebrow: "Screen 03", title: "第三屏：情緒 & 新聞" },
];

export default function AiPage() {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [activeScreen, setActiveScreen] = useState(0);
  const [marketScope, setMarketScope] = useState<MarketScope>("tw");
  const pageData = useMemo(() => (marketScope === "tw" ? twMarketData : usMarketData), [marketScope]);

  function scrollToScreen(index: number) {
    const container = scrollRef.current;
    const target = container?.children.item(index);
    if (!target) return;

    target.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveScreen(index);
  }

  function handleScroll() {
    const container = scrollRef.current;
    if (!container) return;

    const nextIndex = Math.round(container.scrollTop / Math.max(container.clientHeight, 1));
    const clampedIndex = Math.min(Math.max(nextIndex, 0), screens.length - 1);
    if (clampedIndex !== activeScreen) {
      setActiveScreen(clampedIndex);
    }
  }

  function selectMarketScope(nextScope: MarketScope) {
    setMarketScope(nextScope);
  }

  return (
    <main className="ai-page">
      <aside className="ai-left-rail" aria-label="AI market scope">
        <div className="ai-left-rail-title">標的切換</div>
        <button
          className={`ai-scope-button ${marketScope === "tw" ? "active" : ""}`}
          onClick={() => selectMarketScope("tw")}
          type="button"
        >
          <span>台股大盤</span>
          <small>TAIEX focus</small>
        </button>
        <button
          className={`ai-scope-button ${marketScope === "us" ? "active" : ""}`}
          onClick={() => selectMarketScope("us")}
          type="button"
        >
          <span>美股大盤</span>
          <small>S&P 500 focus</small>
        </button>
      </aside>

      <section className="ai-stage" aria-label="AI 摘要三屏">
        <div className="ai-scroll" onScroll={handleScroll} ref={scrollRef}>
          <section aria-labelledby="ai-screen-brief" className="ai-screen">
            <Screen1 data={pageData} marketScope={marketScope} />
          </section>
          <section aria-labelledby="ai-screen-support" className="ai-screen">
            <Screen2 marketScope={marketScope} />
          </section>
          <section aria-labelledby="ai-screen-sentiment" className="ai-screen">
            <Screen3 data={pageData} marketScope={marketScope} />
          </section>
        </div>

        <nav className="ai-screen-dots" aria-label="AI screen navigation">
          {screens.map((screen, index) => (
            <button
              aria-label={`前往${screen.title}`}
              aria-current={activeScreen === index ? "step" : undefined}
              className={`ai-screen-dot ${activeScreen === index ? "active" : ""}`}
              key={screen.id}
              onClick={() => scrollToScreen(index)}
              type="button"
            />
          ))}
        </nav>
      </section>
    </main>
  );
}
