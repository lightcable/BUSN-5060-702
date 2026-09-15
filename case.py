"""
Loader for the project case file (``CASE.md``).

``CASE.md`` is the human-authored blueprint for a run: it states the study
objectives and provides the ``Strategic Question``, ``Attentions``,
``Constraints``, and ``Research Materials`` sections that the agents consume.

Sections are detected by Markdown headings (``##`` .. ``######``). Heading
matching is tolerant: case-insensitive and treating ``_``/spaces as
equivalent, so both ``## Research Materials`` and ``## Research_Materials``
work.
"""

import re
from pathlib import Path

# Canonical section key -> nothing; values are discovered from headings.
_KNOWN = {
    "objectives": "objectives",
    "strategic question": "strategic_question",
    "attentions": "attentions",
    "constraints": "constraints",
    "research materials": "research_materials",
}

_HEADING_RE = re.compile(r"^#{2,6}\s+(.*?)\s*$")


def _canonical(heading):
    """Normalise a heading and map it to a canonical section key."""
    normalized = re.sub(r"\s+", " ", heading.replace("_", " ").strip().lower())
    return _KNOWN.get(normalized)


def load_case(path) -> dict:
    """Read ``path`` and return the case sections as a dict.

    Always returns every known key (empty string when the section or file is
    missing) so callers can use the values unconditionally.
    """
    sections = {key: [] for key in _KNOWN.values()}
    case_path = Path(path)

    if case_path.is_file():
        current = None
        for line in case_path.read_text(encoding="utf-8").splitlines():
            match = _HEADING_RE.match(line)
            if match:
                current = _canonical(match.group(1))
                continue
            if current:
                sections[current].append(line)

    return {key: "\n".join(lines).strip() for key, lines in sections.items()}
