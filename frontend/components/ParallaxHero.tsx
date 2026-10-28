"use client";

// Page header with depth: glowing orbs, a dotted grid and rings move at different speeds when you
// scroll and when you move the mouse over it. Respects "reduce motion".
import { useEffect, useRef } from "react";

export function ParallaxHero({
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let mx = 0;
    let my = 0;
    let raf = 0;
    const paint = () => {
      raf = 0;
      const sy = window.scrollY;
      el.querySelectorAll<HTMLElement>("[data-depth]").forEach((layer) => {
        const d = Number(layer.dataset.depth);
        layer.style.transform = `translate3d(${mx * d * 26}px, ${my * d * 18 + sy * d * 0.35}px, 0)`;
      });
    };
    const queue = () => {
      if (!raf) raf = requestAnimationFrame(paint);
    };
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      mx = (e.clientX - r.left) / r.width - 0.5;
      my = (e.clientY - r.top) / r.height - 0.5;
      queue();
    };
    const onLeave = () => {
      mx = 0;
      my = 0;
      queue();
    };
    window.addEventListener("scroll", queue, { passive: true });
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      window.removeEventListener("scroll", queue);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div ref={box} className="hero-in relative mb-6 overflow-hidden rounded-2xl border border-line bg-panel p-5 sm:p-7">
      {/* depth layers (furthest first) */}
      <div data-depth="0.25" className="pointer-events-none absolute inset-0 transition-transform duration-300 ease-out">
        <div className="hero-dots absolute -inset-10 opacity-60" />
      </div>
      <div data-depth="0.6" className="pointer-events-none absolute -right-20 -top-28 h-80 w-80 rounded-full blur-3xl transition-transform duration-300 ease-out" style={{ background: "radial-gradient(circle, var(--blob1), transparent 70%)" }} />
      <div data-depth="0.9" className="pointer-events-none absolute -bottom-32 left-1/3 h-72 w-72 rounded-full blur-3xl transition-transform duration-300 ease-out" style={{ background: "radial-gradient(circle, var(--blob2), transparent 70%)" }} />
      <div data-depth="1.3" className="pointer-events-none absolute right-10 top-6 hidden h-28 w-28 rounded-full border border-line-strong opacity-50 transition-transform duration-300 ease-out sm:block">
        <div className="float-slow absolute inset-3 rounded-full border border-dashed border-line-strong" />
      </div>
      <div data-depth="1.8" className="pointer-events-none absolute right-36 top-16 hidden h-3 w-3 rounded-full bg-accent opacity-70 shadow-[0_0_14px_var(--accent)] transition-transform duration-300 ease-out sm:block" />

      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-accent">{eyebrow}</p>}
          <h1 className="mt-1 bg-gradient-to-r from-[var(--ink)] to-[var(--accent)] bg-clip-text text-2xl font-semibold tracking-tight text-transparent sm:text-[28px]">{title}</h1>
          {description && <div className="mt-1 max-w-3xl text-[13px] text-ink-2">{description}</div>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children && <div className="relative">{children}</div>}
    </div>
  );
}
