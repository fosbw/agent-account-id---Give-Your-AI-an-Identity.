from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


class CapabilityError(ValueError):
    """Raised when a capability is invalid or not granted."""


_CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+$")


@dataclass(frozen=True)
class SiteCapability:
    site_id: str
    domains: tuple[str, ...]
    capabilities: tuple[str, ...]
    login_method: str
    status: str
    notes: str = ""

    def safe_metadata(self) -> dict:
        return asdict(self)


DEFAULT_SITE_CAPABILITIES: tuple[SiteCapability, ...] = (
    SiteCapability("google-workspace", ("google.com", "googleapis.com"), ("web.read", "web.search", "browser.navigate"), "google_oauth_or_workspace_sso", "conditional", "Depends on Workspace administrator policy."),
    SiteCapability("microsoft-entra", ("microsoft.com", "microsoftonline.com"), ("web.read", "web.search", "browser.navigate"), "oidc_or_google_federation", "conditional", "Requires tenant configuration; not a universal Microsoft login."),
    SiteCapability("notion", ("notion.so", "notion.com"), ("web.read", "web.search", "browser.navigate"), "oauth_or_api", "conditional", "Use an approved Notion integration and scopes."),
    SiteCapability("slack", ("slack.com",), ("web.read", "web.search", "browser.navigate"), "oauth_or_workspace_sso", "conditional", "Requires Workspace or app authorization."),
    SiteCapability("gitlab", ("gitlab.com",), ("web.read", "web.search", "browser.navigate"), "oauth_oidc_or_api", "conditional", "Depends on group or instance configuration."),
    SiteCapability("atlassian", ("atlassian.com", "atlassian.net"), ("web.read", "web.search", "browser.navigate"), "oauth_or_saml_sso", "conditional", "Depends on organization identity settings."),
    SiteCapability("linear", ("linear.app",), ("web.read", "web.search", "browser.navigate"), "oauth_or_api", "conditional", "Requires an approved Linear integration."),
    SiteCapability("github", ("github.com",), ("web.read", "web.search", "browser.navigate"), "github_oauth_or_app", "conditional", "Use GitHub OAuth or GitHub App authorization."),
)


class CapabilityRegistry:
    def __init__(self, sites: Iterable[SiteCapability] = DEFAULT_SITE_CAPABILITIES):
        self._sites = {site.site_id: site for site in sites}

    def list_sites(self) -> list[SiteCapability]:
        return [self._sites[key] for key in sorted(self._sites)]

    def get_site(self, site_id: str) -> SiteCapability:
        try:
            return self._sites[site_id]
        except KeyError as exc:
            raise CapabilityError(f"unknown site capability: {site_id}") from exc

    def check(self, site_id: str, capability: str) -> bool:
        self._validate(capability)
        site = self.get_site(site_id)
        return capability in site.capabilities

    def require(self, site_id: str, capability: str) -> None:
        if not self.check(site_id, capability):
            raise CapabilityError(f"capability not granted: {site_id}:{capability}")

    @staticmethod
    def _validate(capability: str) -> None:
        if capability == "*" or not isinstance(capability, str) or not _CAPABILITY.fullmatch(capability):
            raise CapabilityError("wildcard and malformed capabilities are not allowed")

    def export(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([site.safe_metadata() for site in self.list_sites()], indent=2) + "\n", encoding="utf-8")
