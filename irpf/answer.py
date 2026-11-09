# What the baseline and the agent share: the model, the instructions, how retrieved nodes are shown
# to it, and the citation check. An answer cites manual questions as [045]; any number it cites that
# wasn't retrieved or read while answering is dropped from the text, and reported.

import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from llama_index.core.base.llms.types import ChatResponse
from llama_index.core.schema import NodeWithScore
from llama_index.llms.google_genai import GoogleGenAI

from irpf import index

load_dotenv(".env")

LLM_MODEL = "gemini-3.5-flash-lite"
REFUSAL = "Não encontrei isso no Perguntas e Respostas do IRPF 2026."
# [045], and the grouped forms the model also writes: [045, 046], [045; 046], [045 e 046]
CITATION = re.compile(r"\[(\d{3}(?:\s*(?:,|;|e)\s*\d{3})*)\]")

RULES = """Você responde dúvidas sobre a declaração do IRPF 2026 (ano-calendário 2025) usando apenas o "Perguntas e Respostas" da Receita Federal, cujos trechos você recebe.

- Responda em português, de forma direta e curta, com os valores, prazos e condições exatamente como estão no manual.
- Cite as perguntas do manual que sustentam a resposta pelo número, com três dígitos entre colchetes, logo após a frase que elas sustentam: [045]. Cite apenas perguntas cujo texto você recebeu."""

# Not answering from general knowledge: other years, other taxes, cases the manual doesn't cover
REFUSE = f"""Não responda com conhecimento geral, nem sobre outros anos, outros tributos ou casos que o manual não trata. Se o manual não responde a nenhuma parte da pergunta, responda exatamente "{REFUSAL}" e nada mais; se responde só a uma parte, responda a essa parte e diga que o manual não trata da outra."""

SYSTEM = f"""{RULES}
- Responda só com os trechos recebidos. {REFUSE}"""


def llm() -> GoogleGenAI:
    return GoogleGenAI(model=LLM_MODEL, temperature=0)


def tokens(response: ChatResponse) -> int:
    usage = (response.raw or {}).get("usage_metadata") or {}
    return usage.get("total_token_count") or 0


def context(nodes: list[NodeWithScore]) -> str:
    """Retrieved nodes as the model sees them, each headed by the questions it holds"""
    return "\n\n".join(f"--- perguntas {', '.join(f'{n:03d}' for n in index.numbers(r))} ---\n{r.node.text}" for r in nodes)


@dataclass
class Answer:
    text: str
    cited: list[int]  # what the answer cites, after the check
    dropped: list[int]  # what it cited without having retrieved or read it
    refused: bool
    seen: list[int]  # every question retrieved or read while answering
    calls: int = 0  # model calls
    tokens: int = 0
    tools: list[dict] = field(default_factory=list)  # tool calls, in order
    ms: int = 0


def check(text: str, seen: set[int]) -> tuple[str, list[int], list[int]]:
    """The text without citations to questions it never saw, what it cites, and what was dropped"""
    found = [int(n) for group in CITATION.findall(text) for n in re.findall(r"\d{3}", group)]
    dropped = list(dict.fromkeys(n for n in found if n not in seen))
    # Each kept citation in its own brackets, so [045, 999] becomes [045]
    text = CITATION.sub(lambda m: " ".join(f"[{n}]" for n in re.findall(r"\d{3}", m[1]) if int(n) in seen), text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", re.sub(r"[ \t]{2,}", " ", text)).strip()
    return text, list(dict.fromkeys(n for n in found if n in seen)), dropped


def refused(text: str) -> bool:
    return REFUSAL.rstrip(".").lower() in text.lower()


def finish(text: str, seen: list[int], **cost) -> Answer:
    text, cited, dropped = check(text, set(seen))
    return Answer(text=text, cited=cited, dropped=dropped, refused=refused(text), seen=list(dict.fromkeys(seen)), **cost)
