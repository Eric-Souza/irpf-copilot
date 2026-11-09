# The parsed manual (data/questions.jsonl) and the cleanup of pypdf's text. No model.

from llama_index.core.schema import NodeWithScore, TextNode

from irpf import index, manual

QUESTIONS = manual.load()


def test_every_question_is_there_once():
    assert sorted(QUESTIONS) == list(range(1, 746))


def test_every_question_has_a_question_an_answer_and_a_chapter():
    assert all(q.question and q.answer and q.chapter for q in QUESTIONS.values())


def test_cross_references_point_to_questions_that_exist():
    assert all(n in QUESTIONS for q in QUESTIONS.values() for n in q.see)
    assert sum(1 for q in QUESTIONS.values() if q.see) > 100


def test_clean_joins_what_pypdf_splits():
    assert manual.clean("ano -calendário de 20 26") == "ano-calendário de 2026"
    assert manual.clean("limite de R$ 3. 561,50") == "limite de R$ 3.561,50"
    assert manual.clean("até 3 1 de maio de 2026") == "até 31 de maio de 2026"


def test_headings_are_whole_lines_in_capitals():
    assert manual.is_heading("DEPENDENTES") and not manual.is_heading("Dependentes") and not manual.is_heading("045 — QUEM")


def test_question_nodes_keep_the_question_with_every_part():
    nodes = index.question_nodes(QUESTIONS)
    assert {n.metadata["number"] for n in nodes} == set(QUESTIONS)
    long = [n for n in nodes if n.metadata["parts"] > 1]
    assert long and all(n.text.startswith(f"{n.metadata['number']:03d} — ") for n in long)


def test_numbers_reads_both_kinds_of_node():
    assert index.numbers(NodeWithScore(node=TextNode(text="", metadata={"number": 45}))) == [45]
    assert index.numbers(NodeWithScore(node=TextNode(text="", metadata={"numbers": "44 45"}))) == [44, 45]
