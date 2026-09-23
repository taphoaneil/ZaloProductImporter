from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Product:
    product_name: str
    price: str
    description: str
    product_photos: list[str]
    catalog_id: str | None = None
    currency_unit: str = "VND"

    def to_create_payload(self) -> dict[str, Any]:
        return {
            "create_time": int(time.time() * 1000),
            "product_name": self.product_name,
            "price": self.price,
            "description": self.description,
            "product_photos": self.product_photos,
            "catalog_id": self.catalog_id,
            "currency_unit": self.currency_unit,
        }


@dataclass(frozen=True)
class ProductLoadResult:
    products: list[Product]
    errors: list[str]


def load_products(path: str | Path) -> ProductLoadResult:
    products_path = Path(path)
    if not products_path.exists():
        return ProductLoadResult([], [f"Input file not found: {products_path}"])

    raw = json.loads(products_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return ProductLoadResult([], ["Product input must be a JSON array."])

    products: list[Product] = []
    errors: list[str] = []
    for index, item in enumerate(raw, start=1):
        product, item_errors = _normalize_product(item, index)
        if item_errors:
            errors.extend(item_errors)
            continue
        products.append(product)

    return ProductLoadResult(products, errors)


def _normalize_product(
    item: Any,
    index: int,
) -> tuple[Product | None, list[str]]:
    prefix = f"products[{index}]"
    errors: list[str] = []
    if not isinstance(item, dict):
        return None, [f"{prefix} must be an object."]

    product_name = str(item.get("product_name") or "").strip()
    if not product_name:
        errors.append(f"{prefix}.product_name is required.")

    price = item.get("price", "")
    if price is None:
        price = ""
    price = str(price).strip()
    if price and not price.isdigit():
        errors.append(f"{prefix}.price must be digits only or empty.")

    description = str(item.get("description") or "")

    product_photos_raw = item.get("product_photos", [])
    if product_photos_raw is None:
        product_photos_raw = []
    if not isinstance(product_photos_raw, list):
        errors.append(f"{prefix}.product_photos must be an array.")
        product_photos: list[str] = []
    else:
        product_photos = [str(photo).strip() for photo in product_photos_raw if str(photo).strip()]
        if len(product_photos) > 5:
            errors.append(f"{prefix}.product_photos supports at most 5 photos.")

    catalog_id = str(item.get("catalog_id") or "").strip() or None
    if not catalog_id:
        errors.append(f"{prefix}.catalog_id is required.")

    if errors:
        return None, errors

    return (
        Product(
            product_name=product_name,
            price=price,
            description=description,
            product_photos=product_photos,
            catalog_id=catalog_id,
        ),
        [],
    )
