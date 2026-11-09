# The agent: a LlamaIndex Workflow that starts from the same top 5 as the baseline, then may search
# again with other words or read the questions the retrieved ones point to ("Consulte a pergunta
# 045"), up to MAX_TOOL_CALLS, before it answers. The citation check is the same as the baseline's.
#
#   start ──> think ──> (tool calls) ──> act ──> think ... ──> answer
#
# Usage: uv run python -m irpf.agent "posso declarar minha mãe como dependente?"

import asyncio
import sys
import time
from dataclasses import dataclass, field

from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.tools import FunctionTool, ToolSelection
from llama_index.core.workflow import Context, Event, StartEvent, StopEvent, Workflow, step

from irpf import answer, index, manual

K = 5
MAX_TOOL_CALLS = 4
MAX_READ_CHARS = 8000  # the longest answer is 21K characters

INSTRUCTIONS = f"""{answer.RULES}

Você recebe primeiro os trechos que a busca achou para a pergunta, e pode usar as ferramentas, no máximo {MAX_TOOL_CALLS} chamadas, antes de responder:
- read_question(number): o texto completo de uma pergunta do manual. Use quando um trecho remete a outra pergunta ("Consulte a pergunta 045") e alguma parte da dúvida depende dela, quando um trecho está cortado, ou quando a dúvida cita uma pergunta pelo número.
- search_manual(query): uma nova busca, com outras palavras, quando alguma parte da dúvida não aparece nos trechos.
Se os trechos já respondem a todas as partes da dúvida, responda direto. Antes de dizer que o manual não trata de algo, leia as perguntas para as quais os trechos remetem ou busque de novo. {answer.REFUSE}"""


def search_manual(query: str) -> str:
    """Busca no Perguntas e Respostas do IRPF 2026 os trechos mais próximos da consulta, escrita em português."""
    ...


def read_question(number: int) -> str:
    """O texto completo de uma pergunta do Perguntas e Respostas do IRPF 2026, pelo número (1 a 745)."""
    ...


TOOLS = [FunctionTool.from_defaults(fn=search_manual), FunctionTool.from_defaults(fn=read_question)]


@dataclass
class Run:
    messages: list[ChatMessage]
    seen: list[int]
    start: float = field(default_factory=time.perf_counter)
    calls: int = 0
    tokens: int = 0
    tools: list[dict] = field(default_factory=list)


class Think(Event):
    pass


class Act(Event):
    calls: list[ToolSelection]


class Agent(Workflow):
    def __init__(self, corpus: str = "questions", search=None, llm=None, questions=None, **kwargs):
        super().__init__(timeout=180, **kwargs)
        self.search = search or index.Search(corpus, K)
        self.llm = llm or answer.llm()
        self.questions = questions or manual.load()

    @step
    async def start(self, ctx: Context, ev: StartEvent) -> Think:
        nodes = self.search(ev.question)
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=INSTRUCTIONS),
            ChatMessage(role=MessageRole.USER, content=f"Trechos do manual:\n\n{answer.context(nodes)}\n\nPergunta: {ev.question}"),
        ]
        await ctx.store.set("run", Run(messages=messages, seen=[n for r in nodes for n in index.numbers(r)]))
        return Think()

    @step
    async def think(self, ctx: Context, ev: Think) -> Act | StopEvent:
        run: Run = await ctx.store.get("run")
        if len(run.tools) < MAX_TOOL_CALLS:
            response = await self.llm.achat_with_tools(TOOLS, chat_history=run.messages, allow_parallel_tool_calls=True)
            calls = self.llm.get_tool_calls_from_response(response, error_on_no_tool_call=False)
        else:
            run.messages.append(ChatMessage(role=MessageRole.USER, content="Acabaram as chamadas de ferramentas. Responda agora com o que você leu."))
            response, calls = await self.llm.achat(run.messages), []
        run.messages.append(response.message)
        run.calls, run.tokens = run.calls + 1, run.tokens + answer.tokens(response)
        if calls:
            return Act(calls=calls[: MAX_TOOL_CALLS - len(run.tools)])
        ms = round((time.perf_counter() - run.start) * 1000)
        return StopEvent(result=answer.finish(response.message.content or "", run.seen, calls=run.calls, tokens=run.tokens, tools=run.tools, ms=ms))

    @step
    async def act(self, ctx: Context, ev: Act) -> Think:
        run: Run = await ctx.store.get("run")
        for call in ev.calls:
            result = self.call(call, run)
            run.tools.append({"name": call.tool_name, "args": call.tool_kwargs})
            run.messages.append(ChatMessage(role=MessageRole.TOOL, content=result, additional_kwargs={"tool_call_id": call.tool_id, "name": call.tool_name}))
        return Think()

    def call(self, call: ToolSelection, run: Run) -> str:
        args = call.tool_kwargs
        if call.tool_name == "search_manual":
            nodes = self.search(str(args.get("query", "")))
            run.seen += [n for r in nodes for n in index.numbers(r)]
            return answer.context(nodes)
        if call.tool_name == "read_question":
            try:
                q = self.questions[int(args.get("number"))]
            except (KeyError, TypeError, ValueError):
                return f"Não existe a pergunta {args.get('number')!r}; o manual vai de 001 a 745."
            run.seen.append(q.number)
            text = q.text if len(q.text) <= MAX_READ_CHARS else q.text[:MAX_READ_CHARS] + " [...]"
            return f"--- pergunta {q.number:03d} ({q.chapter} / {q.topic}) ---\n{text}"
        return f"Ferramenta desconhecida: {call.tool_name}"

    def ask(self, question: str) -> answer.Answer:
        async def go():
            return await self.run(question=question)

        return asyncio.run(go())


if __name__ == "__main__":
    print(Agent().ask(" ".join(sys.argv[1:])))
