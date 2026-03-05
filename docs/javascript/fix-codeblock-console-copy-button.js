document.addEventListener("DOMContentLoaded", function() {
  fixCopyOnlyUserSelectable();
});

function fixCopyOnlyUserSelectable() {
  var buttonsToFix = document.querySelectorAll(
    '.language-console button.md-code__button');
  if (!buttonsToFix || buttonsToFix.length === 0) {
    return;
  }
  buttonsToFix.forEach((btn) => {
    var clipboardTarget = btn.dataset ? btn.dataset.clipboardTarget : null;
    if (!clipboardTarget) {
      return;
    }
    var content = extractUserSelectable(clipboardTarget);
    if (content !== null && btn.dataset) {
      btn.dataset.clipboardText = content;
    }
  });
}

function extractUserSelectable(selector) {
  var result = '';
  var element = document.querySelector(selector);

  if (!element) {
    return result;
  }

  // Attempt to remove the non-selectable sections based on style,
  // but we haven't seen this work reliably...
  element.childNodes.forEach((child) => {
    if (child instanceof Element) {
      var s=window.getComputedStyle(child);
      if (s.getPropertyValue('user-select') == 'none' ||
        s.getPropertyValue('-webkit-user-select') == 'none' ||
        s.getPropertyValue('-ms-user-select') == 'none')
      {
        return;
      }
    }
    if (child.textContent !== null && child.textContent !== undefined) {
      result += child.textContent;
    }
  });

  // ... so we fall back to simple but effective:
  // remove "$ " and "# " prompt at start of lines in code
  result = result.replace(/^[\s]?[\$#]\s+/gm, "")

  // remove empty lines
  result = result.replace(/^\s*\n/gm, '')
  return result;
}
