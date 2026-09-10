# TypeBuffer

Teclado en modo máscara: escribes sin que se vea nada en pantalla y, tras una pausa, el texto se vuelca de golpe en la ventana activa. Opcionalmente lo pasa por un corrector ortográfico/gramatical con contexto de frase.

## Qué hace

- **Enmascara** la escritura normal (letras, signos, espacios…)
- Tras **2 segundos** sin teclear, escribe el buffer en la app en foco
- **Corrector** opcional (LanguageTool u OpenAI) sobre la frase/párrafo completo
- **Pasan al instante** (sin delay): flechas, Bloq Mayús, Ctrl+C/V, Alt, Win, Supr, F-keys…

> En Windows usa un hook de teclado de bajo nivel con bloqueo selectivo.  
> Un *servicio* de Windows (Session 0) no puede capturar el teclado del escritorio; usa arranque al iniciar sesión.

## Requisitos

- Python 3.10+
- Windows 10/11 (recomendado), también macOS/Linux con limitaciones
- Dependencia: `pynput`

## Instalación rápida

```bash
pip install -r requirements.txt
python TypeBuffer.py
```

En Windows también puedes usar `TypeBuffer.bat`.

## Uso

```bash
python TypeBuffer.py
python TypeBuffer.py --timeout 2
python TypeBuffer.py --corrector languagetool --lang es
python TypeBuffer.py --corrector openai
python TypeBuffer.py --corrector none
python TypeBuffer.py --quiet
```

| Opción | Descripción |
|--------|-------------|
| `--timeout` | Segundos de pausa antes de volcar (default: 2) |
| `--corrector` | `languagetool` (default), `openai` o `none` |
| `--lang` | Idioma del corrector (default: `es`) |
| `--quiet` | Solo log a archivo (útil en autostart) |
| `ESC` | Sale del modo máscara |

### Corrector OpenAI

```bash
set OPENAI_API_KEY=sk-...
python TypeBuffer.py --corrector openai
```

Variables opcionales: `OPENAI_MODEL`, `OPENAI_BASE_URL`.

### LanguageTool local

```bash
set LANGUAGETOOL_URL=http://127.0.0.1:8010/v2/check
```

## Compilar (.exe)

```bash
# Windows
build.bat

# Linux/macOS
bash build.sh
```

El binario queda en `dist/TypeBuffer` (o `TypeBuffer.exe`).

## Arranque al iniciar sesión

```bash
python install_autostart.py --install
python install_autostart.py --uninstall
```

Compatible con Windows (Startup), Linux (`~/.config/autostart`) y macOS (LaunchAgents).

## Estructura

```
TypeBuffer.py         # aplicación principal
corrector.py          # LanguageTool / OpenAI
install_autostart.py  # autostart multiplataforma
TypeBuffer.bat        # launcher Windows
build.bat / build.sh  # PyInstaller
requirements.txt
requirements-dev.txt
```

## Privacidad

- El texto enmascarado solo vive en memoria hasta el volcado
- Con `--corrector languagetool` (API pública) el texto se envía a LanguageTool.org
- Con `--corrector openai` se envía a la API configurada
- Con `--corrector none` no hay red

## Licencia

MIT — ver [LICENSE](LICENSE).
