import pytest

from automatic_youtube_downloader.config import parse_playlists
from automatic_youtube_downloader.naming import artist_and_title, safe_filename


@pytest.mark.parametrize(
    ("info", "expected"),
    [
        ({"title": "Bicep - Glue (Official Video)"}, ("Bicep", "Glue")),
        ({"title": "Fred again.. – Delilah (pull me out of this) [Official Audio]"},
         ("Fred again..", "Delilah (pull me out of this)")),
        ({"title": "Artist - Track (Extended Mix) [Free Download]"}, ("Artist", "Track (Extended Mix)")),
        ({"title": "Artist - Track (Someone Remix) | Label Records"}, ("Artist", "Track (Someone Remix)")),
        ({"title": "Artist - Track (Lyrics) #house #techno"}, ("Artist", "Track")),
        ({"title": "Glue", "artists": ["Bicep"], "track": "Glue", "channel": "Bicep - Topic"},
         ("Bicep", "Glue")),
        ({"title": "Glue", "channel": "Bicep - Topic"}, ("Bicep", "Glue")),
        ({"title": "Some Song (HD)", "channel": "ArtistVEVO"}, ("Artist", "Some Song")),
    ],
)
def test_artist_and_title(info, expected):
    assert artist_and_title(info) == expected


def test_safe_filename_removes_forbidden_chars():
    assert safe_filename("AC/DC", 'What? "Live"') == "ACDC - What Live.mp3"


def test_safe_filename_is_truncated():
    assert len(safe_filename("A" * 300, "B")) <= 154


def test_parse_playlists_accepts_urls_and_ids():
    raw = ("https://youtube.com/playlist?list=PLabc&si=xyz, PLdef\n"
           "https://www.youtube.com/watch?v=1&list=PLabc")
    assert parse_playlists(raw) == [
        "https://www.youtube.com/playlist?list=PLabc",
        "https://www.youtube.com/playlist?list=PLdef",
    ]
