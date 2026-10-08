# Gitgood web
React/TypeScript with TanStack Start and Query, following Barkpark Studio's separation between interface and authoritative APIs.

Run `npm ci`, then `npm run dev` at http://localhost:47840. The forge must run on 127.0.0.1:47841.
`GITGOOD_API_URL` configures the fixed server-only upstream. Browser requests cannot select another upstream.
Run `npm run check` for the production build and strict TypeScript check.
The browser keeps draft inputs and a creation idempotency key through retry; the backend owns actors, membership and storage.
