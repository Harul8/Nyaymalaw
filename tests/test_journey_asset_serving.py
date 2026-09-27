"""The actual HTTP browser boundary, not browser/model/whole-journey proof."""

from __future__ import annotations

import json
import re
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Mount

from nm.app import api
from nm.app.static_assets import BrowserAssetsRefused, browser_assets_router
from nm.shared.source_layout import LayoutRefused, browser_assets

pytestmark = pytest.mark.class_a
ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "app.css": ("nm/app/app.css", "text/css"),
    "app.js": ("nm/app/app.js", "text/javascript"),
    "index.html": ("nm/app/index.html", "text/html"),
    "brain-preview.html": ("nm/legal_brain/brain-preview.html", "text/html"),
    "brain-preview.js": ("nm/legal_brain/brain-preview.js", "text/javascript"),
    "source-reader.js": ("nm/legal_brain/source-reader.js", "text/javascript"),
    "loop-progress.js": ("nm/legal_brain/loop-progress.js", "text/javascript"),
    "matter-workspace.css": ("nm/legal_brain/matter-workspace.css", "text/css"),
    "matter-workspace.js": ("nm/legal_brain/matter-workspace.js", "text/javascript"),
    "advocate-preferences.js": ("nm/legal_brain/advocate-preferences.js", "text/javascript"),
    "draft-vault.js": ("nm/arrive/draft-vault.js", "text/javascript"),
    "dictation-worklet.js": ("nm/open_matter/dictation-worklet.js", "text/javascript"),
    "intake-materials.css": ("nm/open_matter/intake-materials.css", "text/css"),
    "intake-materials.js": ("nm/open_matter/intake-materials.js", "text/javascript"),
}


@pytest.fixture
def http_boundary(client, monkeypatch):
    def not_an_api_oracle():
        raise AssertionError("Browser files must not access application/private owners")

    # The actual application may supply only its public asset population.
    # Static reads do not consult its health or private API/data projections.
    monkeypatch.setattr(api.application(), "health", not_an_api_oracle)
    yield client


def test_all_fourteen_declared_browser_assets_are_the_exact_shipped_population():
    assert browser_assets(root=ROOT) == {
        name: ROOT / path for name, (path, _media_type) in ASSETS.items()
    }
    assert len(ASSETS) == 14
    # The old tree is migration evidence, not a runtime import or public root.
    assert not any(isinstance(route, Mount) and route.path == "/static"
                   for route in api.app.routes)


def test_actual_served_application_owns_the_renderer_asset_population(http_boundary):
    from nm.app.composition import Application

    application = api.application()
    assert type(application) is Application
    assert dict(application.browser_asset_paths()) == browser_assets(root=ROOT)
    assert application.browser_asset_paths() is application.browser_asset_paths()
    assert http_boundary.get("/").content == (ROOT / "nm/app/index.html").read_bytes()


@pytest.mark.parametrize("name", tuple(ASSETS))
def test_every_real_asset_get_retains_exact_bytes_media_and_cache_headers(http_boundary, name):
    path, media_type = ASSETS[name]
    response = http_boundary.get(f"/static/{name}")
    assert response.status_code == 200
    assert response.content == (ROOT / path).read_bytes()
    assert response.headers["content-type"] == f"{media_type}; charset=utf-8"
    assert response.headers["content-length"] == str(len(response.content))
    assert response.headers["cache-control"] == "no-cache, must-revalidate"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["etag"] and response.headers["last-modified"]


@pytest.mark.parametrize("url", ("/", "/static/index.html", "/static/app.js",
                                 "/static/brain-preview.html", "/static/dictation-worklet.js"))
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


@pytest.mark.parametrize("url", ("/", "/static/app.css", "/static/brain-preview.html"))
def test_head_retains_get_headers_without_a_body(http_boundary, url):
    original = http_boundary.get(url)
    response = http_boundary.head(url)
    assert response.status_code == 200 and response.content == b""
    for name in ("content-type", "content-length", "cache-control", "etag", "last-modified"):
        assert response.headers[name] == original.headers[name]


def test_served_entry_pages_keep_their_existing_script_order(http_boundary):
    index = http_boundary.get("/")
    assert index.content == (ROOT / "nm/app/index.html").read_bytes()
    assert re.findall(r'<script src="([^"]+)"', index.text) == [
        "/static/advocate-preferences.js", "/static/draft-vault.js",
        "/static/source-reader.js", "/static/loop-progress.js", "/static/app.js",
        "/static/matter-workspace.js", "/static/intake-materials.js",
    ]
    preview = http_boundary.get("/static/brain-preview.html")
    assert re.findall(r'<script src="([^"]+)" defer>', preview.text) == [
        "/static/source-reader.js", "/static/brain-preview.js",
    ]


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


def test_declared_alias_cannot_masquerade_as_another_media_or_file_name(tmp_path):
    _temporary_browser_root(tmp_path)
    target = tmp_path / "nm" / "source_layout.json"
    layout = json.loads(target.read_text(encoding="utf-8"))
    layout["browser_assets"]["another.js"] = "nm/app/index.html"
    target.write_text(json.dumps(layout), encoding="utf-8")
    with _temporary_client(tmp_path) as client:
        with pytest.raises(BrowserAssetsRefused):
            client.get("/static/another.js")
