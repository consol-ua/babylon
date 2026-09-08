from __future__ import annotations

import pytest
from tts.normalizer import (
    normalize_ukrainian_text,
    number_to_ukrainian_words,
    transliterate_latin_word,
    expand_numbers_and_symbols,
    VALID_UK_PHONEMES,
)
from tts.piper_provider import PiperTTSProvider
from tts.models import VoiceProfile


def test_user_reported_case():
    """Exact string that triggered the missing phoneme cascade in user logs."""
    raw_text = "mission report reddit youtube x gemini 1 5 flash 3 5 flash 3 6 flash"
    normalized = normalize_ukrainian_text(raw_text)

    # Must contain transliterated words and expanded numbers
    assert "мішн" in normalized
    assert "репорт" in normalized
    assert "реддіт" in normalized
    assert "ютуб" in normalized
    assert "джеміні" in normalized
    assert "флеш" in normalized
    assert "один" in normalized
    assert "п'ять" in normalized
    assert "три" in normalized
    assert "шість" in normalized

    # Must have 0 invalid phonemes for uk_UA-lada-medium
    invalid_chars = [ch for ch in normalized if ch not in VALID_UK_PHONEMES]
    assert len(invalid_chars) == 0, f"Found characters outside whitelist: {invalid_chars}"


def test_number_expansion():
    """Test integer and decimal conversion to Ukrainian words."""
    assert number_to_ukrainian_words(0) == "нуль"
    assert number_to_ukrainian_words(1) == "один"
    assert number_to_ukrainian_words(15) == "п'ятнадцять"
    assert number_to_ukrainian_words(42) == "сорок два"
    assert number_to_ukrainian_words(100) == "сто"
    assert number_to_ukrainian_words(2024) == "дві тисячі двадцять чотири"

    # Decimals
    dec_norm = expand_numbers_and_symbols("Версія 1.5 та 3.6")
    assert "один і п'ять" in dec_norm
    assert "три і шість" in dec_norm

    # Currencies & Percentages
    curr_norm = expand_numbers_and_symbols("Ціна $50 або 100% успіху")
    assert "доларів" in curr_norm
    assert "відсотків" in curr_norm


def test_latin_transliteration():
    """Test dictionary and phonetic Latin-to-Cyrillic transliteration."""
    assert transliterate_latin_word("gemini") == "джеміні"
    assert transliterate_latin_word("youtube") == "ютуб"
    assert transliterate_latin_word("reddit") == "реддіт"
    assert transliterate_latin_word("x") == "ікс"

    # Arbitrary English word with phonetic digraphs
    trans = transliterate_latin_word("benchmark")
    assert any("а" <= c <= "я" for c in trans)


def test_whitelist_guarantee():
    """Ensure any arbitrary dirty input is 100% compliant with the Piper phoneme map."""
    dirty_text = 'Test @#$%^&*()_+ 123 "quotes" [brackets] {braces} /slash/ \\backslash\\'
    normalized = normalize_ukrainian_text(dirty_text)

    for ch in normalized:
        assert ch in VALID_UK_PHONEMES, f"Unexpected char: {ch}"


@pytest.mark.asyncio
async def test_piper_with_normalized_english_text():
    """Verify PiperTTSProvider synthesizes without missing phoneme errors on mixed English/numeric text."""
    provider = PiperTTSProvider()
    profile = VoiceProfile(
        id="uk_lada",
        name="Лада",
        language="uk",
        engine_type="builtin",
        model_name="uk_UA-lada-medium",
    )

    text = "Нове відео на YouTube про Gemini 1.5 Flash та Reddit"
    audio = await provider.synthesize(text, profile)

    assert len(audio) > 0
    # Must have real amplitude, not empty silence
    assert max(abs(audio)) > 500
