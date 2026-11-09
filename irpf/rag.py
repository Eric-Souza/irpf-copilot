# The baseline: retrieve the top 5 nodes, answer in one model call, check the citations. No tools,
# so a cross-reference the retrieved questions point to stays unread.
#
# Usage: uv run python -m irpf.rag "posso declarar minha mãe como dependente?" [--pages]

import sys
import time

from llama_index.core.llms import ChatMessage

from irpf import answer, index, tracing

K = 5


class RAG:
    def __init__(self, corpus: str = "questions", k: int = K, search=None, llm=None):
        self.search, self.llm = search or index.Search(corpus, k), llm or answer.llm()

    def __call__(self, question: str) -> answer.Answer:
        start = time.perf_counter()
        nodes = self.search(question)
        messages = [
            ChatMessage(role="system", content=answer.SYSTEM),
            ChatMessage(role="user", content=f"Trechos do manual:\n\n{answer.context(nodes)}\n\nPergunta: {question}"),
        ]
        response = self.llm.chat(messages)
        seen = [n for r in nodes for n in index.numbers(r)]
        return answer.finish(response.message.content or "", seen, calls=1, tokens=answer.tokens(response), ms=round((time.perf_counter() - start) * 1000))


if __name__ == "__main__":
    tracing.trace_to_phoenix()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(RAG("pages" if "--pages" in sys.argv else "questions")(" ".join(args)))
