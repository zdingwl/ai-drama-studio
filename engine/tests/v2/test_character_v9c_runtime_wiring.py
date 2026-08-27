from __future__ import annotations

import engine.app.character_identity_v91 as identity_v91


def test_v91_progressive_identity_remains_available_for_historical_regression() -> None:
    assert identity_v91.RESOLVER_VERSION == "person-gallery-progressive-v9.1"
    assert callable(identity_v91.resolve_global_identities)
