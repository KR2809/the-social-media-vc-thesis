// Frontend → FastAPI base URL. Override per environment with the
// NEXT_PUBLIC_API_BASE_URL build-time env var (see frontend/README.md).
//
// Dev default: http://localhost:8000 (matches `DATA_SOURCE=local uvicorn
// api.main:app --port 8000`). In prod, point at the deployed FastAPI URL.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
