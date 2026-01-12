# Translation Contributor Guide

Welcome! This guide helps you contribute translations to Cortex Linux.

## Quick Start

1. **Choose a language** from the supported list below
2. **Copy the English template**: `cp cortex/translations/en.json cortex/translations/[code].json`
3. **Translate all values** (keep keys unchanged)
4. **Test your translation**:
   ```bash
   cortex --language [code] install nginx --dry-run
   ```
5. **Submit a PR** with your translation file

## Supported Languages

| Code | Language | Status |
|------|----------|--------|
| en | English | Complete ✓ |
| es | Español | Complete ✓ |
| hi | हिन्दी | Complete ✓ |
| ja | 日本語 | Complete ✓ |
| ar | العربية | Complete ✓ |
| de | Deutsch | Complete ✓ |
| it | Italiano | Complete ✓ |
| ko | 한국어 | Complete ✓ |
| ru | Русский | Complete ✓ |
| zh | 中文 | Complete ✓ |
| pt | Português | Complete ✓ |
| fr | Français | Complete ✓ |

## Translation File Structure

Each translation file is a JSON with nested keys for organization:

```json
{
  "namespace": {
    "key": "Translated message",
    "another_key": "Another message"
  }
}
```

### Key Namespaces

- **`common`**: Basic UI terms (yes, no, error, warning, etc.)
- **`cli`**: CLI argument descriptions
- **`install`**: Package installation messages
- **`remove`**: Package removal messages
- **`search`**: Package search messages
- **`config`**: Configuration and preference messages
- **`errors`**: Error messages and codes
- **`prompts`**: User prompts and questions
- **`status`**: Status and information messages
- **`wizard`**: First-run wizard and setup messages
- **`history`**: Installation history display
- **`notifications`**: Notification messages
- **`help`**: Help text and documentation
- **`demo`**: Demo mode messages

## Translation Guidelines

### ✅ DO

- Keep the JSON structure exactly the same as English
- Translate **only the values**, never the keys
- Keep `{variable}` placeholders unchanged
- Maintain punctuation and formatting
- Use natural language appropriate for your target language
- Test with different command combinations
- Use consistent terminology throughout

### ❌ DON'T

- Add or remove keys
- Change the JSON structure
- Translate variable names like `{package}` or `{count}`
- Add extra comments or notes in the JSON file
- Use machine translation without review
- Change formatting or special characters
- Submit incomplete translations

## Variable Interpolation

Messages may contain variables in `{braces}`:

```json
"install": {
  "success": "{package} installed successfully"
}
```

When translated, keep the variable placeholders:

```json
"install": {
  "success": "{package} fue instalado exitosamente"
}
```

The application will replace `{package}` with actual package names at runtime.

## Pluralization

Some messages support pluralization:

```json
"install": {
  "downloading": "Downloading {package_count, plural, one {# package} other {# packages}}"
}
```

The format is: `{variable, plural, one {singular form} other {plural form}}`

Keep this format in translated versions:

```json
"install": {
  "downloading": "Descargando {package_count, plural, one {# paquete} other {# paquetes}}"
}
```

**Important**: Keep the keywords `plural`, `one`, and `other` unchanged.

## Special Cases

### Right-to-Left (RTL) Languages

Arabic needs special handling:
- Text will be automatically formatted by the system
- Don't add RTL markers manually
- Just translate the text normally
- The system handles directional metadata

### Date and Time Formatting

Some messages may include dates/times:
- These are formatted by the system based on locale
- Translate only the label text
- Example: "Installation completed in {time}s" → "Instalación completada en {time}s"

### Currency and Numbers

Numbers are formatted by the system:
- Translate only surrounding text
- Example: "RAM: {ram}GB" → "RAM: {ram}GB" (keep unchanged)

## Testing Your Translation

Before submitting, test these scenarios:

```bash
# Install a package
cortex --language [code] install nginx --dry-run

# Remove a package
cortex --language [code] remove nginx --dry-run

# Search for packages
cortex --language [code] search python

# Show configuration
cortex --language [code] config language

# Show help
cortex --language [code] --help

# Run in wizard mode (if supported)
cortex --language [code] wizard
```

## Common Challenges

### Long Translations

Some UI spaces are limited. Try to keep translations reasonably concise:

❌ Too long: "Please choose which action you would like to perform with the package listed below"
✅ Better: "Select an action:"

### Technical Terms

Some terms are specific to Linux/package management:
- `apt` - keep as is (it's a name)
- `package` - translate if your language has a standard term
- `dependency` - use standard term in your language
- `DRY RUN` - often kept in English or translated to literal equivalent

### Cultural Differences

Consider cultural context:
- Keep formal/informal tone appropriate for your language
- Use standard terminology from your language community
- Respect regional variations (e.g., Spanish: Spain vs Latin America)

## Submission Process

1. **Fork** the repository
2. **Create a branch**: `git checkout -b i18n/[language-code]`
3. **Add your translation file**: `cortex/translations/[code].json`
4. **Commit**: `git commit -m "Add [Language] translation"`
5. **Push**: `git push origin i18n/[language-code]`
6. **Create PR** with title: `[i18n] Add [Language] Translation`

### PR Checklist

- [ ] Translation file is complete
- [ ] All keys from `en.json` are present
- [ ] No extra keys added
- [ ] JSON syntax is valid
- [ ] Tested with `--language [code]` flag
- [ ] Tested multiple commands
- [ ] No hardcoded English text leaks through

## Common Mistakes to Avoid

1. **Modified keys**: Never change key names
   ```json
   // ❌ WRONG
   "instal": { ... }  // Key name changed
   
   // ✅ CORRECT
   "install": { ... }  // Key name unchanged
   ```

2. **Broken variables**:
   ```json
   // ❌ WRONG
   "success": "paquete {package} instalado"  // Lowercase
   "success": "paquete {Package} instalado"  // Wrong case
   
   // ✅ CORRECT
   "success": "paquete {package} instalado"  // Exact match
   ```

3. **Invalid JSON**:
   ```json
   // ❌ WRONG
   "success": "Installation completed"  // Missing comma
   "failed": "Installation failed"
   
   // ✅ CORRECT
   "success": "Installation completed",
   "failed": "Installation failed"
   ```

4. **Extra content**:
   ```json
   // ❌ WRONG
   {
     "install": { ... },
     "translator": "John Doe",  // Extra field
     "notes": "..."  // Extra field
   }
   
   // ✅ CORRECT
   {
     "install": { ... }
   }
   ```

## Language-Specific Tips

### Spanish (es)
- Use formal "usted" unless context suggests informal
- Consider Spain vs Latin American Spanish conventions
- Example: "instalar" (to install) is same, but "programa" vs "software"

### Hindi (hi)
- Use Devanagari script (it's already shown in examples)
- Consider formal vs informal pronouns
- Example: "आप" (formal) vs "तुम" (informal)

### Japanese (ja)
- No pluralization rules needed (Japanese doesn't distinguish)
- Consider casual vs polite forms
- Example: "ください" (polite) vs standard forms

### Arabic (ar)
- Right-to-left language - system handles display
- Consider Modern Standard Arabic vs dialects
- Pluralization follows Arabic CLDR rules

## Getting Help

- **Questions?** Create an issue labeled `[i18n]`
- **Questions about grammar?** Comment in your PR
- **Want to add a new language?** Open an issue first
- **Found a typo in English?** Create a separate issue

## Recognition

Contributors are recognized in:
- Git commit history
- Project CONTRIBUTORS file
- Release notes
- Community channel (#translators Discord)

## Contact

- Discord: [Cortex Linux Community](https://discord.gg/uCqHvxjU83)
- Email: [translations@cortexlinux.com](mailto:translations@cortexlinux.com)
- Issues: [Use label `[i18n]` on GitHub](https://github.com/cortexlinux/cortex/issues?q=label%3Ai18n)

---

Thank you for making Cortex Linux more accessible to speakers around the world! 🌍
