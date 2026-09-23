from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from .config import Config
from .crypto import decode_payload, encode_payload


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://chat.zalo.me",
    "Referer": "https://chat.zalo.me/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


class ZaloCatalogClient:
    def __init__(self, config: Config, timeout_seconds: int = 30):
        self.config = config
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.session.cookies.update(config.cookies)
        self.secret_key = config.secret_key
        self.uid: str | None = None

    def login(self) -> dict[str, Any]:
        if self.secret_key:
            return {"error_code": 0, "has_secret_key": True, "source": "config"}

        params = {
            "imei": self.config.imei,
            "type": "30",
            "client_version": "645",
            "computer_name": "Web",
            "ts": str(int(time.time() * 1000)),
        }
        response = self.session.get(
            self.config.endpoints.login_info,
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error_code") not in (None, 0):
            raise RuntimeError(f"Zalo login failed: {data}")

        login_data = data.get("data") or {}
        self.secret_key = login_data.get("zpw_enk")
        self.uid = str(login_data.get("uid") or "") or None
        if not self.secret_key:
            raise RuntimeError(f"Zalo login did not return zpw_enk: {data}")

        return {
            "error_code": 0,
            "has_secret_key": True,
            "uid": self.uid,
            "phone_number": login_data.get("phone_number"),
        }

    def list_products(self, catalog_id: str, limit: int = 100) -> dict[str, Any]:
        payload = {
            "catalog_id": catalog_id,
            "limit": limit,
            "version_catalog": 0,
            "last_product_id": "-1",
            "page": 0,
        }
        return self._post_encoded(self.config.endpoints.product_list, payload)

    def list_catalogs(self, limit: int = 100) -> dict[str, Any]:
        payload = {
            "version_list_catalog": 0,
            "limit": limit,
            "last_product_id": -1,
            "page": 0,
        }
        return self._post_encoded(self.config.endpoints.catalog_list, payload)

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_encoded(self.config.endpoints.product_create, payload)

    def upload_product_photo(self, path: str | Path) -> dict[str, Any]:
        if not self.secret_key:
            self.login()
        assert self.secret_key

        photo_path = Path(path)
        content = _normalize_photo_content(photo_path)
        payload = {
            "totalChunk": 1,
            "fileName": photo_path.name,
            "clientId": int(time.time() * 1000),
            "totalSize": len(content),
            "imei": self.config.imei,
            "chunkId": 1,
            "featureId": 2,
        }
        encoded = encode_payload(payload, self.secret_key)
        separator = "&" if "?" in self.config.endpoints.product_photo_upload else "?"
        url = (
            self.config.endpoints.product_photo_upload
            + separator
            + "params="
            + urllib.parse.quote(encoded, safe="")
        )
        headers = dict(self.session.headers)
        headers.pop("Content-Type", None)
        headers["zcommandId"] = "12036"
        if shutil.which("curl"):
            result = self._upload_product_photo_with_curl(
                url=url,
                content=content,
                filename=photo_path.name,
                headers=headers,
            )
            result["_http_status"] = 200
            return result

        files = {
            "chunkContent": (photo_path.name, content, "application/octet-stream"),
        }
        response = self.session.post(
            url,
            files=files,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        result = self._decode_response(response)
        result["_http_status"] = response.status_code
        return result

    def _upload_product_photo_with_curl(
        self,
        url: str,
        content: bytes,
        filename: str,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        cookie_header = "; ".join(f"{name}={value}" for name, value in self.config.cookies.items())
        with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_photo:
            temp_photo.write(content)
            temp_photo.flush()
            config = "\n".join(
                [
                    "silent",
                    "show-error",
                    f"max-time = {self.timeout_seconds}",
                    f'url = "{_curl_escape(url)}"',
                    'request = "POST"',
                    f'header = "Accept: {headers.get("Accept", "application/json, text/plain, */*")}"',
                    'header = "Referer: https://chat.zalo.me/"',
                    f'header = "User-Agent: {headers.get("User-Agent", DEFAULT_HEADERS["User-Agent"])}"',
                    'header = "zcommandId: 12036"',
                    f'header = "Cookie: {_curl_escape(cookie_header)}"',
                    (
                        'form = "chunkContent=@'
                        + _curl_escape(temp_photo.name)
                        + ";filename="
                        + _curl_escape(filename)
                        + ';type=application/octet-stream"'
                    ),
                    "",
                ]
            )
            completed = subprocess.run(
                ["curl", "--config", "-"],
                input=config,
                text=True,
                capture_output=True,
                check=False,
                timeout=self.timeout_seconds + 5,
            )

        if completed.returncode != 0:
            raise RuntimeError(f"curl upload failed: {completed.stderr.strip()}")

        try:
            data = json.loads(completed.stdout)
        except ValueError as exc:
            raise RuntimeError(f"curl upload returned non-JSON: {completed.stdout[:500]}") from exc
        return self._decode_data(data)

    def _post_encoded(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.secret_key:
            self.login()
        assert self.secret_key

        encoded = encode_payload(payload, self.secret_key)
        body = "params=" + urllib.parse.quote(encoded, safe="")
        response = self.session.post(url, data=body, timeout=self.timeout_seconds)
        result = self._decode_response(response)
        result["_http_status"] = response.status_code
        return result

    def _decode_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            return {
                "non_json": True,
                "content_type": response.headers.get("content-type"),
                "text_prefix": response.text[:500],
            }

        if isinstance(data, dict) and data.get("data") and self.secret_key:
            return self._decode_data(data)

        return data

    def _decode_data(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("data") and self.secret_key:
            try:
                decoded = decode_payload(str(data["data"]), self.secret_key)
                if isinstance(decoded, dict):
                    return decoded
                return {"decoded_data": decoded}
            except Exception as exc:
                data["decode_error"] = str(exc)
        return data


def _normalize_photo_content(path: Path) -> bytes:
    with Image.open(path) as image:
        if image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        ):
            background = Image.new("RGB", image.size, "white")
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, format="JPEG", quality=90, optimize=True)
        return output.getvalue()


def _curl_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
