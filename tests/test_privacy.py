from privacy import redact


def test_redact_returns_only_the_length():
    assert redact("hola mundo") == "<10 chars>"
    assert redact("") == "<0 chars>"


def test_redact_never_leaks_the_content():
    out = redact("super-secret-password")
    assert "secret" not in out
    assert "password" not in out
