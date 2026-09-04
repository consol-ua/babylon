from __future__ import annotations

import re
import time
from typing import List, Optional


class PunctuationSentenceStreamer:
    """
    Buffers streaming text tokens and yields clean clauses or sentences
    segmented by punctuation marks or idle timeouts.
    """

    # Matches punctuation boundaries: .,!?;: or newlines (including repeated marks like ... or ?!)
    BOUNDARY_REGEX = re.compile(r'([.,!?;:]+|\n+)')

    def __init__(self) -> None:
        self._buffer: str = ""
        self._last_token_time: float = time.time()

    @property
    def buffer(self) -> str:
        """Current internal unyielded text buffer."""
        return self._buffer

    @property
    def last_token_time(self) -> float:
        """Timestamp of the most recent token ingestion."""
        return self._last_token_time

    def push(self, text: str) -> List[str]:
        """
        Ingest a streaming text fragment and return any complete clauses or sentences.

        Args:
            text: Incoming text chunk or token.

        Returns:
            List of completed, cleanly formatted sentences/clauses.
        """
        if not text:
            return []

        self._buffer += text
        self._last_token_time = time.time()
        return self._extract_clauses()

    def push_token(self, token: str) -> List[str]:
        """Alias for push."""
        return self.push(token)

    def _extract_clauses(self) -> List[str]:
        """Extract completed clauses from buffer based on punctuation boundaries."""
        clauses: List[str] = []

        while self._buffer:
            pos = 0
            found_boundary = False
            boundary_start = 0
            boundary_end = 0
            boundary_delim = ""

            while True:
                match = self.BOUNDARY_REGEX.search(self._buffer, pos=pos)
                if not match:
                    break

                start, end = match.span()
                delim = match.group(0)

                # Check if this punctuation mark is part of a number (e.g. 3.14 or 1,000)
                if delim in (".", ","):
                    has_digit_before = start > 0 and self._buffer[start - 1].isdigit()
                    has_digit_after = end < len(self._buffer) and self._buffer[end].isdigit()
                    if has_digit_before and has_digit_after:
                        # Delimiter is within a number, skip to next search position
                        pos = end
                        continue

                # Found a valid clause/sentence boundary
                found_boundary = True
                boundary_start = start
                boundary_end = end
                boundary_delim = delim
                break

            if not found_boundary:
                break

            # Determine clause text
            if "\n" in boundary_delim:
                clause = self._buffer[:boundary_start].strip()
            else:
                clause = self._buffer[:boundary_end].strip()

            self._buffer = self._buffer[boundary_end:].lstrip()

            if clause:
                clauses.append(clause)

        return clauses

    def flush_if_idle(
        self,
        max_idle_seconds: float = 0.45,
        min_words: int = 3,
        current_time: Optional[float] = None,
    ) -> Optional[str]:
        """
        Flush accumulated buffer if no tokens have arrived within max_idle_seconds
        and the buffer contains at least min_words.

        Args:
            max_idle_seconds: Inactivity timeout in seconds (default: 0.45).
            min_words: Minimum word threshold to trigger flush (default: 3).
            current_time: Optional explicit timestamp for deterministic testing.

        Returns:
            Flushed text if conditions are met, otherwise None.
        """
        now = current_time if current_time is not None else time.time()
        trimmed = self._buffer.strip()

        if not trimmed:
            return None

        if (now - self._last_token_time) >= max_idle_seconds:
            words = trimmed.split()
            if len(words) >= min_words:
                self._buffer = ""
                return trimmed

        return None

    def flush(self) -> Optional[str]:
        """
        Unconditionally flush and return any pending text in the buffer.

        Returns:
            Flushed text if non-empty, otherwise None.
        """
        trimmed = self._buffer.strip()
        self._buffer = ""
        return trimmed if trimmed else None

    def clear(self) -> None:
        """
        Instantly clear the buffer and reset timing for turn interruption cancellation.
        """
        self._buffer = ""
        self._last_token_time = time.time()
