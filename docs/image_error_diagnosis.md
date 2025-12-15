## Diagnose Errors from Screenshots

Cortex can diagnose system and installation errors directly from screenshots using Vision AI.

This is useful when error messages cannot be easily copied from terminals or GUI dialogs.

### Image-based diagnosis

Diagnose an error from an image file:

cortex diagnose --image /path/to/error.png

Supported formats:
- PNG
- JPG / JPEG

### Clipboard-based diagnosis

Diagnose an error copied to the clipboard:

cortex diagnose --clipboard

### Fallback behavior

If Vision APIs or required dependencies are unavailable, Cortex provides a safe
fallback diagnosis instead of failing.