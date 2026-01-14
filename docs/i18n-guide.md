# Cortex Internationalization (i18n) Guide

This guide covers the internationalization system for the Cortex Linux CLI, including how to use translations in code and how to add new languages.

## Table of Contents

1. [Overview](#overview)
2. [Using Translations in Code](#using-translations-in-code)
3. [Adding a New Language](#adding-a-new-language)
4. [Message Catalog Structure](#message-catalog-structure)
5. [Translation Guidelines](#translation-guidelines)
6. [Testing Translations](#testing-translations)
7. [CLI Commands](#cli-commands)

## Overview

Cortex supports multiple languages through a YAML-based message catalog system. The i18n module provides:

- **Message translation** with variable interpolation
- **OS language auto-detection** from environment variables
- **Locale-aware formatting** for dates, times, and numbers
- **Graceful fallback** to English for missing translations

### Supported Languages

| Code | Language | Native Name |
|------|----------|-------------|
| `en` | English | English |
| `es` | Spanish | Español |
| `fr` | French | Français |
| `de` | German | Deutsch |
| `zh` | Chinese (Simplified) | 中文 |

## Using Translations in Code

### Basic Usage

```python
from cortex.i18n import t

# Simple translation
print(t("common.success"))  # Output: "Success" (in English)

# With variable interpolation
print(t("install.package_installed", package="docker"))
# Output: "docker installed successfully"
```

### Setting/Getting Language

```python
from cortex.i18n import set_language, get_language

# Get current language
current = get_language()  # Returns "en", "es", etc.

# Change language
set_language("es")
print(t("common.success"))  # Output: "Éxito"
```

### Locale-Aware Formatting

```python
from cortex.i18n.formatter import LocaleFormatter
from datetime import datetime

formatter = LocaleFormatter(language="de")

# Date formatting
dt = datetime(2024, 3, 15)
print(formatter.format_date(dt))  # Output: "15.03.2024"

# Number formatting
print(formatter.format_number(1234567))  # Output: "1.234.567"

# File size formatting
print(formatter.format_file_size(1536 * 1024))  # Output: "1.5 MB"

# Relative time
print(formatter.format_time_ago(past_datetime))  # Output: "vor 5 Minuten"
```

### Using the Global Formatter

```python
from cortex.i18n.formatter import format_date, format_number, format_file_size

# These use the current global language setting
print(format_date(datetime.now()))
print(format_number(1234567))
print(format_file_size(1024 * 1024))
```

## Adding a New Language

### Step 1: Create the Message Catalog

Create a new YAML file in `cortex/i18n/locales/`:

```bash
cp cortex/i18n/locales/en.yaml cortex/i18n/locales/<code>.yaml
```

### Step 2: Translate Messages

Edit the new file and translate all messages. Keep the same key structure as the English file.

```yaml
# Example: Japanese (ja.yaml)
common:
  success: "成功"
  error: "エラー"
  warning: "警告"
  # ... translate all keys
```

### Step 3: Register the Language

Add the language to `SUPPORTED_LANGUAGES` in `cortex/i18n/translator.py`:

```python
SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    # ... existing languages ...
    "ja": {"name": "Japanese", "native": "日本語"},
}
```

### Step 4: Add Locale Configuration

Add locale formatting rules in `cortex/i18n/formatter.py`:

```python
LOCALE_CONFIGS = {
    # ... existing configs ...
    "ja": {
        "date_format": "%Y年%m月%d日",
        "time_format": "%H:%M",
        "datetime_format": "%Y年%m月%d日 %H:%M",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "time_ago": {
            "seconds": "{n}秒前",
            "second": "1秒前",
            # ... complete the time_ago dict
        },
        "file_size_units": ["B", "KB", "MB", "GB", "TB"],
    },
}
```

### Step 5: Update Detector (Optional)

If the language has regional variants, add mappings in `cortex/i18n/detector.py`:

```python
LANGUAGE_MAPPINGS = {
    # ... existing mappings ...
    "ja": "ja",
    "ja_jp": "ja",
}
```

### Step 6: Add Tests

Add tests for the new language in `tests/test_i18n.py`:

```python
def test_japanese_translations(self):
    """Test Japanese translations."""
    from cortex.i18n.translator import Translator
    
    translator = Translator(language="ja")
    
    self.assertEqual(translator.translate("common.success"), "成功")
```

### Step 7: Update Documentation

Update this guide and the README to include the new language.

## Message Catalog Structure

### File Location

Message catalogs are stored in `cortex/i18n/locales/` as YAML files:

```text
cortex/i18n/locales/
├── en.yaml    # English (source language)
├── es.yaml    # Spanish
├── fr.yaml    # French
├── de.yaml    # German
└── zh.yaml    # Chinese
```

### Key Naming Convention

- Use **dot notation** for hierarchy: `category.subcategory.key`
- Use **snake_case** for key names
- Group by feature/module

```yaml
# Good
install:
  success: "Installation complete!"
  package_installed: "{package} installed successfully"

# Bad - flat keys
install_success: "Installation complete!"
installPackageInstalled: "{package} installed successfully"
```

### Variable Interpolation

Use `{variable_name}` syntax for dynamic values:

```yaml
# In the YAML file
install:
  # {package} - the package name
  package_installed: "{package} installed successfully"
  # {current}, {total} - progress numbers
  step_progress: "Step {current}/{total}"
```

```python
# In code
t("install.package_installed", package="docker")
# Output: "docker installed successfully"

t("install.step_progress", current=2, total=5)
# Output: "Step 2/5"
```

### Comments

Use comments to document variables and provide context for translators:

```yaml
# Variable documentation
install:
  # {package} - the name of the package being installed
  # {version} - the version number (optional)
  package_installed_version: "{package} ({version}) installed successfully"
```

## Translation Guidelines

### For Translators

1. **Preserve Variables**: Keep all `{variable}` placeholders exactly as they appear in English.

   ```yaml
   # English
   package_installed: "{package} installed successfully"
   
   # Spanish - correct
   package_installed: "{package} instalado correctamente"
   
   # Spanish - WRONG (variable modified)
   package_installed: "{paquete} instalado correctamente"
   ```

2. **Match Tone**: Cortex uses a friendly, professional tone. Maintain this in translations.

3. **Be Concise**: CLI messages should be brief. Avoid overly verbose translations.

4. **Use Native Conventions**: Use the appropriate date/time formats, quotation marks, and punctuation for your language.

5. **Test Your Translations**: Run the CLI with your language to verify translations appear correctly.

### For Developers

1. **Always Use Translation Keys**: Never hardcode user-facing strings.

   ```python
   # Good
   cx_print(t("install.success"), "success")
   
   # Bad
   cx_print("Installation complete!", "success")
   ```

2. **Use Descriptive Keys**: Keys should indicate their purpose.

   ```python
   # Good
   t("install.confirm_install_count", count=5)
   
   # Bad
   t("install.msg1", count=5)
   ```

3. **Document Variables**: Add comments in the YAML for translator reference.

4. **Test with Multiple Languages**: Verify your changes work in all supported languages.

## Testing Translations

### Running Translation Tests

```bash
# Run all i18n tests
pytest tests/test_i18n.py -v

# Run specific test class
pytest tests/test_i18n.py::TestTranslator -v

# Run with coverage
pytest tests/test_i18n.py -v --cov=cortex.i18n --cov-report=term-missing
```

### Checking for Missing Translations

```python
from cortex.i18n.translator import Translator

translator = Translator()

# Get missing keys for a language
missing = translator.get_missing_translations("es")
print(f"Missing Spanish translations: {missing}")
```

### Debug Mode

Enable debug mode to see translation keys in the CLI:

```bash
export CORTEX_I18N_DEBUG=1
cortex install docker
# Shows: [install.analyzing] instead of translated text
```

## CLI Commands

### Quick Language Setting (Human-Readable)

The easiest way to set your language is using the global `--set-language` flag with the language name:

```bash
# Using English names
cortex --set-language English
cortex --set-language Spanish
cortex --set-language French
cortex --set-language German
cortex --set-language Chinese

# Using native names
cortex --set-language Español
cortex --set-language Français
cortex --set-language Deutsch
cortex --set-language 中文

# Using language codes
cortex --set-language es
cortex --set-language zh

# Shorter alias
cortex --language Spanish
```

### View Current Language

```bash
cortex config language
# Output: Current language: English (English)
```

### Set Language (Using Code)

```bash
# Set to Spanish
cortex config language es
# Output: ✓ Idioma cambiado a Español

# Set to German
cortex config language de
# Output: ✓ Sprache geändert zu Deutsch
```

### Use Auto-Detection

```bash
cortex config language auto
# Uses OS language setting
```

### List Available Languages

```bash
cortex config language --list
# Output:
# ━━━ Available languages ━━━
#   en - English (English) ✓
#   es - Spanish (Español)
#   fr - French (Français)
#   de - German (Deutsch)
#   zh - Chinese (中文)
```

### Show Language Info

```bash
cortex config language --info
# Output:
# ━━━ Current language ━━━
#   English (English)
#   Code: en
#   Source: config
```

### Environment Variable Override

```bash
# Override language for a single command
CORTEX_LANGUAGE=fr cortex install docker
# Uses French for this command only
```

## Language Resolution Order

The language is determined in this order:

1. `CORTEX_LANGUAGE` environment variable
2. User preference in `~/.cortex/preferences.yaml`
3. OS-detected language (from `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, `LANG`)
4. Default: English (`en`)

## File Locations

| Item | Location |
|------|----------|
| Message catalogs | `cortex/i18n/locales/*.yaml` |
| User preferences | `~/.cortex/preferences.yaml` |
| i18n module | `cortex/i18n/` |
| Tests | `tests/test_i18n.py` |

## Troubleshooting

### Translation Not Showing

1. Verify the language is set correctly:
   ```bash
   cortex config language --info
   ```

2. Check if the key exists in the catalog:
   ```python
   from cortex.i18n.translator import Translator
   t = Translator(language="es")
   print(t.get_all_keys())
   ```

3. Enable debug mode to see keys:
   ```bash
   CORTEX_I18N_DEBUG=1 cortex install docker
   ```

### Auto-Detection Not Working

Check your OS locale settings:
```bash
echo $LANG $LC_ALL $LANGUAGE
```

Verify the detected language:
```python
from cortex.i18n.detector import get_os_locale_info
print(get_os_locale_info())
```

### Missing Variable in Translation

If you see `{variable}` in output, the translation key exists but interpolation failed. Check:

1. Variable name matches exactly (case-sensitive)
2. The `{}` syntax is correct in the YAML file
3. The variable is passed in code: `t("key", variable=value)`
