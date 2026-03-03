// In production (Vercel), API is same-origin (/api/*) so API_BASE = ''.
// In local dev, fallback to localhost:8000 where the FastAPI server runs.
const isLocalDev = typeof window !== 'undefined' && window.location.hostname === 'localhost';
export const API_BASE = (import.meta.env.VITE_API_BASE as string) || (isLocalDev ? 'http://localhost:8000' : '');
