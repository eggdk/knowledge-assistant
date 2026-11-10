"""Split normalized MD/TXT into traceable, bounded text spans.

Character limits are a first experiment, not token limits for a model.
"""

import re
from bisect import bisect_left
from dataclasses import dataclass


CHUNK_STRATEGY_VERSION = "mdtxt-v2"
DEFAULT_MAX_CHARS = 600
DEFAULT_MIN_CHARS = 250
DEFAULT_OVERLAP_CHARS = 80

_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_SENTENCE_END = re.compile(r"[。！？]|[.!?](?=\s)")


def _inside_ascii_word(content: str, position: int) -> bool:
    def word_character(character: str) -> bool:
        return character.isascii() and (character.isalnum() or character == "_")

    return (
        0 < position < len(content)
        and word_character(content[position - 1])
        and word_character(content[position])
    )


@dataclass(frozen=True)
class TextChunk:
    ordinal: int
    text: str
    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    heading: str


def _sections(content: str, suffix: str) -> list[tuple[int, int, str]]:
    if suffix.lower() != ".md":
        return [(0, len(content), "")]

    headings: list[tuple[int, str]] = []
    stack: list[tuple[int, str]] = []
    fence_character: str | None = None
    offset = 0
    for line in content.splitlines(keepends=True):
        fence = _FENCE.match(line)
        if fence:
            character = fence.group(1)[0]
            if fence_character is None:
                fence_character = character
            elif fence_character == character:
                fence_character = None
        elif fence_character is None:
            match = _HEADING.match(line.rstrip("\n"))
            if match:
                level = len(match.group(1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, match.group(2)))
                headings.append((offset, " / ".join(name for _, name in stack)))
        offset += len(line)

    if not headings:
        return [(0, len(content), "")]

    sections: list[tuple[int, int, str]] = []
    if headings[0][0] > 0:
        sections.append((0, headings[0][0], ""))
    for index, (start, heading) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(content)
        sections.append((start, end, heading))
    return sections


def _choose_end(content: str, start: int, ceiling: int, minimum: int) -> int:
    """Prefer a paragraph, then sentence, then line boundary before hard cut."""
    for pattern in (r"\n[ \t]*\n", _SENTENCE_END, r"\n"):
        matches = list(re.finditer(pattern, content[minimum:ceiling]))
        if matches:
            return minimum + matches[-1].end()
    # A hard limit may fall inside Trace, ENOSPC or another identifier.
    # Prefer the start of that word; an over-limit word itself must still split.
    boundary = ceiling
    while boundary > start and _inside_ascii_word(content, boundary):
        boundary -= 1
    if boundary > start:
        return boundary
    return ceiling


def _choose_overlap_start(content: str, start: int, end: int, overlap: int) -> int:
    """Align overlap to a nearby sentence/list line without leaving source gaps."""
    if overlap == 0:
        return end
    target = max(start + 1, end - overlap)
    # A short backward search preserves list items while limiting extra overlap.
    line_lower = max(start + 1, target - overlap // 2)
    line_start = content.rfind("\n", line_lower, target) + 1
    if line_start > start:
        return line_start
    sentence_lower = max(start + 1, target - overlap // 4)
    sentences = list(_SENTENCE_END.finditer(content, sentence_lower, target))
    if sentences:
        return sentences[-1].end()

    lower = max(start + 1, target - overlap)
    boundary = target
    while boundary > lower and _inside_ascii_word(content, boundary):
        boundary -= 1
    if not _inside_ascii_word(content, boundary):
        return boundary
    # No nearby natural boundary: skip to the complete word's end if possible.
    boundary = target
    while boundary < end and _inside_ascii_word(content, boundary):
        boundary += 1
    return boundary if not _inside_ascii_word(content, boundary) else target


def split_text_into_chunks(
    content: str,
    suffix: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    min_chars: int = DEFAULT_MIN_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[TextChunk]:
    """Return exact source slices with line and character offsets.

    Text is expected to have LF newlines, as produced by text_parser.
    """
    if not (0 <= overlap_chars < min_chars <= max_chars):
        raise ValueError("Expected 0 <= overlap_chars < min_chars <= max_chars")
    if suffix.lower() not in {".md", ".txt"}:
        raise ValueError("Chunking supports only MD/TXT")

    newline_offsets = [position for position, character in enumerate(content) if character == "\n"]
    chunks: list[TextChunk] = []
    for section_start, section_end, heading in _sections(content, suffix):
        cursor = section_start
        while cursor < section_end:
            while cursor < section_end and content[cursor].isspace():
                cursor += 1
            if cursor >= section_end:
                break

            ceiling = min(cursor + max_chars, section_end)
            end = (
                section_end
                if ceiling == section_end
                else _choose_end(content, cursor, ceiling, cursor + min_chars)
            )
            while end > cursor and content[end - 1].isspace():
                end -= 1
            if end == cursor:
                raise ValueError("Chunking made no progress")

            chunks.append(
                TextChunk(
                    ordinal=len(chunks) + 1,
                    text=content[cursor:end],
                    start_offset=cursor,
                    end_offset=end,
                    start_line=bisect_left(newline_offsets, cursor) + 1,
                    end_line=bisect_left(newline_offsets, end - 1) + 1,
                    heading=heading,
                )
            )
            if ceiling == section_end:
                break
            cursor = _choose_overlap_start(content, cursor, end, overlap_chars)

    return chunks
