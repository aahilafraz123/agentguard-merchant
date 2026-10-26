# AgentGuard web

The web UI for AgentGuard: the Kettle & Crow live demo (`/`) and the merchant console (`/console`).
Vite + React + TypeScript, plain CSS with design tokens, AG Grid Community for tables.

## Develop

Start the API (simulator mode, no keys needed) from the repo root:

```sh
PAYPAL_MODE=mock ANTHROPIC_API_KEY= uv run uvicorn agentguard.api:app --port 8000
curl -X POST localhost:8000/api/demo/activity   # optional: five sample decisions
```

Then the UI, which proxies `/api` to port 8000:

```sh
cd web
npm install
npm run dev        # http://localhost:5173
```

Set `ANTHROPIC_API_KEY` on the API to chat with the support bot and to compile plain-English
policies. Without it the chat and the compiler explain that Claude is off.

## Build

```sh
npm run build      # type-checks, then writes web/dist
```

FastAPI serves `web/dist` at `http://127.0.0.1:8000/` (restart the API after the first build so
it picks up the folder). `npm run typecheck` runs the type check alone.

## Layout

```
src/
  api.ts            typed client for every endpoint in src/agentguard/api.py
  format.ts         money, dates, labels
  hooks.ts          polling and the small history-based router
  components/       nav, badges, KPIs, decision feed and detail, AG Grid wrapper, sheet
  pages/
    LiveDemoPage.tsx    split screen: storefront chat + merchant live view
    demo/               chat, customer picker, demo openers, merchant pane
    ConsolePage.tsx     console tabs (lazy-loaded with AG Grid)
    console/            overview, review queue, decisions, orders, policy, evals
  styles/           tokens (light and dark), base, demo, console
```
