"""Serve only the browser assets declared by the shipped source-layout owner.

Journey folders also contain Python and private source data. No directory in
that tree is a public static root, and request text never becomes a file path.
"""

from __future__ import annotations

import gzip
import hashlib
import stat
from email.utils import formatdate
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import FileResponse, RedirectResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles

from nm.shared.source_layout import MEDIA_TYPES

_HEADERS = {
    "cache-control": "no-cache, must-revalidate",
    "x-content-type-options": "nosniff",
}
#: The addresses pages are served at (owner decisions P52, O19 and O23, 25 Oct 2026; plan AN.16):
#: nyaymalaw.in opens the public homepage, each public page has its own address, and the app is at
#: /app. Each names one declared page; an address whose page is not declared is the same 404 as any
#: unknown name. No page here reads a session or a matter.
PAGES = MappingProxyType({
    "/": "home.html",
    "/app": "index.html",
    "/admin": "admin.html",  # gated: served only to an account the settings name as an admin (D117)
    "/how-it-works": "how-it-works.html",
    "/what-it-holds": "what-it-holds.html",
    "/trust": "trust.html",
    "/plans": "plans.html",
    "/about": "about.html",
    "/legal": "legal.html",
})
#: Where a signed-out visitor to a gated page is sent: the one sign-in, which opens the page they came for once they are in.
SIGN_IN_ADDRESS = "/app#admin"
# Reuse the framework's conditional-header semantics, not its path lookup or
# serving entry point. This validator has no directory or package population.
_REVALIDATION = StaticFiles()
#: THE PAGE'S OWN FILES ARE SENT COMPRESSED (plan AN.58, piece 58a; D268; the second review of 17 Nov 2026): the page, its
#: script and its styles are text, and the script alone is over half a megabyte - slow on a phone in a court corridor. Only
#: these files, here at their one owner: no answer of the API is compressed (an answer carries an advocate's matter, and the
#: progress stream must not be held back), and a font or an image is compressed already. A browser that does not ask for
#: gzip is sent the file as it is.
_COMPRESSED = frozenset({".html", ".js", ".css", ".svg"})
#: A file smaller than this gains nothing worth a second copy in memory.
_SMALLEST_COMPRESSED = 1024


class BrowserAssetsRefused(ValueError):
    """Trusted composition supplied no usable closed browser population."""


def browser_assets_router(*, asset_paths: Callable[[], Mapping[str, Path]],
                          root: Path,
                          gated: Mapping[str, Callable[[Request], bool | str]] | None = None,
                          filled: Mapping[str, Callable[[str], tuple[str, float | None]]] | None = None) -> APIRouter:
    """Snapshot the trusted manifest's exact URLs, retaining current file bytes.

    The root is supplied by application composition, never an HTTP argument.
    Missing/escaped declarations refuse startup; a subsequently withdrawn or
    redirected asset returns the same 404 as an unknown public name.

    A GATED NAME (plan AN.46, piece 46p; D117) is served only to a request its gate admits - the Admin area's page and files, which the
    server must not tell anyone they are for: to every other request the name is the same 404 as an unknown one. The gate is supplied
    by composition (the edge's sign-in and the settings' admin list), never read from the request; the file is still one the closed
    manifest declares, so there is one way to serve a file and not two.

    A gate answers True (serve it), False (the 404), or "sign-in": nobody is signed in, so a PAGE is answered with a redirect to the
    workspace's own sign-in (there is one login, the same for every account - an admin is whoever the settings name once signed in),
    and any other file with the 404. The redirect tells nobody anything: the sign-in page is public.

    A FILLED PAGE (plan AN.56, piece 56a; D258) is a declared page whose marked places are filled when it is served, by the function
    composition gives for it (the public pages' figures of what NM holds, read from the library's own records): the page's text is
    passed through it at each request and the result is sent, compressed where the browser asks, with a validator of its own bytes
    and, as its date, the later of the file's and of what filled it (the function gives that time, or None for nothing read), so
    that a browser revalidating by date alone is never kept on figures since changed. It is still the one declared file.
    """
    gates = MappingProxyType(dict(gated or {}))
    fills = MappingProxyType(dict(filled or {}))
    if any(not name.endswith(".html") for name in fills):
        raise BrowserAssetsRefused("Only a page is filled when it is served")
    owned_root = root.resolve(strict=True)
    packed: dict[str, tuple[tuple[int, int], bytes]] = {}

    def compressed(name: str, path: Path, info) -> bytes:
        """The file's bytes, gzipped, made once for each state of the file (its size and the time it was last written): a
        changed file is compressed again, never served from the copy of what it was."""
        state = (info.st_size, info.st_mtime_ns)
        held = packed.get(name)
        if held is None or held[0] != state:
            held = packed[name] = (state, gzip.compress(path.read_bytes(), compresslevel=6, mtime=0))
        return held[1]
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
                        or name != path.name or path.suffix not in MEDIA_TYPES
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
        gate = gates.get(name)
        if gate is not None:
            verdict = gate(request)
            if verdict == "sign-in" and path.suffix == ".html":
                return RedirectResponse(SIGN_IN_ADDRESS, status_code=302, headers={"cache-control": "no-store"})
            if verdict is not True:
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
        filler = fills.get(name)
        if filler is not None:
            try:
                # The bytes as written (a page read as text would lose its line endings), and only they.
                written = path.read_bytes().decode("utf-8")
            except (OSError, ValueError):
                raise HTTPException(status_code=404) from None
            text, read_at = filler(written)
            return _sent(request, text.encode("utf-8"), MEDIA_TYPES[path.suffix], max(info.st_mtime, read_at or 0))
        response = FileResponse(
            path,
            stat_result=info,
            media_type=MEDIA_TYPES[path.suffix],
            headers=_HEADERS,
        )
        # A file sent in two forms tells every cache between that the form depends on what the browser accepts.
        packable = path.suffix in _COMPRESSED and info.st_size >= _SMALLEST_COMPRESSED
        if packable:
            response.headers["vary"] = "Accept-Encoding"
        accepted = {part.split(";")[0].strip().lower() for part in request.headers.get("accept-encoding", "").split(",")}
        if packable and "gzip" in accepted:
            try:
                body = compressed(name, path, info)
            except OSError:
                raise HTTPException(status_code=404) from None
            # The compressed form is another representation: it has its own validator, so a cache never answers a browser
            # that wants one form with the other.
            headers = {**_HEADERS, "vary": "Accept-Encoding", "content-encoding": "gzip",
                       "etag": response.headers["etag"].rstrip('"') + '-gzip"',
                       "last-modified": response.headers["last-modified"]}
            response = Response(content=b"" if request.method == "HEAD" else body, media_type=MEDIA_TYPES[path.suffix],
                                headers=headers)
            response.headers["content-length"] = str(len(body))
        if _REVALIDATION.is_not_modified(response.headers, request.headers):
            response = NotModifiedResponse(response.headers)
            response.headers["x-content-type-options"] = "nosniff"
        return response

    def _sent(request: Request, body: bytes, media_type: str, modified: float) -> Response:
        """A filled page's bytes, as a file is sent: its own validator and date, compressed where the browser asks and it is large
        enough."""
        tag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        accepted = {part.split(";")[0].strip().lower() for part in request.headers.get("accept-encoding", "").split(",")}
        headers = {**_HEADERS, "vary": "Accept-Encoding", "etag": tag, "last-modified": formatdate(modified, usegmt=True)}
        if "gzip" in accepted and len(body) >= _SMALLEST_COMPRESSED:
            body = gzip.compress(body, compresslevel=6, mtime=0)
            headers.update({"content-encoding": "gzip", "etag": tag.rstrip('"') + '-gzip"'})
        response = Response(content=b"" if request.method == "HEAD" else body, media_type=media_type, headers=headers)
        response.headers["content-length"] = str(len(body))
        if _REVALIDATION.is_not_modified(response.headers, request.headers):
            response = NotModifiedResponse(response.headers)
            response.headers["x-content-type-options"] = "nosniff"
        return response

    router = APIRouter()

    @router.api_route("/static/{asset_name:path}", methods=["GET", "HEAD"],
                      include_in_schema=False)
    def asset(request: Request, asset_name: str) -> Response:
        return response_for(request, asset_name)

    def page(name: str) -> Callable[[Request], Response]:
        def serve(request: Request) -> Response:
            return response_for(request, name)
        return serve

    for address, name in PAGES.items():
        router.add_api_route(address, page(name), methods=["GET", "HEAD"], include_in_schema=False)

    return router
