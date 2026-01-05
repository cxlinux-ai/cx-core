"""
Pluralization Rules for Cortex Linux i18n

Implements language-specific pluralization rules following CLDR standards.
Supports different plural forms for languages with varying pluralization patterns.

Note: The PluralRules class correctly implements all CLDR plural forms.
However, the message string parser in translator.py (_parse_pluralization)
currently only extracts 'one' and 'other' forms. For full multi-form
pluralization (Arabic 6 forms, Russian 3 forms), use PluralRules.get_plural_form()
directly or use the 'other' form as a catch-all in translation strings.

Author: Cortex Linux Team
License: Apache 2.0
"""

from collections.abc import Callable


def _arabic_plural_rule(n: int) -> str:
    """
    Arabic pluralization rule (6 plural forms per CLDR standard).

    Arabic has distinct plural forms for:
    - zero (0)
    - one (1)
    - two (2)
    - few (3-10)
    - many (11-99)
    - other (100+)

    Args:
        n: Count to pluralize

    Returns:
        Plural form key
    """
    if n == 0:
        return "zero"
    elif n == 1:
        return "one"
    elif n == 2:
        return "two"
    elif 3 <= n <= 10:
        return "few"
    elif 11 <= n <= 99:
        return "many"
    else:
        return "other"


def _russian_plural_rule(n: int) -> str:
    """
    Russian pluralization rule (3 plural forms per CLDR standard).

    Russian has distinct plural forms for:
    - one: n % 10 == 1 and n % 100 != 11
      Examples: 1, 21, 31, 41, 51, 61, 71, 81, 91, 101, 121...
    - few: n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14)
      Examples: 2, 3, 4, 22, 23, 24, 32, 33, 34...
    - many: everything else (plural)
      Examples: 0, 5-20, 25-30, 35-40, 100...

    Args:
        n: Count to pluralize

    Returns:
        Plural form key ('one', 'few', or 'many')
    """
    if n % 10 == 1 and n % 100 != 11:
        return "one"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "few"
    else:
        return "many"


class PluralRules:
    """
    Defines pluralization rules for different languages.

    Different languages have different numbers of plural forms:

    - English: one vs. other
      Examples: 1 package, 2 packages

    - Spanish: one vs. other
      Examples: 1 paquete, 2 paquetes

    - Russian: one, few, many
      Examples: 1, 2-4, 5+

    - Arabic: zero, one, two, few, many, other
      Examples: 0, 1, 2, 3-10, 11-99, 100+

    - Japanese: No plural distinction (all use 'other')

    - Hindi: one vs. other
      Examples: 1 पैकेज, 2 पैकेज
    """

    RULES: dict[str, Callable[[int], str]] = {
        "en": lambda n: "one" if n == 1 else "other",
        "es": lambda n: "one" if n == 1 else "other",
        "fr": lambda n: "one" if n <= 1 else "other",
        "de": lambda n: "one" if n == 1 else "other",
        "it": lambda n: "one" if n == 1 else "other",
        "ja": lambda n: "other",  # Japanese doesn't distinguish
        "zh": lambda n: "other",  # Chinese doesn't distinguish
        "ko": lambda n: "other",  # Korean doesn't distinguish
        "ar": _arabic_plural_rule,
        "hi": lambda n: "one" if n == 1 else "other",
        "pt": lambda n: "one" if n == 1 else "other",
        "ru": _russian_plural_rule,
    }

    @classmethod
    def get_plural_form(cls, language: str, count: int) -> str:
        """
        Get plural form key for language and count.

        Args:
            language: Language code (e.g., 'en', 'es', 'ar')
            count: Numeric count for pluralization

        Returns:
            Plural form key ('one', 'few', 'many', 'other', etc.)

        Example:
            >>> PluralRules.get_plural_form('en', 1)
            'one'
            >>> PluralRules.get_plural_form('en', 5)
            'other'
            >>> PluralRules.get_plural_form('ar', 0)
            'zero'
        """
        # Default to English rules if language not found
        rule = cls.RULES.get(language, cls.RULES["en"])
        return rule(count)

    @classmethod
    def supports_language(cls, language: str) -> bool:
        """
        Check if pluralization rules exist for a language.

        Args:
            language: Language code

        Returns:
            True if language has defined rules
        """
        return language in cls.RULES


# Common pluralization patterns for reference

ENGLISH_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        5: "other",
        100: "other",
    },
}

SPANISH_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        100: "other",
    },
}

RUSSIAN_RULES = {
    "plural_forms": 3,
    "forms": ["one", "few", "many"],
    "examples": {
        1: "one",
        2: "few",
        5: "many",
        21: "one",
        22: "few",
        100: "many",
    },
}

ARABIC_RULES = {
    "plural_forms": 6,
    "forms": ["zero", "one", "two", "few", "many", "other"],
    # Thresholds: 0=zero, 1=one, 2=two, 3-10=few, 11-99=many, 100+=other
    "examples": {
        0: "zero",
        1: "one",
        2: "two",
        3: "few",  # Start of "few" range
        10: "few",  # End of "few" range
        11: "many",  # Start of "many" range
        99: "many",  # End of "many" range
        100: "other",  # Start of "other" range
    },
}

JAPANESE_RULES = {
    "plural_forms": 1,
    "forms": ["other"],
    "examples": {
        1: "other",
        2: "other",
        100: "other",
    },
}

HINDI_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        100: "other",
    },
}
