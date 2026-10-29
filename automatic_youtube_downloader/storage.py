"""Destinations des fichiers (Google Drive ou dossier local) et fichier d'état."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_FOLDER_MIME = "application/vnd.google-apps.folder"


# --------------------------------------------------------------------------- destinations


class Destination(Protocol):
    def find_video(self, video_id: str) -> str | None: ...
    def name_exists(self, name: str) -> bool: ...
    def upload(self, path: Path, name: str, video_id: str) -> str: ...


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


class DriveDestination:
    """Dossier Google Drive. Le scope drive.file ne donne accès qu'aux fichiers créés par l'app :
    le dossier de destination est donc créé par le script lui-même."""

    def __init__(self, token_info: dict, folder_name: str, folder_id: str | None = None):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials.from_authorized_user_info(token_info, DRIVE_SCOPES)
        try:
            credentials.refresh(Request())
        except RefreshError as error:
            raise RuntimeError(
                "Token Google Drive refusé. S'il a expiré après 7 jours, l'app OAuth est restée en "
                "mode « Testing » : passe-la en « Production » puis régénère token.json."
            ) from error
        self._drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self.folder_id = folder_id or self._ensure_folder(folder_name)

    @classmethod
    def from_config(cls, cfg) -> DriveDestination:
        if cfg.drive_token_json:
            token_info = json.loads(cfg.drive_token_json)
        else:
            token_path = Path(cfg.drive_token_file)
            if not token_path.exists():
                raise FileNotFoundError(
                    f"{token_path} introuvable : lance d'abord scripts/get_drive_token.py"
                )
            token_info = json.loads(token_path.read_text(encoding="utf-8"))
        return cls(token_info, cfg.drive_folder_name, cfg.drive_folder_id)

    def _query(self, query: str) -> list[dict]:
        response = (
            self._drive.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=10)
            .execute(num_retries=3)
        )
        return response.get("files", [])

    def _ensure_folder(self, name: str) -> str:
        query = f"name = {_quote(name)} and mimeType = '{_FOLDER_MIME}' and trashed = false"
        found = self._query(query)
        if found:
            return found[0]["id"]
        folder = (
            self._drive.files()
            .create(body={"name": name, "mimeType": _FOLDER_MIME}, fields="id")
            .execute(num_retries=3)
        )
        log.info("Dossier Drive créé : %s", name)
        return folder["id"]

    def find_video(self, video_id: str) -> str | None:
        query = (
            f"appProperties has {{ key='youtube_id' and value={_quote(video_id)} }} "
            f"and {_quote(self.folder_id)} in parents and trashed = false"
        )
        found = self._query(query)
        return found[0]["id"] if found else None

    def name_exists(self, name: str) -> bool:
        query = f"name = {_quote(name)} and {_quote(self.folder_id)} in parents and trashed = false"
        return bool(self._query(query))

    def upload(self, path: Path, name: str, video_id: str) -> str:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(path), mimetype="audio/mpeg", resumable=True)
        body = {"name": name, "parents": [self.folder_id], "appProperties": {"youtube_id": video_id}}
        created = (
            self._drive.files().create(body=body, media_body=media, fields="id").execute(num_retries=3)
        )
        return created["id"]


class LocalDestination:
    """Dossier local, pratique pour tester sans Google Drive."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def find_video(self, video_id: str) -> str | None:
        return None

    def name_exists(self, name: str) -> bool:
        return (self.directory / name).exists()

    def upload(self, path: Path, name: str, video_id: str) -> str:
        target = self.directory / name
        shutil.copyfile(path, target)
        return str(target)


# --------------------------------------------------------------------------- état


class StateStore:
    """Mémorise les vidéos déjà traitées, dans un fichier JSON local ou sur GCS (gs://...)."""

    def __init__(self, uri: str):
        self.uri = uri
        self._blob = None
        if uri.startswith("gs://"):
            from google.cloud import storage

            bucket, _, name = uri[len("gs://") :].partition("/")
            self._blob = storage.Client().bucket(bucket).blob(name or "state.json")

    def load(self) -> dict:
        if self._blob is not None:
            text = self._blob.download_as_text() if self._blob.exists() else None
        else:
            path = Path(self.uri)
            text = path.read_text(encoding="utf-8") if path.exists() else None
        state = json.loads(text) if text else {}
        state.setdefault("videos", {})
        return state

    def save(self, state: dict) -> None:
        text = json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True)
        if self._blob is not None:
            self._blob.upload_from_string(text, content_type="application/json")
        else:
            path = Path(self.uri)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
