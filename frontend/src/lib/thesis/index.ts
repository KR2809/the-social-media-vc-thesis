export * from "./types";
export { syntheticSource } from "./synthetic";
export { loadRealSource } from "./real";

import { syntheticSource } from "./synthetic";
import type { DataSource } from "./types";

// Default source for components. Swap to loadRealSource() once Phase 3
// scoring outputs are wired up.
export const thesis: DataSource = syntheticSource;
