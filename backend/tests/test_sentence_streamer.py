from __future__ import annotations

import time
import pytest
from tts.sentence_streamer import PunctuationSentenceStreamer


def test_punctuation_splitting():
    """Verify sentences/clauses split accurately on various punctuation marks."""
    streamer = PunctuationSentenceStreamer()

    # Period, comma, exclamation, question mark, semicolon, colon
    text = "Привіт, як справи? Усе чудово! Зачекай; ось деталі: розпочнемо зараз."
    clauses = streamer.push(text)

    assert len(clauses) == 6
    assert clauses[0] == "Привіт,"
    assert clauses[1] == "як справи?"
    assert clauses[2] == "Усе чудово!"
    assert clauses[3] == "Зачекай;"
    assert clauses[4] == "ось деталі:"
    assert clauses[5] == "розпочнемо зараз."
    assert streamer.buffer == ""


def test_boundary_conditions():
    """Verify streamer handles empty pushes, whitespaces, and repeated marks."""
    streamer = PunctuationSentenceStreamer()

    # Empty and whitespace tokens
    assert streamer.push("") == []
    assert streamer.push("   ") == []
    assert streamer.buffer == "   "

    # Push actual text following whitespace
    clauses = streamer.push("Завершено.")
    assert clauses == ["Завершено."]
    assert streamer.buffer == ""

    # Repeated punctuation marks (ellipsis, interrobang)
    clauses = streamer.push("Зачекай... Невже?!")
    assert len(clauses) == 2
    assert clauses[0] == "Зачекай..."
    assert clauses[1] == "Невже?!"
    assert streamer.buffer == ""

    # Newlines
    clauses = streamer.push("Перший рядок\nДругий рядок\n")
    assert len(clauses) == 2
    assert clauses[0] == "Перший рядок"
    assert clauses[1] == "Другий рядок"
    assert streamer.buffer == ""


def test_token_streaming_incremental():
    """Verify streaming token-by-token works with proper buffering until boundary."""
    streamer = PunctuationSentenceStreamer()

    assert streamer.push("Це ") == []
    assert streamer.push("початок ") == []
    assert streamer.push("речення, ") == ["Це початок речення,"]
    assert streamer.buffer == ""

    assert streamer.push("а ") == []
    assert streamer.push("це ") == []
    assert streamer.push("кінець!") == ["а це кінець!"]
    assert streamer.buffer == ""


def test_numbers_handling():
    """Verify decimal numbers and thousand separators are preserved without premature splitting."""
    streamer = PunctuationSentenceStreamer()

    # Decimals with period and comma
    text = "Константа pi приблизно 3.14, а ціна товару 15,50 грн."
    clauses = streamer.push(text)

    assert len(clauses) == 2
    assert clauses[0] == "Константа pi приблизно 3.14,"
    assert clauses[1] == "а ціна товару 15,50 грн."

    # Thousands separator
    text2 = "У компанії 1,000 працівників, або 1,000,000 користувачів."
    clauses2 = streamer.push(text2)
    assert len(clauses2) == 2
    assert clauses2[0] == "У компанії 1,000 працівників,"
    assert clauses2[1] == "або 1,000,000 користувачів."

    # Sentence ending in a number with trailing period
    clauses3 = streamer.push("Він був номером 1.")
    assert clauses3 == ["Він був номером 1."]


def test_idle_timeout_flush():
    """Verify flush_if_idle triggers when idle time exceeds threshold and word count is met."""
    streamer = PunctuationSentenceStreamer()

    # Push 3 words without punctuation
    streamer.push("Один два три")
    base_time = streamer.last_token_time

    # Not enough idle time yet (0.2s < 0.45s)
    flushed = streamer.flush_if_idle(max_idle_seconds=0.45, min_words=3, current_time=base_time + 0.2)
    assert flushed is None
    assert streamer.buffer == "Один два три"

    # Sufficient idle time (0.5s >= 0.45s) and >= 3 words
    flushed = streamer.flush_if_idle(max_idle_seconds=0.45, min_words=3, current_time=base_time + 0.5)
    assert flushed == "Один два три"
    assert streamer.buffer == ""

    # Insufficient words (< 3 words) even if idle
    streamer.push("Два слова")
    flushed_few_words = streamer.flush_if_idle(
        max_idle_seconds=0.45, min_words=3, current_time=time.time() + 1.0
    )
    assert flushed_few_words is None
    assert streamer.buffer == "Два слова"

    # Unconditional flush() flushes any text
    assert streamer.flush() == "Два слова"
    assert streamer.buffer == ""


def test_interruption_clear():
    """Verify clear() instantly discards all pending text on interruption."""
    streamer = PunctuationSentenceStreamer()

    streamer.push("Це важливий фрагмент тексту без крапки")
    assert streamer.buffer != ""

    streamer.clear()
    assert streamer.buffer == ""

    # Next push should start clean
    clauses = streamer.push("Новий виклик!")
    assert clauses == ["Новий виклик!"]
