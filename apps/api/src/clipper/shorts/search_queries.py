"""Turn a production brief into bounded topic queries without changing the brief."""

import re

_BOILERPLATE = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "beginner",
        "beginners",
        "by",
        "clear",
        "clean",
        "create",
        "describe",
        "end",
        "ending",
        "explain",
        "for",
        "from",
        "generate",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "keep",
        "make",
        "messy",
        "my",
        "of",
        "on",
        "open",
        "opening",
        "original",
        "our",
        "produce",
        "provide",
        "quick",
        "second",
        "seconds",
        "short",
        "shorts",
        "show",
        "showing",
        "start",
        "style",
        "test",
        "that",
        "the",
        "their",
        "then",
        "this",
        "to",
        "turn",
        "turns",
        "use",
        "using",
        "vertical",
        "video",
        "videos",
        "visual",
        "visuals",
        "want",
        "with",
        "write",
        "you",
        "your",
    ]
)


def search_queries(niche: str, prompt: str) -> list[str]:
    # The opening sentence describes the subject; subsequent sentences usually direct production.
    subject = re.split(r"[.!?\n]", prompt, maxsplit=1)[0]
    niche_terms = re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", niche, flags=re.UNICODE)[:6]
    terms = list(niche_terms)
    seen = {word.casefold().rstrip("s") for word in terms}
    topical = []
    for word in re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", subject, flags=re.UNICODE):
        key = word.casefold().rstrip("s")
        if word.casefold() in _BOILERPLATE or word[0].isdigit() or key in seen:
            continue
        seen.add(key)
        topical.append(word)
        if len(topical) == 6:
            break
    focus = [word for word in terms if word.casefold() not in {"tools", "stories", "everyday"}]
    candidates = [" ".join([*terms, *topical]), " ".join([*focus[:2], *topical[:2]]), niche.strip()]
    return list(dict.fromkeys(query[:180].strip() for query in candidates if query.strip()))
