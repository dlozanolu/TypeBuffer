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

## Why TypeBuffer? The Ergonomics of Blind Flow

Most typing tools and operating systems assume you require continuous on-screen feedback. But for experienced typists with developed muscle memory, constant visual feedback introduces subtle cognitive friction:

- **Cognitive Load & Flow State (Bypassing the Visual "Supervisor")**: When typing with standard feedback, the brain enters an endless supervisory loop: idea generation → motor typing → visual reading → micro-editing. The visual cortex acts as an uninvited supervisor, prompting you to pause or tweak phrases mid-thought. Suppressing immediate feedback routes mental ideas directly to motor execution, letting you type at the exact speed of thought.
- **Genuine Sensory & Visual Rest**: Typing with eyes closed or resting off-screen relieves digital eye strain—eliminating monitor flicker, blue light exposure, ocular muscle tension, and the dry-eye syndrome caused by unblinking screen focus.
- **Why Blind Typing Isn't Usually Recommended (The Expert Typist Paradox)**: Traditional touch typing courses strictly mandate visual monitoring because novice or casual typists easily commit accidental typos or subtle hand displacements off the home row, resulting in lines of unreadable gibberish before they notice. However, for precision typists with ingrained muscle memory, screenless typing becomes an extraordinary instrument of direct mental dictation.
- **The Intelligent Safety Net**: Even for precision writers, TypeBuffer provides complete peace of mind. Your thoughts are held in a silent buffer until you pause, and with optional AI proofreading or language prefixes (`en:`, `fr:`, `es:`), any minor slip or cross-language translation is resolved cleanly before it lands in your target application.

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

## Installation

### For Windows Users (Recommended)

1. Download **`TypeBuffer-Setup.exe`** from [**Releases**](https://github.com/dlozanolu/TypeBuffer/releases).
2. Run the installer. It configures the Start Menu shortcut, optional Desktop icon, and automatic startup with Windows.
3. On first launch, the welcome screen opens automatically to configure your preferences and AI keys.
4. **No Python or development tools required.**

*Note: You can also download `TypeBuffer-windows.exe` for a portable single-file version without installation.*

### For Developers (Run from Source)

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

### Pause & Resume Shortcut

Press **`Ctrl+Shift+Space`** at any time to pause or resume masking. The tray icon switches colour to reflect the current state, and pausing clears whatever is still sitting in the buffer.

The shortcut deliberately avoids `Ctrl+Alt+<key>` combinations: on Spanish and other international layouts `AltGr` is reported as `Ctrl+Alt`, so such a shortcut would collide with everyday characters like `@`, `€`, `[` or `{`.

You can change it under *Settings → Pause/resume shortcut*, or by editing `hotkey_toggle` in `config.json`. Accepted forms are modifier combinations (`ctrl+shift+f9`, `win+alt+t`) and standalone keys that are never used for typing (`pause`, `scrolllock`, `f1`–`f24`). A bare printable key is rejected, since it would swallow normal typing.

To exit completely, right-click the tray icon and choose **Exit**. `ESC` is passed straight through to the active application.

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

## Code Signing (Windows SmartScreen)

Unsigned Windows executables trigger the "Windows protected your PC" SmartScreen warning when downloaded from the internet. To remove it, sign the Windows binaries with [Azure Trusted Signing](https://learn.microsoft.com/azure/trusted-signing/). The release workflow already contains the signing steps (using the [`azure/artifact-signing-action`](https://github.com/Azure/trusted-signing-action)), gated behind a repository variable so releases still work before signing is configured.

To enable signing:

1. Create an [Azure Trusted Signing account](https://learn.microsoft.com/azure/trusted-signing/quickstart?tabs=registerrp-portal%2Caccount-portal) and a certificate profile.
2. Create an App Registration (service principal) and grant it the **Artifact Signing Certificate Profile Signer** role.
3. Configure [OpenID Connect (OIDC) federation](https://learn.microsoft.com/azure/trusted-signing/how-to-signing-integrations) between GitHub and Azure (a federated credential for this repository).
4. Add these secrets in **Settings → Secrets and variables → Actions**:
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
   - `AZURE_SUBSCRIPTION_ID`
   - `AZURE_SIGNING_ENDPOINT` (e.g. `https://eus.codesigning.azure.net/`)
   - `AZURE_SIGNING_ACCOUNT_NAME`
   - `AZURE_CERTIFICATE_PROFILE_NAME`
5. Add a repository **variable** `AZURE_SIGNING_ENABLED` set to `true`.

Once enabled, the next release will produce signed `TypeBuffer-Setup.exe` and `TypeBuffer-windows.exe` files with no SmartScreen warning.

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
installer.iss         # Inno Setup Windows installer script
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
