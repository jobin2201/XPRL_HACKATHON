"use client";

// Layout state shared by the sidebar and the top bar.
// - open: the slide-in drawer on phones and tablets (React state; it always starts closed, so no mismatch).
// - collapsed (desktop): kept as <html data-sidebar="collapsed">, set before paint by the init script and
//   styled in globals.css, so the server HTML and the first browser render are identical (no hydration errors).
import { createContext, useContext, useEffect, useState } from "react";

type Shell = { open: boolean; setOpen: (v: boolean) => void; toggleCollapsed: () => void };
const Ctx = createContext<Shell>({ open: false, setOpen: () => {}, toggleCollapsed: () => {} });

export function ShellProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    // close the drawer when the window grows to desktop size
    const mq = window.matchMedia("(min-width: 1024px)");
    const onWide = () => mq.matches && setOpen(false);
    window.addEventListener("keydown", onKey);
    mq.addEventListener("change", onWide);
    return () => {
      window.removeEventListener("keydown", onKey);
      mq.removeEventListener("change", onWide);
    };
  }, []);

  // lock page scroll while the drawer is open on a phone
  useEffect(() => {
    document.documentElement.style.overflow = open ? "hidden" : "";
  }, [open]);

  const toggleCollapsed = () => {
    const root = document.documentElement;
    const next = root.dataset.sidebar === "collapsed" ? "open" : "collapsed";
    root.dataset.sidebar = next;
    try {
      localStorage.setItem("sidebar", next);
    } catch {}
  };

  return <Ctx.Provider value={{ open, setOpen, toggleCollapsed }}>{children}</Ctx.Provider>;
}

export const useShell = () => useContext(Ctx);
