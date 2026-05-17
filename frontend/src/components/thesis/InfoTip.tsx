"use client";

import type { ReactNode } from "react";

interface Props {
  label?: ReactNode;
  children: ReactNode;
  width?: number;
}

export function InfoTip({ label, children, width = 280 }: Props) {
  return (
    <span className="info-tip" tabIndex={0}>
      {label ? <span className="info-tip-trigger">{label}</span> : null}
      <span className="info-tip-icon" aria-hidden="true">?</span>
      <span className="info-tip-popup" style={{ width }}>
        {children}
      </span>
    </span>
  );
}
