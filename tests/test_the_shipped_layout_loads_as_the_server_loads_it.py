"""The shipped source layout loads exactly as the served app loads it before every page (5 Nov 2026: a new core module was declared
without its role's expected count moving with it, and once applied the app answered every page with an error for about three minutes).
The other layout tests check the reader on fixtures; this one reads the layout the app ships, and the page assets it serves from it."""
from nm.shared.source_layout import ROOT, browser_assets, load_layout


def test_the_shipped_layout_loads_and_names_the_page_assets():
    layout = load_layout(ROOT)
    assert layout["modules"]["nm.core_engine.titles"] == "core"
    served = browser_assets(root=ROOT)
    assert {"app.js", "app.css", "brain-sources.js"} <= set(served)
