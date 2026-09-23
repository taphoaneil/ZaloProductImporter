from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_LOGIN_INFO_URL = "https://wpa.chat.zalo.me/api/login/getLoginInfo"
DEFAULT_PRODUCT_CREATE_URL = (
    "https://catalog.chat.zalo.me/api/prodcatalog/product/create?zpw_ver=686&zpw_type=30"
)
DEFAULT_PRODUCT_PHOTO_UPLOAD_URL = (
    "https://tt-files-wpa.chat.zalo.me/api/product/upload/photo?zpw_ver=686&zpw_type=30"
)
DEFAULT_PRODUCT_LIST_URL = (
    "https://catalog.chat.zalo.me/api/prodcatalog/product/list?zpw_ver=686&zpw_type=30"
)
DEFAULT_CATALOG_LIST_URL = (
    "https://catalog.chat.zalo.me/api/prodcatalog/catalog/list?zpw_ver=686&zpw_type=30"
)


@dataclass(frozen=True)
class Endpoints:
    login_info: str = DEFAULT_LOGIN_INFO_URL
    product_create: str = DEFAULT_PRODUCT_CREATE_URL
    product_photo_upload: str = DEFAULT_PRODUCT_PHOTO_UPLOAD_URL
    product_list: str = DEFAULT_PRODUCT_LIST_URL
    catalog_list: str = DEFAULT_CATALOG_LIST_URL


@dataclass(frozen=True)
class BatchConfig:
    delay_seconds: float = 0.5
    stop_on_quota_error: bool = True


@dataclass(frozen=True)
class Config:
    imei: str
    cookies: dict[str, str]
    endpoints: Endpoints
    batch: BatchConfig
    secret_key: str | None = None


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Config file not found: {config_path}")

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a JSON object.")

    cookies = _normalize_cookies(raw.get("cookies"))
    endpoints_raw = raw.get("endpoints") or {}
    batch_raw = raw.get("batch") or {}

    return Config(
        imei=str(raw.get("imei") or "").strip(),
        cookies=cookies,
        secret_key=_optional_string(raw.get("secret_key")),
        endpoints=Endpoints(
            login_info=str(endpoints_raw.get("login_info") or DEFAULT_LOGIN_INFO_URL),
            product_create=str(endpoints_raw.get("product_create") or DEFAULT_PRODUCT_CREATE_URL),
            product_photo_upload=str(
                endpoints_raw.get("product_photo_upload") or DEFAULT_PRODUCT_PHOTO_UPLOAD_URL
            ),
            product_list=str(endpoints_raw.get("product_list") or DEFAULT_PRODUCT_LIST_URL),
            catalog_list=str(endpoints_raw.get("catalog_list") or DEFAULT_CATALOG_LIST_URL),
        ),
        batch=BatchConfig(
            delay_seconds=float(batch_raw.get("delay_seconds", 0.5)),
            stop_on_quota_error=bool(batch_raw.get("stop_on_quota_error", True)),
        ),
    )


def validate_config(config: Config) -> list[str]:
    errors: list[str] = []
    if not config.imei:
        errors.append("config.imei is required.")
    if not config.cookies:
        errors.append("config.cookies is required.")
    for cookie_name in ("zpsid", "zpw_sek"):
        if cookie_name not in config.cookies:
            errors.append(f"config.cookies.{cookie_name} is recommended and currently missing.")
    if config.batch.delay_seconds < 0:
        errors.append("config.batch.delay_seconds must be >= 0.")
    return errors


def _normalize_cookies(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(cookie_value) for key, cookie_value in value.items() if cookie_value}

    if isinstance(value, list):
        cookies: dict[str, str] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            cookie_value = item.get("value")
            if name and cookie_value:
                cookies[str(name)] = str(cookie_value)
        return cookies

    return {}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
