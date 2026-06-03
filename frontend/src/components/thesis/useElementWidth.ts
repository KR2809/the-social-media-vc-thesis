"use client";

import { useCallback, useRef, useState } from "react";

// Measures an element's content width via ResizeObserver. Returns
// [callbackRef, width]; width is 0 until the first measure, so callers fall
// back to a fixed default.
//
// Uses a CALLBACK ref (not useEffect) so it works even when the measured
// element mounts LATER than the component — e.g. a graph canvas that only
// renders after async data loads. The observer attaches the moment the node
// appears and detaches when it's removed.
//
// Width is quantized to the nearest 8px so transient sub-pixel / address-bar
// resizes don't thrash consumers that re-run work on width change (e.g. the
// ForceGraph cooling simulation re-seeds on dimension change).
export function useElementWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [width, setWidth] = useState(0);
  const roRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: T | null) => {
    roRef.current?.disconnect();
    roRef.current = null;
    if (!node || typeof ResizeObserver === "undefined") return;
    const quantize = (w: number) => Math.round(w / 8) * 8;
    const ro = new ResizeObserver(([entry]) => {
      setWidth(prev => {
        const next = quantize(entry.contentRect.width);
        return next === prev ? prev : next;
      });
    });
    ro.observe(node);
    roRef.current = ro;
    setWidth(quantize(node.getBoundingClientRect().width));
  }, []);

  return [ref, width];
}
