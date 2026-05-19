"use client";

// Single-source-of-truth for the active DataSource at runtime.
// App.tsx resolves the source (real → hybrid, fallback → synthetic) and
// wraps the tree. Components call useThesis() instead of importing the
// module-level `thesis` constant, so the hybrid roster reaches every view.

import { createContext, useContext, type ReactNode } from "react";
import type { DataSource } from "./types";
import { syntheticSource } from "./synthetic";

const ThesisContext = createContext<DataSource>(syntheticSource);

export function ThesisProvider({
  value,
  children,
}: {
  value: DataSource;
  children: ReactNode;
}) {
  return (
    <ThesisContext.Provider value={value}>{children}</ThesisContext.Provider>
  );
}

export function useThesis(): DataSource {
  return useContext(ThesisContext);
}
