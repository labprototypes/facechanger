# facechanger

## Frontend env

Set NEXT_PUBLIC_API_URL to your deployed backend base URL (e.g. https://api-backend-XXXX.onrender.com). Without it, the web app will call its own host (producing 404 like /api/heads, /api/skus/*). Relative fallback only works if a reverse proxy forwards /api and /internal to the backend.
