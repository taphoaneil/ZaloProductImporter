from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def new_result_path(results_dir: str | Path = "results") -> Path:
    directory = Path(results_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return directory / f"{timestamp}-create-result.json"


def write_result(path: str | Path, data: dict[str, Any]) -> Path:
    result_path = Path(path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result_path
