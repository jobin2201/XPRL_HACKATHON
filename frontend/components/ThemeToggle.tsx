"use client";

// Animated day/night switch: a sky track (blue by day, starry by night) with a sliding sun ☀️ / moon 🌙 knob.
import { useEffect, useState } from "react";

type Theme = "dark" | "light";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    setTheme((document.documentElement.dataset.theme as Theme) || "dark");
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    const root = document.documentElement;
    root.classList.add("theme-anim");
    root.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {}
    setTheme(next);
    window.setTimeout(() => root.classList.remove("theme-anim"), 600);
  }

  const day = theme === "light";
  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={day}
      aria-label={day ? "Switch to dark mode" : "Switch to light mode"}
      title={day ? "Light mode · click for dark" : "Dark mode · click for light"}
      className="relative h-8 w-[64px] shrink-0 overflow-hidden rounded-full border border-line-strong transition-[background] duration-500"
      style={{
        background: day ? "linear-gradient(135deg,#8fd3ff 0%,#5fb6f5 60%,#ffd27a 140%)" : "linear-gradient(135deg,#0b1430 0%,#1b2552 70%,#3a2e6e 140%)",
      }}
    >
      {/* night: twinkling stars */}
      <span className={`pointer-events-none absolute inset-0 transition-opacity duration-500 ${day ? "opacity-0" : "opacity-100"}`}>
        {[
          [10, 7, 0],
          [20, 18, 0.6],
          [30, 9, 1.2],
          [16, 24, 1.8],
        ].map(([x, y, d], i) => (
          <span key={i} className="twinkle absolute h-[2px] w-[2px] rounded-full bg-white" style={{ left: x, top: y, animationDelay: `${d}s` }} />
        ))}
      </span>
      {/* day: little clouds */}
      <span className={`pointer-events-none absolute inset-0 transition-all duration-500 ${day ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"}`}>
        <span className="absolute left-[34px] top-[17px] h-[7px] w-[16px] rounded-full bg-white/85" />
        <span className="absolute left-[44px] top-[8px] h-[5px] w-[11px] rounded-full bg-white/70" />
      </span>
      {/* the knob slides and turns */}
      <span
        className="absolute top-[3px] grid h-6 w-6 place-items-center rounded-full text-[15px] leading-none shadow-md transition-all duration-500 ease-[cubic-bezier(.68,-0.35,.27,1.35)]"
        style={{
          left: day ? 3 : 35,
          transform: `rotate(${day ? 0 : 360}deg)`,
          background: day ? "#fff4cc" : "#c9d3f0",
          boxShadow: day ? "0 0 12px 3px rgba(255,200,60,0.65)" : "0 0 10px 2px rgba(180,200,255,0.45)",
        }}
      >
        <span className={day ? "spin-slow" : ""} aria-hidden>
          {day ? "☀️" : "🌙"}
        </span>
      </span>
    </button>
  );
}

// Runs before the page paints, so a saved light theme never flashes dark first.
export const THEME_INIT_SCRIPT = `try{var d=document.documentElement,t=localStorage.getItem("theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"}d.dataset.theme=t;d.dataset.sidebar=localStorage.getItem("sidebar")==="collapsed"?"collapsed":"open"}catch(e){document.documentElement.dataset.theme="dark"}`;
