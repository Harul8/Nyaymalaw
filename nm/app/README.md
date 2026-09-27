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

- [composition.py](composition.py)
- [main.py](main.py)
- [model_permission.py](model_permission.py)

### Contracts and package

- [__init__.py](__init__.py)

### HTTP and rendering boundary

- [api.py](api.py)
- [static_assets.py](static_assets.py)

### Browser assets

- [app.css](app.css)
- [app.js](app.js)
- [index.html](index.html)

Only the exact declared `/static/<name>` URLs are public; Python and private files in the same folders are never a static population.
