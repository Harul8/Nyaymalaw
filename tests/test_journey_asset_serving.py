"""The actual HTTP browser boundary, not browser/model/whole-journey proof."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nm.app import api
from nm.app.static_assets import BrowserAssetsRefused, browser_assets_router
from nm.shared.source_layout import LayoutRefused, browser_assets
from starlette.routing import Mount

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def http_boundary(client, monkeypatch):
    def not_an_api_oracle():
        raise AssertionError("Browser files must not access application/private owners")

    # The actual application may supply only its public asset population.
    # Static reads do not consult its health or private API/data projections.
    monkeypatch.setattr(api.application(), "health", not_an_api_oracle)
    yield client


@pytest.mark.parametrize("url", ("/", "/static/index.html", "/static/app.js",
                                 "/static/dictation-worklet.js"))
@pytest.mark.parametrize("validator", ("etag", "weak_etag", "modified_since"))
def test_real_page_and_scripts_revalidate_with_empty_304(http_boundary, url, validator):
    original = http_boundary.get(url)
    assert original.status_code == 200
    if validator == "modified_since":
        headers = {"if-modified-since": original.headers["last-modified"]}
    else:
        tag = original.headers["etag"]
        headers = {"if-none-match": f'"another", W/{tag}' if validator == "weak_etag" else tag}
    response = http_boundary.get(url, headers=headers)
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == original.headers["etag"]
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_etag_mismatch_cannot_be_overridden_by_a_matching_date(http_boundary):
    original = http_boundary.get("/static/app.js")
    response = http_boundary.get("/static/app.js", headers={
        "if-none-match": '"a different shipped version"',
        "if-modified-since": original.headers["last-modified"],
    })
    assert response.status_code == 200
    assert response.content == original.content


@pytest.mark.parametrize("url", ("/", "/static/app.css"))
def test_head_retains_get_headers_without_a_body(http_boundary, url):
    original = http_boundary.get(url)
    response = http_boundary.head(url)
    assert response.status_code == 200 and response.content == b""
    for name in ("content-type", "content-length", "cache-control", "etag", "last-modified"):
        assert response.headers[name] == original.headers[name]


@pytest.mark.parametrize("name", (
    "", "unknown.js", "app.py", "main.py", "api.py", "static_assets.py",
    "app/api.py", "nm/app/api.py", "app/app.js", "backlog.json", "source_layout.json",
    "app/source_layout.json", "shared/source_layout.py", "private.json", ".env",
    ".nm/eval_results.json", "__pycache__/api.pyc", "C:/Users/rahul/.env",
    "../app/api.py", "%2e%2e/app/api.py", "%2e%2e/app.js", "%252e%252e/app/api.py",
    "%2fapp.js", "app.js%2f..%2fapi.py", "app%2ejs", "app.js%00", "app.js%5capi.py",
))
def test_unknown_nested_private_and_escaped_names_never_leave_the_boundary(http_boundary, name):
    response = http_boundary.get(f"/static/{name}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert "Nyaymalaw" not in response.text and "Path(" not in response.text


@pytest.mark.parametrize("method", ("POST", "PUT", "PATCH", "DELETE"))
def test_browser_asset_routes_accept_only_read_methods(http_boundary, method):
    response = http_boundary.request(method, "/static/app.js")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}


def _temporary_browser_root(tmp_path):
    product = tmp_path / "nm" / "app"
    product.mkdir(parents=True)
    (product / "entry.py").write_text("# trusted test-only module\n", encoding="utf-8")
    (product / "index.html").write_text("<p>Public entry page</p>", encoding="utf-8")
    (product / "app.js").write_text("window.publicOnly = 1;", encoding="utf-8")
    layout = {
        "schema": 1,
        "modules": {"nm.app.entry": "edge"},
        "expected_roles": {"edge": 1},
        "browser_assets": {"index.html": "nm/app/index.html", "app.js": "nm/app/app.js"},
    }
    (tmp_path / "nm" / "source_layout.json").write_text(json.dumps(layout), encoding="utf-8")
    return product


def _temporary_client(tmp_path):
    app = FastAPI()
    paths = browser_assets(root=tmp_path)
    app.include_router(browser_assets_router(asset_paths=lambda: paths, root=tmp_path))
    return TestClient(app)


def test_unlisted_files_created_after_admission_still_cannot_be_served(tmp_path):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        (product / "private.json").write_text('{"secret":"PRIVATE"}', encoding="utf-8")
        (product / "backlog.json").write_text('{"secret":"BACKLOG"}', encoding="utf-8")
        (product / "private.py").write_text('SECRET = "PRIVATE"', encoding="utf-8")
        for name in ("private.json", "backlog.json", "private.py", "app/private.json"):
            assert client.get(f"/static/{name}").json() == {"detail": "Not Found"}
        assert client.get("/static/app.js").content == b"window.publicOnly = 1;"


def test_later_manifest_edits_cannot_widen_the_admitted_public_population(tmp_path):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        (product / "private.html").write_text("PRIVATE", encoding="utf-8")
        manifest = tmp_path / "nm" / "source_layout.json"
        layout = json.loads(manifest.read_text(encoding="utf-8"))
        layout["browser_assets"]["private.html"] = "nm/app/private.html"
        manifest.write_text(json.dumps(layout), encoding="utf-8")
        assert client.get("/static/private.html").status_code == 404
        assert client.get("/static/app.js").status_code == 200


def test_withdrawn_or_directory_replacement_of_owned_asset_is_404(tmp_path):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        assert client.get("/static/app.js").status_code == 200
        (product / "app.js").unlink()
        assert client.get("/static/app.js").status_code == 404
        (product / "app.js").mkdir()
        assert client.get("/static/app.js").status_code == 404


def test_changed_owned_bytes_are_fresh_not_a_cached_prior_version(tmp_path):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        previous = client.get("/static/app.js")
        (product / "app.js").write_text(
            "window.publicOnly = 'new shipped bytes';", encoding="utf-8")
        current = client.get("/static/app.js", headers={"if-none-match": previous.headers["etag"]})
        assert current.status_code == 200
        assert current.content == b"window.publicOnly = 'new shipped bytes';"
        assert current.headers["etag"] != previous.headers["etag"]


def test_redirected_declared_path_refuses_even_inside_root(tmp_path, monkeypatch):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        actual_resolve = Path.resolve

        def redirected(path, *args, **kwargs):
            if path == product / "app.js":
                return product / "private.json"
            return actual_resolve(path, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", redirected)
        assert client.get("/static/app.js").status_code == 404


def test_windows_reparse_or_symlink_asset_refuses_after_admission(tmp_path, monkeypatch):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == product or original(path))
        assert client.get("/static/app.js").status_code == 404


def test_windows_reparse_attribute_refuses_after_admission(tmp_path, monkeypatch):
    product = _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        assert client.get("/static/app.js").status_code == 200
        actual_lstat = Path.lstat

        def reparse(path, *args, **kwargs):
            value = actual_lstat(path, *args, **kwargs)
            if path == product / "app.js":
                return SimpleNamespace(
                    st_mode=value.st_mode,
                    st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
                )
            return value

        monkeypatch.setattr(Path, "lstat", reparse)
        assert client.get("/static/app.js").status_code == 404


def test_missing_or_nonbrowser_manifest_declaration_refuses_startup(tmp_path):
    product = _temporary_browser_root(tmp_path)
    (product / "app.js").unlink()
    with pytest.raises(LayoutRefused):
        _temporary_client(tmp_path)


def test_python_cannot_become_public_even_if_declared_as_a_browser_name(tmp_path):
    _temporary_browser_root(tmp_path)
    target = tmp_path / "nm" / "source_layout.json"
    layout = json.loads(target.read_text(encoding="utf-8"))
    layout["browser_assets"]["entry.js"] = "nm/app/entry.py"
    target.write_text(json.dumps(layout), encoding="utf-8")
    with pytest.raises(LayoutRefused):
        _temporary_client(tmp_path)


def test_a_font_may_be_declared_and_no_other_new_kind_of_file(tmp_path):
    """The design's fonts are served by the app (owner decision O24, plan AN.18): a .woff2 joins
    the kinds a browser asset may be, and the list stays closed to every other kind."""
    product = _temporary_browser_root(tmp_path)
    target = tmp_path / "nm" / "source_layout.json"
    layout = json.loads(target.read_text(encoding="utf-8"))
    (product / "face.woff2").write_bytes(b"wOF2 test font")
    layout["browser_assets"]["face.woff2"] = "nm/app/face.woff2"
    target.write_text(json.dumps(layout), encoding="utf-8")
    assert browser_assets(root=tmp_path)["face.woff2"] == product / "face.woff2"
    for name in ("face.woff", "face.ttf", "face.otf", "notes.txt", "data.json"):
        (product / name).write_bytes(b"not a browser asset")
        refused = dict(layout, browser_assets=dict(layout["browser_assets"], **{name: f"nm/app/{name}"}))
        target.write_text(json.dumps(refused), encoding="utf-8")
        with pytest.raises(LayoutRefused):
            browser_assets(root=tmp_path)


def test_a_declared_font_is_served_as_a_font_with_its_exact_bytes(tmp_path):
    """The server reads the layout owner's media types (plan AN.18): a font goes out as
    font/woff2, byte for byte, with the same revalidation and no-sniffing as every asset."""
    product = _temporary_browser_root(tmp_path)
    target = tmp_path / "nm" / "source_layout.json"
    layout = json.loads(target.read_text(encoding="utf-8"))
    font = b"wOF2\x00\x01\x00\x00 binary test font \xff\xfe"
    (product / "face.woff2").write_bytes(font)
    layout["browser_assets"]["face.woff2"] = "nm/app/face.woff2"
    target.write_text(json.dumps(layout), encoding="utf-8")
    with _temporary_client(tmp_path) as client:
        response = client.get("/static/face.woff2")
        assert response.status_code == 200 and response.content == font
        assert response.headers["content-type"] == "font/woff2"
        assert response.headers["cache-control"] == "no-cache, must-revalidate"
        assert response.headers["x-content-type-options"] == "nosniff"
        again = client.get("/static/face.woff2", headers={"if-none-match": response.headers["etag"]})
        assert again.status_code == 304 and again.content == b""


def test_declared_alias_cannot_masquerade_as_another_media_or_file_name(tmp_path):
    _temporary_browser_root(tmp_path)
    target = tmp_path / "nm" / "source_layout.json"
    layout = json.loads(target.read_text(encoding="utf-8"))
    layout["browser_assets"]["another.js"] = "nm/app/index.html"
    target.write_text(json.dumps(layout), encoding="utf-8")
    with _temporary_client(tmp_path) as client:
        with pytest.raises(BrowserAssetsRefused):
            client.get("/static/another.js")


ASSETS = {
    "app.css": ("nm/app/app.css", "text/css"),
    "app.js": ("nm/app/app.js", "text/javascript"),
    "index.html": ("nm/app/index.html", "text/html"),
    "person.js": ("nm/app/person.js", "text/javascript"),
    "brain-sources.js": ("nm/app/brain-sources.js", "text/javascript"),
    "draft-vault.js": ("nm/arrive/draft-vault.js", "text/javascript"),
    "dictation-worklet.js": ("nm/open_matter/dictation-worklet.js", "text/javascript"),
    "intake-materials.css": ("nm/open_matter/intake-materials.css", "text/css"),
    "intake-materials.js": ("nm/open_matter/intake-materials.js", "text/javascript"),
    # The public site at nyaymalaw.in (owner decisions P52, O19, O23; plan AN.16).
    "site.css": ("nm/site/site.css", "text/css"),
    "site.js": ("nm/site/site.js", "text/javascript"),
    "home.html": ("nm/site/home.html", "text/html"),
    "how-it-works.html": ("nm/site/how-it-works.html", "text/html"),
    "what-it-holds.html": ("nm/site/what-it-holds.html", "text/html"),
    "trust.html": ("nm/site/trust.html", "text/html"),
    "plans.html": ("nm/site/plans.html", "text/html"),
    "about.html": ("nm/site/about.html", "text/html"),
    "legal.html": ("nm/site/legal.html", "text/html"),
    # The design's fonts, served by the app itself (owner decision O24; plan AN.18).
    "fonts.css": ("nm/app/fonts/fonts.css", "text/css"),
    **{f"{face}-{subset}-wght-{style}.woff2": (f"nm/app/fonts/{face}-{subset}-wght-{style}.woff2", "font/woff2")
       for face in ("source-serif-4", "source-sans-3") for subset in ("latin", "latin-ext")
       for style in ("normal", "italic")},
}


def test_every_declared_browser_asset_is_the_exact_shipped_population():
    assert browser_assets(root=ROOT) == {
        name: ROOT / path for name, (path, _media_type) in ASSETS.items()
    }
    assert len(ASSETS) == 27
    # The old tree is migration evidence, not a runtime import or public root.
    assert not any(isinstance(route, Mount) and route.path == "/static"
                   for route in api.app.routes)


@pytest.mark.parametrize("name", tuple(ASSETS))
def test_every_real_asset_get_retains_exact_bytes_media_and_cache_headers(http_boundary, name):
    path, media_type = ASSETS[name]
    response = http_boundary.get(f"/static/{name}")
    assert response.status_code == 200
    assert response.content == (ROOT / path).read_bytes()
    # Text is declared UTF-8; a font is binary and carries no character set.
    assert response.headers["content-type"] == (
        f"{media_type}; charset=utf-8" if media_type.startswith("text/") else media_type)
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"] and response.headers["last-modified"]

#: Each address the app serves a page at, and the page it is (owner decisions P52, O19, O23; plan AN.16).
ADDRESSES = {
    "/": "nm/site/home.html",
    "/app": "nm/app/index.html",
    "/how-it-works": "nm/site/how-it-works.html",
    "/what-it-holds": "nm/site/what-it-holds.html",
    "/trust": "nm/site/trust.html",
    "/plans": "nm/site/plans.html",
    "/about": "nm/site/about.html",
    "/legal": "nm/site/legal.html",
}


@pytest.mark.parametrize("address", tuple(ADDRESSES))
def test_each_address_serves_its_own_declared_page(http_boundary, address):
    response = http_boundary.get(address)
    assert response.status_code == 200
    assert response.content == (ROOT / ADDRESSES[address]).read_bytes()
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-cache, must-revalidate"


def test_the_homepage_is_not_the_app_and_other_addresses_are_unknown(http_boundary):
    assert http_boundary.get("/").content != (ROOT / "nm/app/index.html").read_bytes()
    for address in ("/nope", "/index.html", "/home.html", "/pricing", "/app.html"):
        assert http_boundary.get(address).status_code == 404, address


def test_an_address_whose_page_is_not_declared_is_a_plain_404(tmp_path):
    _temporary_browser_root(tmp_path)
    with _temporary_client(tmp_path) as client:
        assert client.get("/app").content == b"<p>Public entry page</p>"
        for address in ("/", "/trust", "/plans"):
            response = client.get(address)
            assert response.status_code == 404 and response.json() == {"detail": "Not Found"}
