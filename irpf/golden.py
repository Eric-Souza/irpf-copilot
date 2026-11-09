# The golden set in evals/golden.json: questions written the way a taxpayer asks them, each labeled
# with the manual questions that answer it and a fact a right answer has to state. The facts are
# copied from the manual, and tests/test_golden.py checks they are still there.

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

GOLDEN = Path("evals/golden.json")


@dataclass
class Item:
    id: str
    kind: str  # number, direct, colloquial, multi-hop, out-of-scope
    question: str
    expected: list[int] = field(default_factory=list)
    fact: str | None = None
    # For multi-hop: the question the fact is in, which the first expected one only points to
    hop: int | None = None
    # Other wording of the fact, also copied from an expected question, for answers that quote that instead
    also: list[str] = field(default_factory=list)

    @property
    def facts(self) -> list[str]:
        return [self.fact, *self.also] if self.fact else []

    def stated(self, text: str) -> bool:
        return any(contains(text, f) for f in self.facts)


def load(path: Path = GOLDEN) -> list[Item]:
    return [Item(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def normalize(text: str) -> str:
    # pypdf splits some words ("jul gamento"), so spaces are dropped altogether
    return re.sub(r"\s+", "", text).lower()


def contains(text: str, fact: str) -> bool:
    return normalize(fact) in normalize(text)
