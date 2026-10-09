import time

import TypeBuffer


def _make_app(monkeypatch):
    app = TypeBuffer.TypeBufferApp()
    injected = []
    monkeypatch.setattr(app, "_type_text", injected.append)
    return app, injected


def test_needs_ai_detects_translation_and_spellcheck():
    app = TypeBuffer.TypeBufferApp()
    assert app._needs_ai("en: hola") is True
    assert app._needs_ai("hola") is False


def test_take_flush_waits_while_ai_is_busy(monkeypatch):
    app, injected = _make_app(monkeypatch)
    app.buffer = list("hola")
    app.last_type_time = time.time()
    with app.lock:
        app._ai_busy = True
        app._ai_source = "anterior"
        app._ai_token = object()
    assert app._take_flush() is None
    assert injected == []


def test_take_flush_aborts_pending_ai_when_next_text_is_due(monkeypatch):
    app, injected = _make_app(monkeypatch)
    with app.lock:
        app._ai_busy = True
        app._ai_source = "anterior"
        app._ai_token = object()
    app.buffer = list("nuevo")
    app.last_type_time = time.time() - 10
    assert app._take_flush() == "nuevo"
    assert injected == ["anterior"]
    assert app._ai_busy is False


def test_drain_results_discards_stale_result(monkeypatch):
    app, injected = _make_app(monkeypatch)
    app._ai_results.put((object(), "corregido", []))
    app._drain_results()
    assert injected == []


def test_drain_results_injects_matching_result(monkeypatch):
    app, injected = _make_app(monkeypatch)
    token = object()
    app._ai_busy = True
    app._ai_token = token
    app._ai_source = "hola"
    app._ai_results.put((token, "Hola.", []))
    app._drain_results()
    assert injected == ["Hola."]
    assert app._ai_busy is False
    assert app._ai_token is None


def test_drain_results_notifies_on_ai_fallback(monkeypatch):
    app, _ = _make_app(monkeypatch)
    notices = []
    app.set_status_notifier(notices.append)
    token = object()
    app._ai_busy = True
    app._ai_token = token
    app._ai_results.put((token, "texto", ["spellcheck failed (HTTP 401)"]))
    app._drain_results()
    assert notices and "spellcheck failed" in notices[0]


def test_set_active_drops_pending_ai(monkeypatch):
    app, _ = _make_app(monkeypatch)
    with app.lock:
        app._ai_busy = True
        app._ai_source = "hola"
        app._ai_token = object()
    app.set_active(False)
    assert app._ai_busy is False
    assert app._ai_token is None
    assert app._ai_source is None
    app.set_active(True)
