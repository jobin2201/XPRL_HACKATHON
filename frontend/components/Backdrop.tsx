"use client";

// Fixed, soft aurora behind every page. The colour orbs drift slowly and move at different speeds
// with scroll and mouse (parallax). Pure decoration: no pointer events, hidden from screen readers.
import { useEffect, useRef } from "react";

export function Backdrop() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let mx = 0;
    let my = 0;
    let raf = 0;
    const paint = () => {
      raf = 0;
      const sy = window.scrollY;
      el.querySelectorAll<HTMLElement>("[data-depth]").forEach((o) => {
        const d = Number(o.dataset.depth);
        o.style.transform = `translate3d(${mx * d * 40}px, ${my * d * 30 - sy * d * 0.25}px, 0)`;
      });
    };
    const queue = () => {
      if (!raf) raf = requestAnimationFrame(paint);
    };
    const onMove = (e: PointerEvent) => {
      mx = e.clientX / window.innerWidth - 0.5;
      my = e.clientY / window.innerHeight - 0.5;
      queue();
    };
    window.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("scroll", queue);
      window.removeEventListener("pointermove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div ref={ref} aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div data-depth="0.4" className="absolute -left-40 -top-40 h-[520px] w-[520px] transition-transform duration-500 ease-out">
        <div className="drift-a h-full w-full rounded-full blur-3xl" style={{ background: "radial-gradient(circle, var(--blob1), transparent 65%)" }} />
      </div>
      <div data-depth="0.8" className="absolute -right-32 top-1/4 h-[460px] w-[460px] transition-transform duration-500 ease-out">
        <div className="drift-b h-full w-full rounded-full blur-3xl" style={{ background: "radial-gradient(circle, var(--blob2), transparent 65%)" }} />
      </div>
      <div data-depth="1.2" className="absolute bottom-[-180px] left-1/3 h-[420px] w-[420px] transition-transform duration-500 ease-out">
        <div className="drift-a h-full w-full rounded-full blur-3xl" style={{ background: "radial-gradient(circle, var(--blob3), transparent 65%)", animationDelay: "-6s" }} />
      </div>
    </div>
  );
}
