"""Former home of the citation owner, kept so archived imports still resolve.

The one owner moved to `nm.shared.citation_contracts` on 9 October 2026, when
the live citation engine needed it and the active product may not depend on the
archive. Nothing is defined here: a pattern written in this file would be the
second copy `tests/test_citation_patterns.py` refuses.
"""
from nm.shared.citation_contracts import (  # noqa: F401
    ANY_PROVISION,
    ARTICLE,
    CASE,
    ORDER,
    SECTION,
    ProvisionKeyBinding,
    ProvisionKeyState,
    bind_provision_key,
    cases_named,
    last_wanted_section,
    provision_label,
    provisions_cited,
    reporter_key,
    wanted_section,
)
