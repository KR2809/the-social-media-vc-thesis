export * from "./types";
export { syntheticSource } from "./synthetic";
export { loadRealSource } from "./real";

import { syntheticSource } from "./synthetic";
import { loadRealSource } from "./real";
import type { DataSource } from "./types";

// Prefer the real (FastAPI-backed) DataSource. On any fetch failure
// loadRealSource() already falls back to synthetic with a console.warn,
// so callers can treat the returned source as authoritative.
//
// Use this in Server Components / async Client boundaries — see
// frontend/src/app/page.tsx for the migration pattern.
export async function getThesisSource(): Promise<DataSource> {
  return loadRealSource();
}

// Synchronous default — kept for legacy import paths that can't await
// (deep utility helpers, type-only consumers). Equivalent to the C.0
// behaviour. New code should prefer getThesisSource().
export const thesis: DataSource = syntheticSource;
