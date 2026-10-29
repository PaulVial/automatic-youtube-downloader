"""Déduit « Artiste - Titre » à partir des métadonnées YouTube."""

from __future__ import annotations

import re
import unicodedata

# Mentions inutiles entre parenthèses/crochets : "(Official Video)", "[Lyrics]", "(HD)"...
_NOISE = re.compile(
    r"\b(official|officiel(le)?|video|vid[eé]o|audio|lyrics?|paroles|clip|visuali[sz]er"
    r"|hd|hq|4k|8k|m/?v|premiere|free\s+download|out\s+now|explicit|full\s+version)\b",
    re.IGNORECASE,
)
# ...sauf si elles décrivent la version du morceau, essentielle pour un DJ.
_KEEP = re.compile(
    r"\b(mix|remix|edit|rework|bootleg|dub|vip|version|instrumental|acapella|flip|cover|live)\b",
    re.IGNORECASE,
)
_BRACKETS = re.compile(r"\s*(\([^()]*\)|\[[^\[\]]*\]|【[^【】]*】)")
_SEPARATOR = re.compile(r"\s+[-–—]+\s+")
_CHANNEL_SUFFIX = re.compile(r"\s*(-\s*topic|vevo|official)\s*$", re.IGNORECASE)
_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

MAX_FILENAME_LENGTH = 150


def _strip_noise(text: str) -> str:
    def replace(match: re.Match) -> str:
        group = match.group(1)
        return "" if _NOISE.search(group) and not _KEEP.search(group) else match.group(0)

    text = _BRACKETS.sub(replace, text)
    text = text.split(" | ")[0]  # "Artiste - Titre | Label"
    text = re.sub(r"\s#\w+", "", text)  # hashtags
    return _clean(text)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—\"'“”«»")
    return text.strip()


def _artist_from_channel(channel: str | None) -> str:
    return _clean(_CHANNEL_SUFFIX.sub("", channel or "")) or "Unknown Artist"


def artist_and_title(info: dict) -> tuple[str, str]:
    """Retourne (artiste, titre).

    Ordre de priorité :
    1. un titre de la forme « Artiste - Titre » (cas des chaînes de labels) ;
    2. les métadonnées musicales de YouTube (chaînes « - Topic », Content ID) ;
    3. le nom de la chaîne comme artiste.
    """
    raw_title = info.get("title") or info.get("id") or "Unknown"
    title = _strip_noise(raw_title)

    parts = _SEPARATOR.split(title, maxsplit=1)
    if len(parts) == 2 and all(p.strip() for p in parts):
        return _clean(parts[0]), _clean(parts[1])

    artists = info.get("artists") or ([info["artist"]] if info.get("artist") else [])
    track = info.get("track")
    if artists and track:
        return _clean(", ".join(artists[:3])), _strip_noise(track)

    return _artist_from_channel(info.get("channel") or info.get("uploader")), title


def safe_filename(artist: str, title: str, extension: str = "mp3") -> str:
    base = _FORBIDDEN_CHARS.sub("", f"{artist} - {title}")
    base = re.sub(r"\s+", " ", base).strip(" .")
    base = base[:MAX_FILENAME_LENGTH].rstrip(" .")
    return f"{base or 'track'}.{extension}"
