# The Workflow with a scripted model and a fake search: which tools run, what counts as seen, and
# where the step limit stops it. No model, no index.

from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.tools import ToolSelection

from irpf import agent, manual

QUESTIONS = {
    12: manual.Question(12, "Dependentes", "Geral", "Quem pode ser dependente?", "Filhos até 21 anos. Consulte a pergunta 013.", [13]),
    13: manual.Question(13, "Dependentes", "Geral", "E o filho universitário?", "Até 24 anos, se cursando ensino superior."),
}


def node(number: int) -> NodeWithScore:
    return NodeWithScore(node=TextNode(text=QUESTIONS[number].text, metadata={"number": number}), score=0.9)


class Search:
    def __init__(self):
        self.queries = []

    def __call__(self, query: str) -> list[NodeWithScore]:
        self.queries.append(query)
        return [node(12)]


class Model:
    """Answers with the scripted replies in order: a list of tool calls, or the final text"""

    def __init__(self, *replies):
        self.replies, self.with_tools, self.seen = list(replies), [], []

    def _next(self, messages) -> ChatResponse:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, str):
            return ChatResponse(message=ChatMessage(role="assistant", content=reply), raw={"usage_metadata": {"total_token_count": 10}})
        calls = [ToolSelection(tool_id=f"c{i}", tool_name=name, tool_kwargs=args) for i, (name, args) in enumerate(reply)]
        return ChatResponse(message=ChatMessage(role="assistant", content="", additional_kwargs={"tool_calls": calls}), raw={"usage_metadata": {"total_token_count": 10}})

    async def achat_with_tools(self, tools, chat_history, **kwargs):
        self.with_tools.append(True)
        return self._next(chat_history)

    async def achat(self, messages):
        self.with_tools.append(False)
        return self._next(messages)

    def get_tool_calls_from_response(self, response, error_on_no_tool_call=False):
        return response.message.additional_kwargs.get("tool_calls", [])


def make(model: Model) -> tuple[agent.Agent, Search]:
    search = Search()
    return agent.Agent(search=search, llm=model, questions=QUESTIONS), search


def test_answers_straight_from_the_retrieved_questions():
    bot, search = make(Model("Filhos até 21 anos [012]."))
    a = bot.ask("meu filho pode ser dependente?")
    assert a.cited == [12] and a.calls == 1 and a.tools == [] and a.tokens == 10
    assert search.queries == ["meu filho pode ser dependente?"]


def test_reading_a_cross_reference_makes_it_citable():
    bot, _ = make(Model([("read_question", {"number": 13})], "Até 24 anos [013], filhos até 21 [012]."))
    a = bot.ask("e se ele estiver na faculdade?")
    assert a.cited == [13, 12] and a.dropped == [] and a.calls == 2
    assert a.tools == [{"name": "read_question", "args": {"number": 13}}]


def test_a_citation_to_an_unread_question_is_dropped():
    # 013 is only mentioned in 012's "Consulte a pergunta 013", never read
    bot, _ = make(Model("Até 24 anos [013]."))
    a = bot.ask("e se ele estiver na faculdade?")
    assert a.cited == [] and a.dropped == [13] and "[013]" not in a.text


def test_search_manual_adds_what_it_finds():
    bot, search = make(Model([("search_manual", {"query": "dependente filho"})], "Sim [012]."))
    a = bot.ask("filho conta?")
    assert search.queries == ["filho conta?", "dependente filho"] and a.cited == [12]


def test_a_question_that_does_not_exist_is_reported_to_the_model():
    model = Model([("read_question", {"number": 999})], agent.answer.REFUSAL)
    bot, _ = make(model)
    a = bot.ask("o que diz a pergunta 999?")
    assert a.refused and "Não existe a pergunta 999" in model.seen[1][-1].content


def test_the_step_limit_forces_an_answer_without_tools():
    loop = [("search_manual", {"query": "de novo"})]
    model = Model(*[loop] * agent.MAX_TOOL_CALLS, "Sim [012].")
    bot, _ = make(model)
    a = bot.ask("filho conta?")
    assert len(a.tools) == agent.MAX_TOOL_CALLS
    assert model.with_tools == [True] * agent.MAX_TOOL_CALLS + [False]
    assert a.calls == agent.MAX_TOOL_CALLS + 1 and a.cited == [12]


def test_parallel_calls_past_the_limit_are_cut():
    model = Model([("read_question", {"number": 13})] * (agent.MAX_TOOL_CALLS + 2), "Sim [013].")
    bot, _ = make(model)
    a = bot.ask("filho conta?")
    assert len(a.tools) == agent.MAX_TOOL_CALLS and model.with_tools == [True, False]
