"""Unit tests for elset cache (hot list)."""

import json
from unittest.mock import MagicMock

from citrascope.elset_cache import ElsetCache


def test_refresh_updates_get_elsets():
    """Refresh with mocked API client updates get_elsets() with normalized list."""
    raw = [
        {
            "satelliteId": "12345",
            "satelliteName": "ISS",
            "tle": [
                "1 25544U 98067A  12345.67890123  .00012345  00000-0  12345-3 0  1234",
                "2 25544  51.6400 123.4567 0001234  0.0000  0.0000 15.12345678901234",
            ],
        },
        {
            "satelliteId": "99999",
            "satelliteName": "TEST-SAT",
            "tle": [
                "1 99999U 99001A  12345.67890123  .00000000  00000-0  00000-0 0  0000",
                "2 99999  55.0000 100.0000 0000000  0.0000  0.0000 12.34567890123456",
            ],
        },
    ]
    api_client = MagicMock()
    api_client.get_elsets_latest.return_value = raw
    logger = MagicMock()

    cache = ElsetCache(cache_path=None)  # no file
    assert cache.get_elsets() == []

    ok = cache.refresh(api_client, logger=logger, days=14)
    assert ok is True
    api_client.get_elsets_latest.assert_called_once_with(days=14)

    elsets = cache.get_elsets()
    assert len(elsets) == 2
    assert elsets[0]["satellite_id"] == "12345"
    assert elsets[0]["name"] == "ISS"
    assert len(elsets[0]["tle"]) == 2
    assert elsets[1]["satellite_id"] == "99999"
    assert elsets[1]["name"] == "TEST-SAT"


def test_refresh_returns_false_when_api_returns_none():
    """When get_elsets_latest returns None, refresh returns False and list is unchanged."""
    api_client = MagicMock()
    api_client.get_elsets_latest.return_value = None
    logger = MagicMock()

    cache = ElsetCache(cache_path=None)
    cache._list = [{"satellite_id": "1", "name": "Old", "tle": ["l1", "l2"]}]

    ok = cache.refresh(api_client, logger=logger)
    assert ok is False
    assert cache.get_elsets() == [{"satellite_id": "1", "name": "Old", "tle": ["l1", "l2"]}]


def test_load_from_file_restores_list(tmp_path):
    """load_from_file() restores in-memory list from processor-ready JSON."""
    cache_file = tmp_path / "elset_cache.json"
    stored = [
        {"satellite_id": "111", "name": "Sat A", "tle": ["line1", "line2"]},
        {"satellite_id": "222", "name": "Sat B", "tle": ["line1b", "line2b"]},
    ]
    cache_file.write_text(json.dumps(stored), encoding="utf-8")

    cache = ElsetCache(cache_path=cache_file)
    assert cache.get_elsets() == []
    cache.load_from_file()
    assert cache.get_elsets() == stored


def test_load_from_file_no_op_when_file_missing(tmp_path):
    """load_from_file() does nothing when file does not exist."""
    cache = ElsetCache(cache_path=tmp_path / "nonexistent.json")
    cache._list = [{"satellite_id": "1", "name": "X", "tle": ["a", "b"]}]
    cache.load_from_file()
    assert len(cache.get_elsets()) == 1


def test_refresh_writes_cache_file(tmp_path):
    """refresh() writes normalized list to cache_path when set."""
    api_client = MagicMock()
    api_client.get_elsets_latest.return_value = [
        {
            "satelliteId": "1",
            "satelliteName": "One",
            "tle": [
                "1 1U 00000A  00000.0  00000-0  00000-0 0  000",
                "2 1  00.0000 000.0000 0000000  00.0000  00.0000 00.00000000000000",
            ],
        },
    ]
    cache_path = tmp_path / "processing" / "elset_cache.json"
    cache = ElsetCache(cache_path=cache_path)
    cache.refresh(api_client, logger=MagicMock())
    assert cache_path.exists()
    loaded = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(loaded) == 1
    assert loaded[0]["satellite_id"] == "1"
    assert loaded[0]["name"] == "One"
