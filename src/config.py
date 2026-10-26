"""Load credentials from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root (parent of src/)
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_ID = ""
SKILL_VERSION = "1.0.5"
WEREAD_GATEWAY = "https://i.weread.qq.com/api/agent/gateway"
NOTION_VERSION = "2022-06-28"
FINISHED_ARCHIVE_NAME = "读完"


def _normalize_database_id(raw: str) -> str:
    value = raw.strip().replace("-", "")
    if len(value) != 32:
        return raw.strip()
    return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"


@dataclass(frozen=True)
class Settings:
    weread_api_key: str
    notion_token: str
    notion_database_id: str


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or ROOT / ".env")

    weread = os.getenv("WEREAD_API_KEY", "").strip()
    notion = os.getenv("NOTION_TOKEN", "").strip()
    database = os.getenv("NOTION_DATABASE_ID", DEFAULT_DATABASE_ID).strip()

    missing = [
        name
        for name, value in (
            ("WEREAD_API_KEY", weread),
            ("NOTION_TOKEN", notion),
            ("NOTION_DATABASE_ID", database),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required env vars: "
            + ", ".join(missing)
            + f"\nCopy .env.example to .env and fill in values (see {ROOT / '.env.example'})."
        )

    return Settings(
        weread_api_key=weread,
        notion_token=notion,
        notion_database_id=_normalize_database_id(database),
    )
