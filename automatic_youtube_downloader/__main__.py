"""Point d'entrée : python -m automatic_youtube_downloader [--dry-run] [--limit N] [--output-dir DIR]"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import naming, tagging
from .config import Config
from .storage import Destination, DriveDestination, LocalDestination, StateStore
from .youtube import BotCheckError, PlaylistEntry, YouTube

log = logging.getLogger("automatic_youtube_downloader")


class _CloudLoggingFormatter(logging.Formatter):
    """Une ligne JSON par log : Cloud Logging en lit la sévérité."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {"severity": record.levelname, "message": super().format(record)}
        return json.dumps(payload, ensure_ascii=False)


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if os.environ.get("CLOUD_RUN_JOB"):
        handler.setFormatter(_CloudLoggingFormatter("%(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _process(entry: PlaylistEntry, youtube: YouTube, destination: Destination, cfg: Config) -> dict:
    existing = destination.find_video(entry.video_id)
    if existing:
        log.info("Déjà présent dans Drive : %s", entry.title)
        return {"file_id": existing, "note": "déjà présent"}

    with tempfile.TemporaryDirectory() as tmp:
        track = youtube.download_mp3(entry.url, Path(tmp), cfg.audio_bitrate)
        artist, title = naming.artist_and_title(track.info)
        cover = tagging.square_cover(track.thumbnail_path) if track.thumbnail_path else None
        tagging.write_tags(track.mp3_path, artist, title, entry.video_id, entry.url, cover)

        name = naming.safe_filename(artist, title)
        if destination.name_exists(name):
            name = naming.safe_filename(artist, f"{title} [{entry.video_id}]")
        file_id = destination.upload(track.mp3_path, name, entry.video_id)

    log.info("OK : %s", name)
    return {"file": name, "file_id": file_id}


def run(cfg: Config, dry_run: bool, limit: int, output_dir: Path | None) -> int:
    store = StateStore(cfg.state_uri)
    state = store.load()
    videos: dict = state["videos"]
    failures = 0

    with YouTube.open(cookies=cfg.yt_cookies, proxy=cfg.proxy) as youtube:
        entries: dict[str, PlaylistEntry] = {}
        for playlist_url in cfg.playlists:
            try:
                for entry in youtube.list_playlist(playlist_url):
                    entries.setdefault(entry.video_id, entry)
            except BotCheckError:
                log.error("YouTube bloque les requêtes (anti-bot). Voir la section Dépannage du README.")
                return 2
            except Exception:
                log.exception("Impossible de lire la playlist %s", playlist_url)
                failures += 1

        def is_pending(video_id: str) -> bool:
            record = videos.get(video_id)
            if record is None:
                return True
            return record["status"] == "failed" and record.get("attempts", 0) < cfg.max_attempts

        pending = [e for e in entries.values() if is_pending(e.video_id)]
        if limit:
            pending = pending[:limit]
        log.info("%d vidéos au total, %d à traiter", len(entries), len(pending))

        if dry_run:
            for entry in pending:
                log.info("  - %s (%s)", entry.title, entry.url)
            return 0
        if not pending:
            return 1 if failures else 0

        destination: Destination = (
            LocalDestination(output_dir) if output_dir else DriveDestination.from_config(cfg)
        )

        for index, entry in enumerate(pending, 1):
            log.info("[%d/%d] %s", index, len(pending), entry.title)
            try:
                result = _process(entry, youtube, destination, cfg)
                videos[entry.video_id] = {
                    "status": "done", "title": entry.title, "updated_at": _now(), **result
                }
            except BotCheckError:
                log.error("YouTube bloque les requêtes (anti-bot). Arrêt du run, reprise au prochain.")
                failures += 1
                break
            except Exception as error:
                failures += 1
                previous = videos.get(entry.video_id, {})
                videos[entry.video_id] = {
                    "status": "failed",
                    "title": entry.title,
                    "attempts": previous.get("attempts", 0) + 1,
                    "error": str(error)[:500],
                    "updated_at": _now(),
                }
                log.exception("Échec : %s", entry.title)
            finally:
                store.save(state)  # après chaque morceau : un run interrompu reprend où il en était

    done = sum(1 for v in videos.values() if v["status"] == "done")
    log.info("Terminé. %d morceaux dans la bibliothèque, %d échecs sur ce run.", done, failures)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="liste ce qui serait téléchargé")
    parser.add_argument("--limit", type=int, default=None, help="nombre max de morceaux ce run")
    parser.add_argument("--output-dir", type=Path, help="écrit en local au lieu de Google Drive")
    args = parser.parse_args()

    _setup_logging()
    cfg = Config.from_env()
    limit = args.limit if args.limit is not None else cfg.max_downloads
    sys.exit(run(cfg, args.dry_run, limit, args.output_dir))


if __name__ == "__main__":
    main()
