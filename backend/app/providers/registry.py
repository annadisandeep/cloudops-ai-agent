"""Provider resolution.

In demo mode, ``gcp``/``aws`` route to the demo adapter (filtered to the
emulated provider) so the whole product works without credentials. Live
adapters are only constructed when explicitly enabled AND allowlisted —
otherwise requests fail closed with 403.
"""

from __future__ import annotations

from ..config import get_settings
from ..errors import ProviderDisabledError, ValidationApiError
from .base import ProviderAdapter
from .demo import DemoAdapter


def get_adapter(provider: str, account: str | None = None) -> ProviderAdapter:
    settings = get_settings()
    if provider not in ("demo", "gcp", "aws"):
        raise ValidationApiError(f"Unknown provider '{provider}'")

    if provider == "demo":
        if not settings.demo_mode:
            raise ProviderDisabledError("Demo mode is disabled.")
        return DemoAdapter()

    if provider == "gcp":
        if settings.gcp_enabled:
            from .gcp import GcpAdapter

            projects = settings.gcp_allowed_project_list
            project = account or (projects[0] if projects else None)
            if not project:
                raise ProviderDisabledError("GCP is enabled but no projects are allowlisted.")
            return GcpAdapter(project)
        if settings.demo_mode:
            return DemoAdapter(emulated_provider="gcp")
        raise ProviderDisabledError("GCP provider is not enabled.")

    # aws
    if settings.aws_enabled:
        from .aws import AwsAdapter

        return AwsAdapter(account)
    if settings.demo_mode:
        return DemoAdapter(emulated_provider="aws")
    raise ProviderDisabledError("AWS provider is not enabled.")
