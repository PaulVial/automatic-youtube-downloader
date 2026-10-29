"""Lecture des playlists et téléchargement audio via yt-dlp."""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

log = logging.getLogger(__name__)

_UNAVAILABLE_TITLES = {"[Deleted video]", "[Private video]", "Deleted video", "Private video"}
_BOT_CHECK_MARKERS = ("confirm you're not a bot", "confirm you’re not a bot", "HTTP Error 429")
_THUMB_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class BotCheckError(RuntimeError):
    """YouTube bloque les requêtes (anti-bot). Inutile de continuer ce run."""


@dataclass(frozen=True)
class PlaylistEntry:
    video_id: str
    title: str
    playlist_url: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass(frozen=True)
class DownloadedTrack:
    mp3_path: Path
    thumbnail_path: Path | None
    info: dict


class _Logger:
    """Redirige les messages de yt-dlp vers logging (sans le bruit de progression)."""

    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug]"):
            log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


def _raise_if_bot_check(error: Exception) -> None:
    if any(marker.lower() in str(error).lower() for marker in _BOT_CHECK_MARKERS):
        raise BotCheckError(str(error)) from error


class YouTube:
    def __init__(self, base_options: dict):
        self._base = base_options

    @classmethod
    @contextmanager
    def open(cls, cookies: str | None = None, proxy: str | None = None) -> Iterator[YouTube]:
        options = {
            "logger": _Logger(),
            "quiet": True,
            "noprogress": True,
            "retries": 5,
            "fragment_retries": 5,
            "socket_timeout": 30,
        }
        if proxy:
            options["proxy"] = proxy
        with tempfile.TemporaryDirectory() as tmp:
            if cookies:
                # yt-dlp réécrit le fichier de cookies : on travaille sur une copie.
                cookie_file = os.path.join(tmp, "cookies.txt")
                Path(cookie_file).write_text(cookies, encoding="utf-8")
                options["cookiefile"] = cookie_file
            yield cls(options)

    def list_playlist(self, playlist_url: str) -> list[PlaylistEntry]:
        options = {**self._base, "extract_flat": "in_playlist", "skip_download": True}
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
        except DownloadError as error:
            _raise_if_bot_check(error)
            raise

        entries = []
        for entry in info.get("entries") or []:
            if not entry or not entry.get("id"):
                continue
            title = entry.get("title") or ""
            if title in _UNAVAILABLE_TITLES:
                log.info("Vidéo indisponible ignorée : %s", entry["id"])
                continue
            entries.append(PlaylistEntry(entry["id"], title, playlist_url))
        log.info("Playlist « %s » : %d vidéos", info.get("title", playlist_url), len(entries))
        return entries

    def download_mp3(self, video_url: str, workdir: Path, bitrate: str) -> DownloadedTrack:
        options = {
            **self._base,
            "format": "bestaudio/best",
            "outtmpl": str(workdir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate}
            ],
        }
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(video_url, download=True)
        except DownloadError as error:
            _raise_if_bot_check(error)
            raise

        mp3_files = list(workdir.glob("*.mp3"))
        if not mp3_files:
            raise RuntimeError("yt-dlp n'a produit aucun fichier MP3")
        thumbnails = [p for p in workdir.iterdir() if p.suffix.lower() in _THUMB_EXTENSIONS]
        return DownloadedTrack(mp3_files[0], thumbnails[0] if thumbnails else None, info)
