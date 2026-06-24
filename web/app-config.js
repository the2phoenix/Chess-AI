// Public runtime config for the frontend (no secrets here).
//
// DARWIN_API_BASE — where the Python engine API lives.
//   Local dev: leave empty ("") — server.py serves the page and /api together.
//   Production: set to your Render backend URL, e.g.
//   "https://darwins-gambit-api.onrender.com" so the Vercel-hosted page calls it.
window.DARWIN_API_BASE = "";
