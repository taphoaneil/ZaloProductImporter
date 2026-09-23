from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from .config import Config, load_config, validate_config
from .products import Product, load_products
from .results import new_result_path, write_result


QUOTA_ERROR_CODES = {821}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "catalogs":
            return _cmd_catalogs(args)
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "create":
            return _cmd_create(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ZaloProductImporter",
        description="Bulk create Zalo catalog products from JSON input.",
    )
    parser.add_argument("--config", default="config.json", help="Path to config JSON.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate config and product input.")
    validate_parser.add_argument("--input", default="products.json", help="Path to products JSON.")

    catalogs_parser = subparsers.add_parser("catalogs", help="List product catalogs and catalog IDs.")
    catalogs_parser.add_argument("--limit", type=int, default=100, help="Max catalogs to request.")

    list_parser = subparsers.add_parser("list", help="List products in a catalog.")
    list_parser.add_argument(
        "--catalog-id",
        required=True,
        help="Catalog ID to list.",
    )
    list_parser.add_argument("--limit", type=int, default=100, help="Max products to request.")

    create_parser = subparsers.add_parser("create", help="Create products from JSON input.")
    create_parser.add_argument("--input", default="products.json", help="Path to products JSON.")
    create_parser.add_argument("--dry-run", action="store_true", help="Validate and print payloads only.")
    create_parser.add_argument("--results-dir", default="results", help="Directory for result logs.")

    return parser


def _cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    errors = validate_config(config)
    product_result = load_products(args.input)
    errors.extend(product_result.errors)

    if errors:
        _print_errors(errors)
        return 1

    print(f"OK: config valid, {len(product_result.products)} product(s) valid.")
    return 0


def _cmd_catalogs(args: argparse.Namespace) -> int:
    from .client import ZaloCatalogClient

    config = _load_valid_config(args.config)
    client = ZaloCatalogClient(config)
    client.login()
    data = client.list_catalogs(limit=args.limit)
    _print_catalog_table(data)

    return 0 if _is_success(data) else 1


def _cmd_list(args: argparse.Namespace) -> int:
    from .client import ZaloCatalogClient

    config = _load_valid_config(args.config)
    client = ZaloCatalogClient(config)
    login = client.login()
    data = client.list_products(args.catalog_id, limit=args.limit)
    print(json.dumps({"login": login, "list_product": data}, ensure_ascii=False, indent=2))
    return 0 if _is_success(data) else 1


def _cmd_create(args: argparse.Namespace) -> int:
    config = _load_valid_config(args.config)
    product_result = load_products(args.input)
    if product_result.errors:
        _print_errors(product_result.errors)
        _write_invalid_result(args.results_dir, args.input, config, product_result.errors)
        return 1

    payloads = [product.to_create_payload() for product in product_result.products]
    if args.dry_run:
        print(json.dumps({"dry_run": True, "payloads": payloads}, ensure_ascii=False, indent=2))
        return 0

    from .client import ZaloCatalogClient

    client = ZaloCatalogClient(config)
    login = client.login()
    result = _create_products(
        client=client,
        config=config,
        products=product_result.products,
        source_file=args.input,
        login=login,
    )
    result_path = write_result(new_result_path(args.results_dir), result)
    print(f"Result written: {result_path}")
    print(
        f"Created: {len(result['created'])}, failed: {len(result['failed'])}, skipped: {len(result['skipped'])}"
    )
    return 0 if not result["failed"] and not result["skipped"] else 1


def _create_products(
    client: ZaloCatalogClient,
    config: Config,
    products: list[Product],
    source_file: str,
    login: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_file": source_file,
        "login": login,
        "created": [],
        "failed": [],
        "skipped": [],
    }

    for product_index, product in enumerate(products):
        payload = product.to_create_payload()
        try:
            payload["product_photos"], uploaded_photos = _prepare_product_photos(
                client,
                payload["product_photos"],
                source_file,
            )
        except Exception as exc:
            result["failed"].append(
                {
                    "product_name": payload["product_name"],
                    "price": payload["price"],
                    "catalog_id": payload["catalog_id"],
                    "payload": payload,
                    "response": {"error": str(exc)},
                }
            )
            continue

        response = client.create_product(payload)
        product_result = {
            "product_name": payload["product_name"],
            "price": payload["price"],
            "catalog_id": payload["catalog_id"],
            "payload": payload,
            "uploaded_photos": uploaded_photos,
            "response": response,
        }

        if _is_success(response):
            item = response.get("item") or response.get("data") or response
            result["created"].append(
                {
                    "product_id": _pick_product_id(item),
                    "product_name": payload["product_name"],
                    "price": payload["price"],
                    "description": payload["description"],
                    "product_photos": payload["product_photos"],
                    "uploaded_photos": uploaded_photos,
                    "catalog_id": payload["catalog_id"],
                    "response": response,
                }
            )
        else:
            result["failed"].append(product_result)
            error_code = response.get("error_code")
            if config.batch.stop_on_quota_error and error_code in QUOTA_ERROR_CODES:
                result["skipped"].extend(
                    {
                        "product_name": skipped.product_name,
                        "reason": f"Stopped after quota error {error_code}.",
                    }
                    for skipped in products[product_index + 1 :]
                )
                break

        if config.batch.delay_seconds:
            time.sleep(config.batch.delay_seconds)

    return result


def _prepare_product_photos(
    client: Any,
    product_photos: list[str],
    source_file: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    source_dir = Path(source_file).resolve().parent
    resolved_photos: list[str] = []
    uploaded_photos: list[dict[str, Any]] = []

    for photo in product_photos:
        temp_path: Path | None = None
        if _is_url(photo):
            temp_path = _download_photo_url(photo)
            photo_path = temp_path
            source_type = "url"
        else:
            photo_path = Path(photo)
            if not photo_path.is_absolute():
                photo_path = source_dir / photo_path
            if not photo_path.exists():
                raise FileNotFoundError(f"Photo file not found: {photo}")
            if not photo_path.is_file():
                raise ValueError(f"Photo path is not a file: {photo}")
            source_type = "local"

        try:
            upload_response = client.upload_product_photo(photo_path)
            if not _is_success(upload_response):
                raise RuntimeError(f"Upload photo failed for {photo}: {upload_response}")

            upload_data = upload_response.get("data") or upload_response
            if not isinstance(upload_data, dict):
                raise RuntimeError(f"Upload photo response missing data for {photo}: {upload_response}")
            photo_url = upload_data.get("normalUrl") or upload_data.get("hdUrl") or upload_data.get("thumbUrl")
            if not photo_url:
                raise RuntimeError(f"Upload photo response missing URL for {photo}: {upload_response}")

            resolved_photos.append(str(photo_url))
            uploaded_photos.append(
                {
                    "source": photo,
                    "source_type": source_type,
                    "resolved_path": str(photo_path),
                    "url": str(photo_url),
                    "photo_id": upload_data.get("photoId"),
                    "response": upload_response,
                }
            )
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    return resolved_photos, uploaded_photos


def _is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"}


def _download_photo_url(url: str, max_bytes: int = 25 * 1024 * 1024) -> Path:
    response = requests.get(url, stream=True, timeout=30)
    try:
        response.raise_for_status()
        suffix = _photo_suffix_from_url_or_content_type(
            url,
            response.headers.get("content-type", ""),
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            total_size = 0
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if not chunk:
                    continue
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise ValueError(f"Photo URL is larger than {max_bytes} bytes: {url}")
                temp_file.write(chunk)
    except Exception:
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        response.close()

    return temp_path


def _photo_suffix_from_url_or_content_type(url: str, content_type: str) -> str:
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
        return suffix
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    return ".jpg"


def _load_valid_config(path: str | Path) -> Config:
    config = load_config(path)
    errors = validate_config(config)
    if errors:
        raise ValueError("\n".join(errors))
    return config


def _write_invalid_result(
    results_dir: str | Path,
    source_file: str,
    config: Config,
    errors: list[str],
) -> None:
    write_result(
        new_result_path(results_dir),
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_file": source_file,
            "created": [],
            "failed": [],
            "skipped": [{"reason": error} for error in errors],
        },
    )


def _print_errors(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)


def _print_catalog_table(response: dict[str, Any]) -> None:
    if not _is_success(response):
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return

    catalogs = _extract_items(response)
    if not catalogs:
        print("No catalogs found.")
        return

    rows = []
    for item in catalogs:
        if not isinstance(item, dict):
            continue
        catalog_id = item.get("catalog_id") or item.get("id") or ""
        catalog_name = item.get("catalog_name") or item.get("name") or ""
        rows.append((str(catalog_id), str(catalog_name)))

    headers = ("catalog_id", "catalog_name")
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def _extract_items(response: dict[str, Any]) -> list[Any]:
    data = response.get("data")
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(response.get("items"), list):
        return response["items"]
    return []


def _is_success(response: dict[str, Any]) -> bool:
    return response.get("error_code") == 0


def _pick_product_id(item: Any) -> str | None:
    if isinstance(item, dict):
        nested_item = item.get("item")
        if isinstance(nested_item, dict):
            return nested_item.get("product_id") or nested_item.get("id")
        return item.get("product_id") or item.get("id")
    return None
