"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";

interface Props {
  label?: ReactNode;
  children: ReactNode;
  width?: number;
}

// Tooltip that positions itself in the VIEWPORT via fixed coords computed on
// open — so it never gets clipped by a card's edge or overflow (the old
// pure-CSS absolute popup was cut off when the trigger sat near the right
// edge, e.g. the Knowledge-Graph card "?"). It measures the trigger rect,
// prefers below-centered, then flips above / clamps horizontally to stay on
// screen with a margin.
const MARGIN = 12;

export function InfoTip({ label, children, width = 280 }: Props) {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number; arrow: number } | null>(null);

  const open = useCallback(() => {
    const el = triggerRef.current;
    if (typeof window === "undefined" || !el) return;
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.min(width, vw - MARGIN * 2);

    // Horizontal: centre on the trigger, then clamp to the viewport.
    const triggerCx = r.left + r.width / 2;
    let left = triggerCx - w / 2;
    left = Math.max(MARGIN, Math.min(left, vw - w - MARGIN));
    // Arrow points at the trigger centre, relative to the popup's left.
    const arrow = Math.max(12, Math.min(w - 12, triggerCx - left));

    // Vertical: prefer below; flip above if it would overflow the bottom.
    const below = r.bottom + 8;
    const estH = 160; // generous estimate; popup is height:auto
    const top = below + estH > vh - MARGIN ? Math.max(MARGIN, r.top - 8 - estH) : below;

    setPos({ left, top, arrow });
  }, [width]);

  const close = useCallback(() => setPos(null), []);

  return (
    <span
      ref={triggerRef}
      className="info-tip"
      tabIndex={0}
      onMouseEnter={open}
      onMouseLeave={close}
      onFocus={open}
      onBlur={close}
    >
      {label ? <span className="info-tip-trigger">{label}</span> : null}
      <span className="info-tip-icon" aria-hidden="true">?</span>
      {pos && (
        <span
          className="info-tip-popup open"
          style={
            {
              width: Math.min(width, typeof window !== "undefined" ? window.innerWidth - MARGIN * 2 : width),
              left: pos.left,
              top: pos.top,
              "--arrow-x": `${pos.arrow}px`,
            } as React.CSSProperties
          }
        >
          {children}
        </span>
      )}
    </span>
  );
}
