// Domain types for the thesis demo. Matches the shapes the prototype's
// data.js produces, but typed so a real-data adapter can be swapped in.

export type FounderId = string;

export type TaxonomyCode = "S1" | "S2" | "S3" | "S4" | "S5" | "S6";

export interface TaxonomyEntry {
  label: string;
  color: string;
}

export type Taxonomy = Record<TaxonomyCode, TaxonomyEntry>;

export interface Founder {
  id: FounderId;
  name: string;
  niche: string;
  first: string;
  emerge: string | null;
  venture: string | null;
  ventureMetric: string | null;
  emphasis: TaxonomyCode[];
}

export type Outcome = "emerged" | "not_yet" | "unknown";

export interface RankedPick {
  id: FounderId;
  name: string;
  niche: string;
  t1: number | null;
  t2: number | null;
  combined: number;
  emerge: string | null;
  first: string;
  outcome: Outcome;
}

export interface PrecisionResult {
  hits: number;
  k: number;
  precision: number;
}

export interface BaselinePick {
  id: FounderId;
  name: string;
  score?: number;
}

export interface SignalEvidence {
  id: number;
  dim: string;
  cat: TaxonomyCode;
  score: number;
  raw: string;
  platform: string;
  timestamp: string;
}

export type KGNodeKind = "founder" | "signal" | "topic" | "platform";

export interface KGNode {
  id: string;
  kind: KGNodeKind;
  label: string;
  weight?: number;
}

export interface KGEdge {
  a: string;
  b: string;
  w: number;
}

export interface EgoNetwork {
  nodes: KGNode[];
  edges: KGEdge[];
}

export interface Palette {
  c1: string;
  c2: string;
}

// The DataSource is the seam between "synthetic" and "real" backends.
// Components import this interface — never concrete loaders directly.
export interface DataSource {
  readonly source: "synthetic" | "real" | "hybrid";
  readonly today: number; // months since 2014-01

  taxonomy(): Taxonomy;
  founders(): readonly Founder[];

  months(s: string | null): number | null;
  fmtMonth(mo: number): string;
  fmtQuarter(mo: number): string;

  curve(founder: Founder, t: number): number | null;
  tier1(founder: Founder, t: number): number | null;
  tier2(founder: Founder, t: number): number | null;

  rankAt(t: number, K: number): RankedPick[];
  outcomeAt(founder: Founder, t: number): Outcome;

  baselineRandom(t: number, K: number, seed: number): BaselinePick[];
  baselineVolume(t: number, K: number): BaselinePick[];
  baselineRecency(t: number, K: number): BaselinePick[];

  precisionAt(picks: ReadonlyArray<BaselinePick | RankedPick>, t: number): PrecisionResult;
  bootCI(hits: number, k: number): [number, number];

  signalsFor(founderId: FounderId, t: number): SignalEvidence[];
  egoFor(founderId: FounderId): EgoNetwork;

  paletteFor(id: FounderId): Palette;
}
