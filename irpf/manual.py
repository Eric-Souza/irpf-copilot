# The Receita Federal's "Perguntas e Respostas" for the IRPF 2026 (ano-calendário 2025) as one record
# per numbered question: its chapter and topic headings, the question, the answer, the questions it
# points to ("Consulte as perguntas 018, 045 e 252") and the page it starts on.
#
# Usage: uv run python -m irpf.manual   (writes data/questions.jsonl)

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pypdf import PdfReader

PDF = Path("data/pr-irpf-2026.pdf")
OUT = Path("data/questions.jsonl")
FIRST_PAGE = 23  # pages before this are the cover and the table of contents

QUESTION = re.compile(r"^(\d{3})\s*[—–-]\s*(.*)")
SEE = re.compile(r"Consulte (?:a|as) perguntas? ([\d ,e]+)", re.IGNORECASE)
NOISE = re.compile(r"^\s*(\d{1,3}|Retorno ao sum[aá]rio)\s*$", re.IGNORECASE)


@dataclass
class Question:
    number: int
    chapter: str
    topic: str
    question: str
    answer: str
    see: list[int] = field(default_factory=list)
    page: int = 0

    @property
    def text(self) -> str:
        return f"{self.number:03d} — {self.question}\n{self.answer}"


def is_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters) and not QUESTION.match(line)


def clean(text: str) -> str:
    # pypdf splits "ano-calendário" as "ano -calendário" and leaves runs of spaces
    text = re.sub(r" +-(?=\w)", "-", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    # and sometimes splits numbers: "20 26", "202 5", "R$ 3. 561,50", "R$ 5 00,00", "1 6 de março"
    text = re.sub(r"\b20(?: 2(\d)|2 (\d))\b", lambda m: f"202{m[1] or m[2]}", text)
    text = re.sub(r"(\d)\. (\d{3})", r"\1.\2", text)
    text = re.sub(r"(R\$ \d) (\d)", r"\1\2", text)
    text = re.sub(r"\b([1-3]) (\d)(?= de [a-zç]+ de \d{4}|/\d\d/\d{4})", r"\1\2", text)
    return text


def parse(pdf: Path = PDF) -> list[Question]:
    lines: list[tuple[int, str]] = []
    for i, page in enumerate(PdfReader(pdf).pages[FIRST_PAGE - 1 :], start=FIRST_PAGE):
        for j, line in enumerate((page.extract_text() or "").splitlines()):
            # The first line of every page is its number
            if (j == 0 and line.strip().isdigit()) or NOISE.match(line) or not line.strip():
                continue
            lines.append((i, line.rstrip()))

    questions: list[Question] = []
    chapter = topic = ""
    headings: list[str] = []
    current: Question | None = None
    body: list[str] = []
    asking = False

    def close():
        if current is None:
            return
        answer = clean("\n".join(body))
        current.answer = answer
        current.see = sorted({int(n) for m in SEE.finditer(answer) for n in re.findall(r"\d{3}", m.group(1))})
        questions.append(current)

    for page, line in lines:
        m = QUESTION.match(line.strip())
        if m and (not questions or int(m.group(1)) > (current.number if current else 0)):
            close()
            # One heading over a question is its topic; two are a new chapter and its topic
            if len(headings) >= 2:
                chapter, topic = headings[-2], headings[-1]
            elif headings:
                topic = headings[-1]
            headings = []
            current = Question(int(m.group(1)), chapter, topic, m.group(2).strip(), "", page=page)
            body = []
            asking = not current.question.endswith("?")
            continue
        if current and asking:
            current.question = clean(f"{current.question} {line.strip()}")
            asking = not line.strip().endswith("?") and len(current.question) < 600
            continue
        if is_heading(line.strip()):
            headings.append(clean(line))
            continue
        # A heading followed by body text was a word in capitals, not a heading
        if headings:
            body.extend(headings)
            headings = []
        body.append(line)
    close()
    return questions


def load(path: Path = OUT) -> dict[int, Question]:
    """The parsed questions by number"""
    with path.open(encoding="utf-8") as f:
        return {q.number: q for q in (Question(**json.loads(line)) for line in f)}


if __name__ == "__main__":
    qs = parse()
    OUT.write_text("".join(json.dumps(asdict(q), ensure_ascii=False) + "\n" for q in qs), encoding="utf-8")
    numbers = [q.number for q in qs]
    missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
    print(f"{len(qs)} questions, 001 to {max(numbers):03d}, {len(missing)} missing: {missing[:20]}")
    print(f"{len({q.chapter for q in qs})} chapters, {sum(bool(q.see) for q in qs)} questions point to others")
