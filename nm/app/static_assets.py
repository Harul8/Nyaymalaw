"""Serve only the browser assets declared by the shipped source-layout owner.

Journey folders also contain Python and private source data. No directory in
that tree is a public static root, and request text never becomes a file path.
"""

from __future__ import annotations

import stat
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles

_MEDIA_TYPES = {
    ".css": "text/css",
    ".html": "text/html",
    ".js": "text/javascript",
    ".svg": "image/svg+xml",
}
_HEADERS = {
    "cache-control": "no-cache, must-revalidate",
    "x-content-type-options": "nosniff",
}
# Reuse the framework's conditional-header semantics, not its path lookup or
# serving entry point. This validator has no directory or package population.
_REVALIDATION = StaticFiles()


class BrowserAssetsRefused(ValueError):
    """Trusted composition supplied no usable closed browser population."""


def browser_assets_router(*, asset_paths: Callable[[], Mapping[str, Path]],
                          root: Path) -> APIRouter:
    """Snapshot the trusted manifest's exact URLs, retaining current file bytes.

    The root is supplied by application composition, never an HTTP argument.
    Missing/escaped declarations refuse startup; a subsequently withdrawn or
    redirected asset returns the same 404 as an unknown public name.
    """
    owned_root = root.resolve(strict=True)
    admitted_owner = None
    assets = MappingProxyType({})
    canonical = {}

    def admitted_assets():
        nonlocal admitted_owner, assets, canonical
        declared = asset_paths()
        if declared is not admitted_owner:
            if not isinstance(declared, Mapping) or "index.html" not in declared:
                raise BrowserAssetsRefused("The browser population has no entry page")
            paths, resolved_paths = {}, {}
            for name, path in declared.items():
                if (not isinstance(name, str) or not isinstance(path, Path)
                        or name != path.name or path.suffix not in _MEDIA_TYPES
                        or "/" in name or "\\" in name):
                    raise BrowserAssetsRefused("A browser URL must name its exact browser file")
                # The admitted identity is the declared physical path, not a
                # potentially redirected destination discovered on first GET.
                expected = path.absolute()
                if owned_root not in expected.parents:
                    raise BrowserAssetsRefused("A browser file escapes its owning application")
                paths[name], resolved_paths[name] = path, expected
            assets, canonical = MappingProxyType(paths), resolved_paths
            admitted_owner = declared
        return assets

    def response_for(request: Request, name: str) -> Response:
        # Refuse noncanonical escapes before looking up even an existing file.
        # ASGI raw_path is already separate from the query string.
        raw_path = request.scope.get("raw_path", b"")
        if any(value in raw_path for value in (b"%", b"\\", b"\x00")):
            raise HTTPException(status_code=404)
        path = admitted_assets().get(name)
        if path is None:
            raise HTTPException(status_code=404)
        try:
            resolved = path.resolve(strict=True)
            if resolved != canonical[name] or owned_root not in resolved.parents:
                raise HTTPException(status_code=404)
            # A parent symlink/reparse-point must not redirect a declared file
            # into another part of the mixed product tree, even within root.
            for component in (path, *path.parents):
                if component == root:
                    break
                attributes = getattr(component.lstat(), "st_file_attributes", 0)
                reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                if component.is_symlink() or attributes & reparse:
                    raise HTTPException(status_code=404)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise HTTPException(status_code=404)
        except (OSError, ValueError):
            raise HTTPException(status_code=404) from None
        response = FileResponse(
            path,
            stat_result=info,
            media_type=_MEDIA_TYPES[path.suffix],
            headers=_HEADERS,
        )
        if _REVALIDATION.is_not_modified(response.headers, request.headers):
            response = NotModifiedResponse(response.headers)
            response.headers["x-content-type-options"] = "nosniff"
        return response

    router = APIRouter()

    @router.api_route("/static/{asset_name:path}", methods=["GET", "HEAD"],
                      include_in_schema=False)
    def asset(request: Request, asset_name: str) -> Response:
        return response_for(request, asset_name)

    @router.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def index(request: Request) -> Response:
        return response_for(request, "index.html")

    return router
