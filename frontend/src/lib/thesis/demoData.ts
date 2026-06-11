// Data layer for the /demo live read. One small static bundle, lazy-loaded
// (the landing page never pays for it): the study's real scored posts for
// the named founders, used for the labelled SAMPLE read.

export interface FounderPost {
  date: string;
  platform: string;
  text: string;
  strength: number;
  signals: string[]; // plain-named, already translated at export
}

export interface FounderPosts {
  person_id: string;
  founder_name: string;
  venture: string;
  flag_date: string;
  emergence_date: string | null;
  lead_time_months: number | null;
  posts: FounderPost[];
}

let postsCache: Promise<{ founders: FounderPosts[] }> | null = null;
export function loadFounderPosts(): Promise<{ founders: FounderPosts[] }> {
  postsCache ??= fetch("/founder_posts.json").then((r) => {
    if (!r.ok) throw new Error(`founder_posts: ${r.status}`);
    return r.json();
  });
  return postsCache;
}

/** Collected post text sometimes carries HTML entities and stray tags
 *  (HN/Twitter sources); decode/strip them for display. Never alters the
 *  words themselves. */
export function plainText(s: string): string {
  return s
    .replace(/<\/?[a-z][^>]*>/gi, " ")
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#x2f;/gi, "/")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\s{2,}/g, " ")
    .trim();
}
