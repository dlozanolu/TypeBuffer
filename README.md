# TypeBuffer

TypeBuffer is a masked keyboard input tool. It lets you type without anything appearing on the screen immediately, and after a brief pause, the accumulated text is dumped at once into the active window. It can also run a spell/grammar checker and an AI translator over your text before outputting it.

## Features

- **Masks** normal typing (letters, symbols, spaces...).
- After **0.3 seconds** of inactivity, it outputs the buffer into the active application.
- **Spellchecker** (optional) using LanguageTool, OpenAI, Claude, DeepSeek, or any custom endpoint.
- **Translation mode**: start a phrase with a 2-letter language code (e.g. `en: Hola mundo`) and it will be translated into that language by your AI provider.
- **System tray icon** (Windows) to toggle on/off, open Settings, or exit.
- **First-run welcome screen** with a settings form (timeout, autostart, spellcheck, translation, API keys).
- **Instant passthrough**: arrow keys, Caps Lock, Ctrl+C/Ctrl+V, Alt, Win, Del, F-keys, etc. are passed instantly without delay.

> **Note for Windows:** It uses a low-level `WH_KEYBOARD_LL` hook with selective blocking. A Windows *Service* (Session 0) cannot capture the desktop keyboard; use the included autostart script to run it at user login instead.

## Requirements

- **Python 3.10+**
- **Windows 10/11** (recommended); also works on macOS/Linux with limitations.

### Dependencies

Install them with:

```bash
pip install -r requirements.txt
```

| Package  | Purpose                          |
|----------|----------------------------------|
| `pynput` | Keyboard hook and input control  |
| `pystray`| System tray icon (near the clock)|
| `Pillow` | Image handling for the tray icon |

## Quick Install

```bash
pip install -r requirements.txt
python TypeBuffer.py
```

On Windows, you can also use `TypeBuffer.bat`.

> The first time you run it, a **welcome window** opens so you can configure the timeout, autostart, spellchecker, translation, and your AI API keys.

## Usage

```bash
python TypeBuffer.py
python TypeBuffer.py --timeout 0.3
python TypeBuffer.py --corrector openai
python TypeBuffer.py --corrector claude
python TypeBuffer.py --corrector deepseek
python TypeBuffer.py --corrector none
python TypeBuffer.py --quiet
```

| Option | Description |
|--------|-------------|
| `--timeout` | Seconds of pause before flushing the text (default: 0.3) |
| `--corrector` | AI/spellcheck provider: `languagetool`, `openai`, `claude`, `deepseek`, or `none` |
| `--lang` | Language for the spellchecker (default: `en`) |
| `--quiet` | Only log to file (useful for autostart setups) |
| `ESC` | Exits masked mode |

### Translation Mode

Start your phrase with a 2-letter language code followed by `: `:

```
en: Hola mundo, ¿cómo estás?
```

TypeBuffer sends `Hola mundo, ¿cómo estás?` to your configured AI provider and outputs the English translation automatically. It supports all common language codes (`es`, `en`, `fr`, `de`, `it`, `pt`, `ca`, `eu`, `gl`, `ru`, `zh`, `ja`, `ko`, ...).

### AI Providers & API Keys

Configure providers from the **Settings** window (tray icon → Settings), or edit `config.json` located in:

- Windows: `%LOCALAPPDATA%\TypeBuffer\config.json`
- Linux/macOS: `~/.local/share/TypeBuffer/config.json`

Predefined providers with their endpoints:

| Provider  | Endpoint                          | API Key |
|-----------|-----------------------------------|---------|
| OpenAI    | `https://api.openai.com/v1`       | Yes     |
| Claude    | `https://api.anthropic.com/v1`    | Yes     |
| DeepSeek  | `https://api.deepseek.com/v1`     | Yes     |
| LanguageTool | `https://api.languagetool.org/v2/check` | Free (no key) |

You can also register a **custom provider** (name + endpoint + API key + model) if your favorite one is not in the list.

### Local LanguageTool

Set the LanguageTool endpoint to your local server in Settings:

```
http://127.0.0.1:8010/v2/check
```

## Build (Stand-alone Executable)

```bash
# Windows
build.bat

# Linux/macOS
bash build.sh
```

The binary will be placed in `dist/TypeBuffer` (or `TypeBuffer.exe`). GitHub Actions are provided to automatically build cross-platform releases on new tags.

## Login Autostart (Run at Startup)

```bash
python setup_autostart.py --install
python setup_autostart.py --uninstall
```

Compatible with Windows (Startup folder), Linux (`~/.config/autostart`), and macOS (`LaunchAgents`). You can also enable it from the welcome/settings window.

## Structure

```
TypeBuffer.py         # Main application (keyboard hook + buffer)
corrector.py          # Spellchecker + translator (multi-provider AI)
config.py             # Settings storage (config.json)
gui.py                # Welcome & Settings windows (tkinter)
tray.py               # System tray icon (pystray)
setup_autostart.py    # Cross-platform login autostart script
TypeBuffer.bat        # Windows launcher
test_tray.bat         # Standalone tray icon test
build.bat / build.sh  # PyInstaller build scripts
assets/               # Tray icons (active/inactive)
requirements.txt
requirements-dev.txt
```

## Privacy

- Masked text only lives in memory until it is flushed.
- With the spellchecker using LanguageTool (default public API), text is sent to LanguageTool.org.
- With an AI provider (OpenAI/Claude/DeepSeek/custom), text is sent to the configured API endpoint.
- With `--corrector none` and translation disabled, no network requests are made.

## License

MIT — see [LICENSE](LICENSE).
