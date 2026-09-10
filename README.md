# TypeBuffer

TypeBuffer is a masked keyboard input tool. It lets you type without anything appearing on the screen immediately, and after a brief pause, the accumulated text is dumped at once into the active window. Optionally, it passes your text through a spell and grammar checker with full sentence context before outputting it.

## Features

- **Masks** normal typing (letters, symbols, spaces...).
- After **1.5 seconds** of inactivity, it outputs the buffer into the active application.
- **Spellchecker** (optional, uses LanguageTool or OpenAI) that corrects the full sentence or paragraph.
- **Instant passthrough**: arrow keys, Caps Lock, Ctrl+C/Ctrl+V, Alt, Win, Del, F-keys, etc. are passed instantly without delay.

> **Note for Windows:** It uses a low-level `WH_KEYBOARD_LL` hook with selective blocking. A Windows *Service* (Session 0) cannot capture the desktop keyboard; use the included autostart script to run it at user login instead.

## Requirements

- Python 3.10+
- Windows 10/11 (recommended), also works on macOS/Linux with some limitations.
- Dependency: `pynput`

## Quick Install

```bash
pip install -r requirements.txt
python TypeBuffer.py
```

On Windows, you can also use `TypeBuffer.bat`.

## Usage

```bash
python TypeBuffer.py
python TypeBuffer.py --timeout 1.5
python TypeBuffer.py --corrector languagetool --lang en
python TypeBuffer.py --corrector openai
python TypeBuffer.py --corrector none
python TypeBuffer.py --quiet
```

| Option | Description |
|--------|-------------|
| `--timeout` | Seconds of pause before flushing the text (default: 1.5) |
| `--corrector` | `languagetool` (default), `openai`, or `none` |
| `--lang` | Language for the spellchecker (default: `en`) |
| `--quiet` | Only log to file (useful for autostart setups) |
| `ESC` | Exits masked mode |

### OpenAI Spellchecker

```bash
set OPENAI_API_KEY=sk-...
python TypeBuffer.py --corrector openai
```

Optional variables: `OPENAI_MODEL`, `OPENAI_BASE_URL`.

### Local LanguageTool

```bash
set LANGUAGETOOL_URL=http://127.0.0.1:8010/v2/check
```

## Build (Stand-alone Executable)

```bash
# Windows
build.bat

# Linux/macOS
bash build.sh
```

The binary will be placed in `dist/TypeBuffer` (or `TypeBuffer.exe`). Note: GitHub Actions are provided to automatically build cross-platform releases on new tags.

## Login Autostart (Run at Startup)

You can easily configure TypeBuffer to start automatically when you log into your computer.

```bash
python setup_autostart.py --install
python setup_autostart.py --uninstall
```

Compatible with Windows (Startup folder), Linux (`~/.config/autostart`), and macOS (`LaunchAgents`).

## Structure

```
TypeBuffer.py         # Main application
corrector.py          # LanguageTool / OpenAI integration
setup_autostart.py    # Cross-platform login autostart script
TypeBuffer.bat        # Windows launcher
build.bat / build.sh  # PyInstaller build scripts
requirements.txt
requirements-dev.txt
```

## Privacy

- Masked text only lives in memory until it is flushed.
- With `--corrector languagetool` (default public API), text is sent to LanguageTool.org.
- With `--corrector openai`, text is sent to the configured OpenAI API.
- With `--corrector none`, no network requests are made.

## License

MIT — see [LICENSE](LICENSE).