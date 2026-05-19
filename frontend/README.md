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

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
