"""Tags ID3 et pochette carrée, lisibles par Rekordbox / Serato / Traktor."""

from __future__ import annotations

import io
from pathlib import Path

from mutagen.id3 import APIC, COMM, ID3, TIT2, TPE1, TXXX
from PIL import Image

COVER_SIZE = 800


def square_cover(thumbnail: Path) -> bytes:
    """Recadre la miniature YouTube (16:9) en carré centré, au format JPEG."""
    with Image.open(thumbnail) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        if side > COVER_SIZE:
            image = image.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


def write_tags(
    mp3: Path,
    artist: str,
    title: str,
    video_id: str,
    source_url: str,
    cover: bytes | None,
) -> None:
    tags = ID3()  # repart de zéro : on ignore les tags hérités de la source
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=source_url))
    tags.add(TXXX(encoding=3, desc="youtube_id", text=video_id))
    if cover:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
    # ID3v2.3 : la version la mieux supportée par les logiciels DJ.
    tags.save(mp3, v2_version=3)
