# Aster web

Next.js frontend imported from the user's `aster-hero` prototype. The landing page
retains its illustrative preview; `/dashboard` connects to the Python campaign API.
The original separate landing-page repository remains unchanged.

From the repository root, follow [the dashboard guide](../../docs/DASHBOARD.md).
The scientific backend lives in `../../aster/`. Do not run it in the browser or
inside a Vercel request. The frontend's server route proxies to `ASTER_API_URL`
(default `http://127.0.0.1:8000`). This integration is a local research prototype.

```sh
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Use `npm run build` for the production/TypeScript check. The integrated app uses
system fonts so builds do not require downloading Google Fonts.
