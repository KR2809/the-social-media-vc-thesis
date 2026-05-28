This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Configuration

### `NEXT_PUBLIC_API_BASE_URL`

The frontend's data layer (`src/lib/thesis/real.ts`) fetches the live cohort
and timeline bounds from the FastAPI backend in `api/`. The base URL is
read from `NEXT_PUBLIC_API_BASE_URL` at build time.

- **Development** (default): `http://localhost:8000`. Start the API with
  `DATA_SOURCE=local uvicorn api.main:app --port 8000` from the repo
  root, then `npm run dev` here.
- **Production**: set `NEXT_PUBLIC_API_BASE_URL` as a Vercel project env
  var pointing at the deployed FastAPI URL (e.g. Fly.io / Railway / etc.).

If the API is unreachable, `loadRealSource()` logs a `console.warn` and
falls back to the synthetic source so the demo still renders.

## Tests

```bash
npm run test:smoke    # smoke-test the real-data adapter against mocked fetch
```

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel (Phase D.3)

The demo (this `frontend/` app) deploys to Vercel; the FastAPI backend in
`../api/` deploys separately (Fly.io / Railway / Render) and the frontend
points at it via `NEXT_PUBLIC_API_BASE_URL`.

### One-time Vercel setup

1. **Import the repo** at [vercel.com/new](https://vercel.com/new).
2. **Root Directory** → set to `frontend` (the Next app is not at repo root).
   Vercel auto-detects Next.js + `vercel.json` from there.
3. **Environment variables** (Project → Settings → Environment Variables):
   - `NEXT_PUBLIC_API_BASE_URL` → the deployed FastAPI URL (e.g.
     `https://thesis-api.fly.dev`). If unset, the data layer falls back to
     the synthetic source and shows the "synthetic" banner.
   - `NEXT_PUBLIC_SITE_URL` → the Vercel production URL (e.g.
     `https://thesis-demo.vercel.app`). Used as `metadataBase` so the
     generated OG image (`/opengraph-image`) resolves to an absolute URL.
4. **Deploy.** Pushes to `main` auto-deploy (see `vercel.json`).

### Backend (FastAPI) deploy

Deploy `../api/` with `DATA_SOURCE=supabase` (prod) and set
`FRONTEND_ORIGINS` to the Vercel URL to tighten CORS.

### EDHEC compliance

Public, read-only demo of a working artefact — no personal data beyond the
publicly-named cohort, no student PII. The locked prediction JSON + SHA-256
+ git tag remain the canonical record; the deploy is a convenience surface,
not the submission.

### Social / OG image

`src/app/opengraph-image.tsx` generates a 1200×630 branded card at build
time (also used for the Twitter `summary_large_image`). Preview locally at
`http://localhost:3001/opengraph-image`.

### Thesis-appendix screenshots (Phase D.4)

A print stylesheet (`@media print` in `src/app/demo.css`) forces light
surfaces, hides interactive chrome (gear / help / tooltips), and prevents
cards from splitting across page breaks — so "Print → Save as PDF" yields
clean appendix figures.
