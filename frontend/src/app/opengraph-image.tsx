import { ImageResponse } from "next/og";

// Branded OG/social card, generated at build/request time. Matches the
// thesis demo's dark palette + serif headline. Reused for Twitter via
// the twitter card metadata in layout.tsx.
export const alt =
  "From Social Signals to Pre-Seed Allocation — a systematic framework for pre-seed venture capital";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "linear-gradient(150deg, #0B0F1C 0%, #141A2B 100%)",
          padding: "72px 80px",
          color: "#ECEEF5",
          fontFamily: "serif",
        }}
      >
        {/* Mark + eyebrow */}
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              background: "#1F4E79",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div style={{ width: 14, height: 14, borderRadius: 999, background: "#fff" }} />
          </div>
          <div
            style={{
              fontSize: 22,
              letterSpacing: 4,
              color: "#7E8699",
              textTransform: "uppercase",
              fontFamily: "sans-serif",
            }}
          >
            EDHEC BSc Global Business · Thesis Demo
          </div>
        </div>

        {/* Headline */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 64, lineHeight: 1.1, fontWeight: 600, maxWidth: 980 }}>
            From Social Signals to Pre-Seed Allocation
          </div>
          <div
            style={{
              fontSize: 30,
              color: "#B5BCCC",
              maxWidth: 920,
              fontFamily: "sans-serif",
              lineHeight: 1.35,
            }}
          >
            A systematic framework for pre-seed venture capital — replay any date, score the picks,
            drill into the evidence.
          </div>
        </div>

        {/* Footer byline */}
        <div
          style={{
            fontSize: 24,
            color: "#6FA8DC",
            fontFamily: "sans-serif",
            display: "flex",
          }}
        >
          Kristian Ratkov · supervised by George Tovstiga
        </div>
      </div>
    ),
    { ...size },
  );
}
