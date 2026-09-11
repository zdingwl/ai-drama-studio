"""P9 Source identity resolution domain."""

# Import the Provider-wire adapter at package load so every P9 entry point (API, one-click
# orchestration and tests) uses the same source-owned Prop observation contract.  The adapter
# patches only Provider request/parse globals; published P9 Artifact schemas stay unchanged.
from app.source_resolution import providers_v9 as _providers_v9  # noqa: F401,E402
