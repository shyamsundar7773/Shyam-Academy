from dataclasses import dataclass

from auth.firebase import mask_secret
from config.bootstrap import get_config_value


@dataclass(frozen=True)
class ProviderConfiguration:
    provider: str
    model: str
    account_reference: str | None
    credential_configured: bool
    base_url: str


def get_provider_configuration() -> ProviderConfiguration:
    provider = (get_config_value("SHYAM_ACADEMY_AI_PROVIDER", "mock") or "").strip().lower()
    model = get_config_value("SHYAM_ACADEMY_AI_MODEL", "development-classroom") or ""
    account = get_config_value("SHYAM_ACADEMY_AI_ACCOUNT_REFERENCE")
    credential = get_config_value("SHYAM_ACADEMY_AI_API_KEY")
    return ProviderConfiguration(
        provider, model, account, bool(credential),
        get_config_value(
            "SHYAM_ACADEMY_AI_BASE_URL", "https://api.openai.com/v1"
        ) or "",
    )


def provider_status() -> str:
    config = get_provider_configuration()
    if config.provider in {"mock", "development"}:
        return "mock"
    if not config.credential_configured:
        return "not_configured"
    if config.provider == "cloudflare" and not config.account_reference:
        return "not_configured"
    return "configured"


def masked_credential() -> str:
    return mask_secret(get_config_value("SHYAM_ACADEMY_AI_API_KEY"))
