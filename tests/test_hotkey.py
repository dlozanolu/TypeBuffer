import TypeBuffer


def test_parse_combination():
    assert TypeBuffer.parse_hotkey("ctrl+shift+space") == (frozenset({"ctrl", "shift"}), 0x20)


def test_parse_aliases():
    assert TypeBuffer.parse_hotkey("control+super+t") == (frozenset({"ctrl", "win"}), ord("T"))
    assert TypeBuffer.parse_hotkey("win+alt+f9") == (frozenset({"win", "alt"}), 0x78)


def test_standalone_keys_that_are_safe():
    assert TypeBuffer.parse_hotkey("f13") == (frozenset(), 0x70 + 12)
    assert TypeBuffer.parse_hotkey("pause") == (frozenset(), 0x13)
    assert TypeBuffer.parse_hotkey("scrolllock") == (frozenset(), 0x91)


def test_bare_printable_key_is_rejected():
    assert TypeBuffer.parse_hotkey("a") is None
    assert TypeBuffer.parse_hotkey("space") is None
    assert TypeBuffer.parse_hotkey("enter") is None


def test_malformed_specs_are_rejected():
    assert TypeBuffer.parse_hotkey("ctrl+") is None
    assert TypeBuffer.parse_hotkey("ctrl++") is None
    assert TypeBuffer.parse_hotkey("ctrl+nope") is None
    assert TypeBuffer.parse_hotkey("") is None
    assert TypeBuffer.parse_hotkey(None) is None


def test_sanitize_chars_drops_dead_key_marks():
    assert TypeBuffer._sanitize_chars("a´b") == "ab"
    assert TypeBuffer._sanitize_chars("a\u00a8b") == "ab"
    assert TypeBuffer._sanitize_chars("a\x01b") == "ab"


def test_sanitize_chars_keeps_accents_and_whitespace():
    assert TypeBuffer._sanitize_chars("áéí óú ñ") == "áéí óú ñ"
    assert TypeBuffer._sanitize_chars("\n\t ") == "\n\t "
    assert TypeBuffer._sanitize_chars("日本語") == "日本語"
