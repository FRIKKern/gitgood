# Gitgood web

The React/TypeScript interface uses TanStack Start, Router and Query. It follows Barkpark Studio's separation between the interface and authoritative APIs: the forge owns actors, permissions, Git rules and durable outcomes.

**Start with [Run Gitgood locally](../../docs/DEVELOPMENT.md)** to prepare the database, API and disposable accounts. This guide describes the web application's responsibilities and commands.

## See the interface

The [web tour](../../docs/WEB-TOUR.md) shows the current screens in screenshots, an animated walkthrough and a navigation map. Captures use the real interface with synthetic API data. Run `npm run tour` from this directory to refresh them; the guide explains how to review and retain the generated media.

## Start the interface

With the forge already running, open a terminal in `apps/web`:

```bash
export GITGOOD_API_URL=http://127.0.0.1:47841
npm ci
npm run dev
```

Open **http://localhost:47840**. The development command binds `127.0.0.1` and uses a strict port, so an occupied port causes an error instead of silently changing the browser origin. Keep the URL consistent with the forge's `GITGOOD_WEB_ORIGIN`. See the [local guide](../../docs/DEVELOPMENT.md#2-start-the-web-interface) for changing the port pair.

`GITGOOD_API_URL` configures the server-only upstream. The browser calls `/api/` on the web origin, and [the proxy](src/server/forge.ts) forwards allowed requests to the forge. Browser requests cannot select another upstream or receive the server's service credentials.

## Where things live

| Location | Responsibility |
|---|---|
| [src/routes](src/routes/) | Home, repository, pull request, operation and change pages |
| [src/lib/api.ts](src/lib/api.ts) | Typed API requests and errors |
| [src/lib/access-boundary.tsx](src/lib/access-boundary.tsx) | Shared session/access state and invalidation |
| [src/lib](src/lib/) | Feature components for reviews, imports, releases, Barkpark and team access |
| [src/server/forge.ts](src/server/forge.ts) | Fixed upstream proxy, bounded bodies, timeouts and private response handling |
| [src/styles.css](src/styles.css) | Interface styles |
| [e2e](e2e/) | Actual browser workflows and their fixtures |
| [verification](verification/) | Proxy, client address, edge-port and recovery-readiness checks |

The [repository code map](../../docs/CODEBASE.md) connects these surfaces to backend modules. `src/routeTree.gen.ts` is generated from the route files.

## State and access rules

The browser keeps draft inputs and stable request identities through retries. It shows unavailable or uncertain outcomes explicitly and reconciles against backend receipts. Membership checks, protected merges, evidence custody and recovery decisions remain in the forge. Hiding a button is never access enforcement.

Vite's [configuration](vite.config.ts) rejects importing `src/server` modules into client code. Keep credentials and private source adapters on the server, and use the existing shared access boundary when adding authenticated views.

## Check and build

Run `npm run check` from this directory. It builds the production app, runs strict TypeScript checks, and executes the proxy/runtime verification tests listed in [package.json](package.json).

Browser checks use Playwright and need the corresponding forge fixtures, Git tools and browser runtime. [playwright.config.ts](playwright.config.ts) uses one worker and can start the local web server; `GITGOOD_TEST_WEB_URL` selects an already running test target. Follow the relevant [implementation guide](../../docs/implementation/README.md) and [CI sequence](../../.github/workflows/product.yml) for the complete environment instead of treating a web build as workflow verification.

`npm run build` produces the web artifacts. `npm start` serves the packaged production entry; it is part of the [production packaging procedure](../../docs/deployment/production.md), which includes static assets, locked production dependencies, and matching forge/web build identities. A successful build does not establish a managed deployment or product release.
