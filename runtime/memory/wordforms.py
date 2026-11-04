"""Light word-form folding for lesson search (Russian, English, Azerbaijani).

Exact token matching treated "тест", "тесты" and "тестов" as three unrelated words, and most
lessons of a Russian-speaking owner are written in Russian. This strips common inflectional
endings so the forms of one word share a key. It is deliberately conservative: only endings,
never prefixes or word roots; short words stay as they are; a stripped key keeps at least
three letters. Missing an unusual form is acceptable (the agent still judges relevance and
can add synonyms); merging unrelated words is not, so derivational suffixes are left alone.
"""

# Longest first, so "ями" wins over "и". Reflexive "ся"/"сь" is removed before these.
_RUSSIAN = sorted((
    "иями", "ями", "ами", "иях", "ях", "ах", "ов", "ев", "ей", "ий", "ый", "ой", "ая", "яя",
    "ое", "ее", "ые", "ие", "ого", "его", "ому", "ему", "ыми", "ими", "ых", "их", "ым", "им",
    "ую", "юю", "ом", "ем", "ам", "ям", "ешь", "ишь", "ете", "ите", "ет", "ит", "ют", "ут",
    "ат", "ят", "ть", "ла", "ло", "ли", "а", "я", "о", "е",
    "ы", "и", "у", "ю", "ь", "й",
), key=len, reverse=True)

# Azerbaijani suffixes. Those without a language-specific letter ("lar", "da", "dan") would
# also cut English words such as "dollar" or "panda", so they apply only to words that
# contain an Azerbaijani-specific letter somewhere.
_AZ_MARKED = sorted((
    "lərin", "ların", "lərdə", "lərdən", "ləri", "ları", "lərə", "lər", "dən", "də", "ın",
    "ün", "ı", "ü", "ə",
), key=len, reverse=True)
_AZ_PLAIN = sorted(("lardan", "larda", "lara", "lar", "dan", "da", "in", "un", "i", "u"),
                   key=len, reverse=True)
_AZ_LETTERS = set("əıöüğşç")

from functools import lru_cache


def _cyrillic(word):
    return any("Ѐ" <= ch <= "ӿ" for ch in word)


@lru_cache(maxsize=65536)
def fold(word):
    """Return the shared key for the forms of `word` (already case-folded)."""
    if len(word) < 5:
        return word
    if _cyrillic(word):
        for reflexive in ("ся", "сь"):
            if word.endswith(reflexive) and len(word) - 2 >= 4:
                word = word[:-2]
                break
        for ending in _RUSSIAN:
            if word.endswith(ending) and len(word) - len(ending) >= 3:
                return word[:-len(ending)]
        return word
    azerbaijani = bool(_AZ_LETTERS & set(word))
    endings = sorted(_AZ_MARKED + (_AZ_PLAIN if azerbaijani else []), key=len, reverse=True)
    for ending in endings:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    if azerbaijani:
        return word
    if word.endswith("ies") and len(word) - 3 >= 3:
        return word[:-3] + "y"
    for ending in ("ing", "ed", "es", "s"):
        if word.endswith(ending) and not word.endswith("ss") and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    return word
