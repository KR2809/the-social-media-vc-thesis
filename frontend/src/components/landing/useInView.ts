"use client";

import { useEffect, useRef, useState } from "react";

// Reveal-once scroll hook. `inView` flips true when >=15% of the element is
// visible, then stays true (we unobserve — sections reveal once, never re-hide).
// prefers-reduced-motion users get inView=true immediately so no content is
// gated behind animation for them.
export function useInView<T extends HTMLElement>(
  threshold = 0.15,
): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setInView(true);
      return;
    }

    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setInView(true);
            obs.unobserve(e.target);
          }
        }
      },
      { threshold },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);

  return [ref, inView];
}
