from enum import StrEnum

from app.core.config import get_settings


class AppStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class AppConfigType(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


DEFAULT_APP_CONFIG = get_settings().default_app_config
