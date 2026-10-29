"""Configuration lue depuis les variables d'environnement."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or default


def parse_playlists(raw: str) -> list[str]:
    """Accepte des URLs ou des IDs séparés par des virgules, espaces ou retours à la ligne."""
    urls = []
    for item in re.split(r"[,\s]+", raw.strip()):
        if not item:
            continue
        if item.startswith("http"):
            playlist_id = parse_qs(urlparse(item).query).get("list", [None])[0]
            if not playlist_id:
                raise ValueError(f"URL de playlist sans paramètre 'list=' : {item}")
        else:
            playlist_id = item
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        if url not in urls:
            urls.append(url)
    return urls


@dataclass(frozen=True)
class Config:
    playlists: list[str]
    state_uri: str
    drive_folder_name: str
    drive_folder_id: str | None
    drive_token_json: str | None
    drive_token_file: str | None
    yt_cookies: str | None
    proxy: str | None
    audio_bitrate: str
    max_downloads: int
    max_attempts: int

    @classmethod
    def from_env(cls) -> Config:
        playlists = parse_playlists(_env("PLAYLISTS", ""))
        if not playlists:
            raise ValueError("PLAYLISTS est vide : indique au moins une URL de playlist.")
        return cls(
            playlists=playlists,
            state_uri=_env("STATE_URI", "state.json"),
            drive_folder_name=_env("DRIVE_FOLDER_NAME", "DJ - YouTube"),
            drive_folder_id=_env("DRIVE_FOLDER_ID"),
            drive_token_json=_env("DRIVE_TOKEN_JSON"),
            drive_token_file=_env("DRIVE_TOKEN_FILE", "token.json"),
            yt_cookies=_env("YT_COOKIES"),
            proxy=_env("PROXY_URL"),
            audio_bitrate=_env("AUDIO_BITRATE", "320"),
            max_downloads=int(_env("MAX_DOWNLOADS_PER_RUN", "0")),
            max_attempts=int(_env("MAX_ATTEMPTS", "3")),
        )
