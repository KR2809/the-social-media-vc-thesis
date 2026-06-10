"use client";

import { useEffect, useRef, useState } from "react";

// Progressive-enhancement scroll reveal.
//
// SSR / pre-hydration / no-JS: NO hiding class -> content fully visible
// (screenshots, SEO and no-JS readers always see the page).
// After hydration: elements still below the viewport get the `lp-reveal`
// hidden state, then animate in (`lp-in`) when >=15% visible, once.
// Elements already on screen at mount stay visible (no pop).
// prefers-reduced-motion: never hidden, never animated.
//
// Returns [ref, className] — append className to the element's class list.
export function useReveal<T extends HTMLElement>(
  threshold = 0.15,
): [React.RefObject<T | null>, string] {
  const ref = useRef<T | null>(null);
  const [cls, setCls] = useState("");

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const rect = el.getBoundingClientRect();
    const alreadyVisible = rect.top < window.innerHeight && rect.bottom > 0;
    if (alreadyVisible) return; // on screen at mount -> leave it visible

    setCls("lp-reveal"); // hide, then animate in on intersection
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setCls("lp-reveal lp-in");
            obs.unobserve(e.target);
          }
        }
      },
      { threshold },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);

  return [ref, cls];
}
