import updater


def test_parse_version():
    assert updater.parse_version("v1.2.10") == (1, 2, 10)
    assert updater.parse_version("1.2") == (1, 2)
    assert updater.parse_version("2.0.0-beta.1") == (2, 0, 0, 1)
    assert updater.parse_version("") == (0,)


def test_is_newer():
    assert updater.is_newer("1.3.0", "1.2.9")
    assert not updater.is_newer("1.2.9", "1.3.0")
    assert not updater.is_newer("1.2.0", "1.2.0")


def test_check_for_update_reports_newer(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda timeout=6.0: "v9.9.9")
    assert updater.check_for_update() == ("9.9.9", updater.RELEASES_PAGE)


def test_check_for_update_ignores_current(monkeypatch):
    monkeypatch.setattr(updater, "fetch_latest_version", lambda timeout=6.0: "v0.0.1")
    assert updater.check_for_update() is None


def test_check_for_update_is_silent_on_failure(monkeypatch):
    def boom(timeout=6.0):
        raise OSError("offline")

    monkeypatch.setattr(updater, "fetch_latest_version", boom)
    assert updater.check_for_update() is None
