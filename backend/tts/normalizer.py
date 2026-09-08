"""
Ukrainian Text Normalizer for Piper TTS (uk_UA-lada-medium).

uk_UA-lada-medium is a phoneme_type: 'text' model whose phoneme_id_map strictly contains:
- Ukrainian lowercase Cyrillic alphabet (а-я, ґ, є, і, ї, ь)
- Basic punctuation: .,!?:;-— and apostrophe (')
It has NO Latin alphabet characters (a-z) and NO digits (0-9).

This module normalizes arbitrary input text into clean Ukrainian Cyrillic:
1. Expands numbers and decimals (1.5 -> один і п'ять, 2024 -> дві тисячі двадцять чотири).
2. Maps common English technical words & brand names to Ukrainian phonetic equivalents.
3. Transliterates arbitrary Latin words into Ukrainian phonetics.
4. Normalizes symbols (%, $, &, +, =, /).
5. Filters out any characters outside the model's valid phoneme whitelist.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


# Valid characters supported by uk_UA-lada-medium phoneme_id_map
VALID_UK_PHONEMES = set(
    "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя́̆̈—_ ^$!',-.:;? "
)

# Common Tech, Web, AI, and Social Media brand dictionary
TECH_DICTIONARY: Dict[str, str] = {
    # AI & Models
    "gemini": "джеміні",
    "flash": "флеш",
    "pro": "про",
    "ultra": "ультра",
    "chatgpt": "чат джі пі ті",
    "gpt": "джі пі ті",
    "openai": "опен ей ай",
    "claude": "клод",
    "anthropic": "антропік",
    "llama": "лама",
    "deepmind": "діпмайнд",
    "copilot": "копайлот",
    "ai": "ей ай",
    "agi": "ей джі ай",
    "llm": "ел ел ем",
    "tts": "ті ті ес",
    "stt": "ес ті ті",
    "api": "ей пі ай",

    # Platforms & Web
    "reddit": "реддіт",
    "youtube": "ютуб",
    "google": "гугл",
    "apple": "епл",
    "microsoft": "майкрософт",
    "meta": "мета",
    "amazon": "амазон",
    "netflix": "нетфлікс",
    "x": "ікс",
    "twitter": "твіттер",
    "telegram": "телеграм",
    "instagram": "інстаграм",
    "facebook": "фейсбук",
    "tiktok": "тікток",
    "github": "гітхаб",
    "discord": "діскорд",
    "zoom": "зум",
    "slack": "слек",

    # Common spoken video & tech terms
    "mission": "мішн",
    "report": "репорт",
    "live": "лайв",
    "stream": "стрім",
    "podcast": "подкаст",
    "online": "онлайн",
    "offline": "офлайн",
    "update": "апдейт",
    "release": "реліз",
    "version": "версія",
    "feature": "фіча",
    "bug": "баг",
    "fix": "фікс",
    "test": "тест",
    "code": "код",
    "prompt": "промпт",
    "token": "токен",
    "tokens": "токени",
    "benchmark": "бенчмарк",
    "video": "відео",
    "audio": "аудіо",
    "channel": "канал",
    "post": "пост",
    "link": "лінк",
    "click": "клік",

    # Hardware & System
    "cpu": "сі пі ю",
    "gpu": "джі пі ю",
    "ram": "рем",
    "ssd": "ес ес де",
    "usb": "ю ес бі",
    "wifi": "вай фай",
    "wi-fi": "вай фай",
    "bluetooth": "блютуз",
    "windows": "віндовс",
    "linux": "лінукс",
    "macos": "мак ос",
    "android": "андроїд",
    "ios": "ай ос",
    "nvidia": "нвідіа",
    "amd": "а ем де",
    "intel": "інтел",
}

# English multi-character phonetic patterns to Ukrainian
PHONETIC_PAIRS: List[Tuple[str, str]] = [
    (r"tion\b", "шн"),
    (r"sion\b", "жн"),
    (r"ture\b", "чер"),
    (r"tch", "ч"),
    (r"ch", "ч"),
    (r"sh", "ш"),
    (r"th", "т"),
    (r"ph", "ф"),
    (r"kh", "х"),
    (r"gh", "г"),
    (r"zh", "ж"),
    (r"wh", "в"),
    (r"wr", "р"),
    (r"kn", "н"),
    (r"qu", "кв"),
    (r"ck", "к"),
    (r"ee", "і"),
    (r"ea", "і"),
    (r"oo", "у"),
    (r"ou", "ау"),
    (r"ow", "ау"),
    (r"oy", "ой"),
    (r"oi", "ой"),
    (r"ay", "ей"),
    (r"ey", "ей"),
    (r"ai", "ей"),
    (r"ie", "і"),
    (r"c([eiy])", r"с\1"),
    (r"g([eiy])", r"дж\1"),
]

# Single Latin character fallback
SINGLE_LATIN_MAP: Dict[str, str] = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "і", "j": "дж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс",
    "y": "і", "z": "з",
}


def number_to_ukrainian_words(n: int) -> str:
    """Convert an integer (0 to 999,999,999) into Ukrainian words."""
    if n == 0:
        return "нуль"
    if n < 0:
        return f"мінус {number_to_ukrainian_words(abs(n))}"

    units = ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"]
    teens = [
        "десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять",
        "п'ятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять"
    ]
    tens = [
        "", "десять", "двадцять", "тридцять", "сорок",
        "п'ятдесят", "шістдесят", "сімдесят", "вісімдесят", "дев'яносто"
    ]
    hundreds = [
        "", "сто", "двісті", "триста", "чотириста",
        "п'ятсот", "шістсот", "сімсот", "вісімсот", "дев'ятсот"
    ]

    parts: List[str] = []

    # Millions
    if n >= 1_000_000:
        millions = n // 1_000_000
        n %= 1_000_000
        m_last = millions % 10
        m_tens = (millions // 10) % 10
        m_word = number_to_ukrainian_words(millions)
        if m_tens != 1 and m_last == 1:
            parts.append(f"{m_word} мільйон")
        elif m_tens != 1 and 2 <= m_last <= 4:
            parts.append(f"{m_word} мільйони")
        else:
            parts.append(f"{m_word} мільйонів")

    # Thousands
    if n >= 1_000:
        thousands = n // 1_000
        n %= 1_000
        t_last = thousands % 10
        t_tens = (thousands // 10) % 10
        if t_tens != 1 and t_last == 1:
            if thousands == 1:
                parts.append("тисяча")
            else:
                prefix = number_to_ukrainian_words(thousands - 1)
                parts.append(f"{prefix} одна тисяча")
        elif t_tens != 1 and t_last == 2:
            if thousands == 2:
                parts.append("дві тисячі")
            else:
                prefix = number_to_ukrainian_words((thousands // 10) * 10)
                parts.append(f"{prefix} дві тисячі".strip())
        elif t_tens != 1 and 3 <= t_last <= 4:
            parts.append(f"{number_to_ukrainian_words(thousands)} тисячі")
        else:
            parts.append(f"{number_to_ukrainian_words(thousands)} тисяч")

    # Hundreds
    if n >= 100:
        parts.append(hundreds[n // 100])
        n %= 100

    # Teens & Tens & Units
    if 10 <= n <= 19:
        parts.append(teens[n - 10])
    else:
        if n >= 20:
            parts.append(tens[n // 10])
            n %= 10
        if n > 0:
            parts.append(units[n])

    return " ".join(p for p in parts if p)


def transliterate_latin_word(word: str) -> str:
    """Transliterate an English/Latin word to phonetic Ukrainian Cyrillic."""
    clean = word.lower()
    if clean in TECH_DICTIONARY:
        return TECH_DICTIONARY[clean]

    # Apply phonetic digraph substitutions
    for pattern, replacement in PHONETIC_PAIRS:
        clean = re.sub(pattern, replacement, clean)

    # Character-by-character fallback for remaining Latin letters
    res: List[str] = []
    for ch in clean:
        res.append(SINGLE_LATIN_MAP.get(ch, ch))
    return "".join(res)


def expand_numbers_and_symbols(text: str) -> str:
    """Convert digits, decimals, percentages, and currencies to Ukrainian words."""
    # Currency replacements
    text = re.sub(r"\$(\d+([.,]\d+)?)", r"\1 доларів", text)
    text = re.sub(r"€(\d+([.,]\d+)?)", r"\1 євро", text)
    text = re.sub(r"₴(\d+([.,]\d+)?)", r"\1 гривень", text)
    text = re.sub(r"(\d+([.,]\d+)?)\s*%", r"\1 відсотків", text)

    # Decimals: e.g. 1.5, 3.5, 3.6
    def _replace_decimal(match: re.Match) -> str:
        int_part = int(match.group(1))
        dec_part = int(match.group(2))
        return f"{number_to_ukrainian_words(int_part)} і {number_to_ukrainian_words(dec_part)}"

    text = re.sub(r"(\d+)[.,](\d+)", _replace_decimal, text)

    # Standalone integers: e.g. 1, 5, 2024
    def _replace_integer(match: re.Match) -> str:
        num = int(match.group(0))
        return number_to_ukrainian_words(num)

    text = re.sub(r"\b\d+\b", _replace_integer, text)

    # Symbol translations
    symbol_map = {
        "+": " плюс ",
        "=": " дорівнює ",
        "&": " і ",
        "@": " ет ",
        "#": " номер ",
        "/": " або ",
        "\\": " ",
        "*": " ",
        "\"": " ",
        "«": " ",
        "»": " ",
        "(": ", ",
        ")": ", ",
        "[": ", ",
        "]": ", ",
        "{": ", ",
        "}": ", ",
        "~": " приблизно ",
        "<": " менше ",
        ">": " більше ",
    }
    for sym, repl in symbol_map.items():
        if sym in text:
            text = text.replace(sym, repl)

    return text


def normalize_ukrainian_text(text: str) -> str:
    """
    Main entry point to normalize text for Piper Ukrainian TTS (uk_UA-lada-medium).

    Guarantees:
    - All numbers/decimals are expanded into Ukrainian words.
    - All Latin/English words are phonetically transliterated into Ukrainian Cyrillic.
    - All unsupported symbols are replaced or stripped.
    - Only valid phonemes from uk_UA-lada-medium phoneme_id_map remain.
    """
    if not text:
        return ""

    # 1. Expand numbers, currencies, percentages, and symbols
    expanded = expand_numbers_and_symbols(text)

    # 2. Tokenize and transliterate Latin words / brands
    latin_word_pattern = re.compile(r"\b[a-zA-Z0-9_\-']+\b")

    def _replace_latin_token(match: re.Match) -> str:
        token = match.group(0)
        if any("a" <= c <= "z" or "A" <= c <= "Z" for c in token):
            return transliterate_latin_word(token)
        return token

    transliterated = latin_word_pattern.sub(_replace_latin_token, expanded)

    # 3. Lowercase all text for Piper text-type phonemizer
    lowered = transliterated.lower()

    # 4. Strict whitelist filtering against uk_UA-lada-medium phoneme_id_map
    cleaned_chars: List[str] = []
    for char in lowered:
        if char in VALID_UK_PHONEMES:
            cleaned_chars.append(char)
        else:
            cleaned_chars.append(" ")

    result = "".join(cleaned_chars)

    # 5. Clean up redundant spaces and orphan punctuation
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\s+([.,!?:;])", r"\1", result)
    result = re.sub(r"([.,!?:;]){2,}", r"\1", result)

    return result.strip()
