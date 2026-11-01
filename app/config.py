import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# A blank secret must stop startup: anyone could sign webhooks with an empty key.
Required = Annotated[str, Field(min_length=1)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    whatsapp_phone_number_id: Required
    whatsapp_app_secret: Required
    whatsapp_access_token: Required
    whatsapp_verify_token: Required
    graph_api_version: str = "v23.0"

    # Telegram stays off until both of these are set.
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    # This server's HTTPS address, so it can register its Telegram webhook.
    public_url: str = ""

    vault_key: Required  # Base64 of 32 random bytes. Losing it loses the vault.
    api_token: Required  # Sent by the web app on every session API call.

    database_path: Path = Path("data/app.db")
    checkpoint_path: Path = Path("data/checkpoints.db")
    files_path: Path = Path("data/files")

    # Any OpenAI-compatible endpoint. Production uses the freellmpool proxy.
    llm_base_url: str = ""
    llm_api_key: str = "unused"
    llm_model: str = "auto"

    language_service_url: str = ""
    default_language: str = "en"
    choose_language: bool = True  # Ask for a language before anything else.
    browser_worker_url: str = ""
    # The browser service in browser-product/, which takes over from the two above.
    browser_product_url: str = ""
    browser_product_key: str = ""
    # "portal" runs its fixed mock portal. "general" drives real pages step by step.
    browser_product_mode: Literal["portal", "general", "bridge"] = "portal"
    # For "general": JSON mapping each portal_id to its start page.
    portal_urls: str = "{}"
    # The browser service's own ceiling, whatever a form allows. Raise it with the service.
    browser_upload_max_bytes: int = 1_048_576

    # Runs a fake portal and fake extraction, so the loop can be tried end to end.
    use_standins: bool = False
    # Used when the rule engine is not merged, or matched nothing to choose from.
    default_portal_id: str = ""

    # Stays off unless the applicant genuinely qualifies. When off, the agent
    # stops at the review page and never presses final submit.
    allow_real_submit: bool = False
    # When real submit is off, sends a one-time link so the user presses Submit themselves.
    submit_link: bool = False
    final_submit_pattern: str = (
        r"\b(final\s+submit|submit\s+application|submit|pay(ment)?|e-?sign)\b"
    )
    max_explore_steps: int = 40
    max_upload_bytes: int = 20_000_000
    cors_origins: str = ""  # Comma separated, for the web app.

    def portal_url_map(self) -> dict[str, str]:
        return json.loads(self.portal_urls)
