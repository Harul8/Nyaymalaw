# App

Composition, startup and the single HTTP application. The existing `api.py` route surface and `app.js` browser shell remain shared across journeys; this reorganisation does not claim that their internals have been split into separate screens or services.

Key files:

- [composition.py](composition.py) — Selects concrete adapters and supplies the shipped browser-asset population.
- [main.py](main.py) — Builds and wires the ASGI application and command-line startup.
- [api.py](api.py) — Owns the HTTP/session/CSRF and released-byte boundary.
- [static_assets.py](static_assets.py) — Renders only injected, exact browser asset paths; no mixed journey directory is a static root.

## Current file index

This index follows the shipped [source-layout manifest](../source_layout.json). The semantic roles below retain the existing dependency boundary; the journey folder is not a permission or acceptance claim.

### Composition and configuration

- [composition.py](composition.py) — Selects concrete ports, adapters and shipped browser assets.
- [main.py](main.py) — Wires the ASGI application and command-line startup.
- [model_permission.py](model_permission.py) — Owner-approved OpenAI text route, narrowed by each authenticated advocate.

### Contracts and package

- [__init__.py](__init__.py) — Application composition, HTTP routes and the browser shell.

### HTTP and rendering boundary

- [api.py](api.py) — Serves authenticated HTTP routes with session, CSRF and release checks.
- [static_assets.py](static_assets.py) — Serve only the browser assets declared by the shipped source-layout owner.

### Browser assets

- [app.css](app.css) — Advocate-facing design system and responsive shell for the journey screens.
- [app.js](app.js) — Renders journey state and browser interactions without deciding legal facts.
- [index.html](index.html) — Main browser document and journey screen containers.

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
