from collections import Counter

import pytest

from irpf import golden, manual

QUESTIONS = manual.load()
ITEMS = golden.load()


def test_ids_are_unique():
    assert not [i for i, n in Counter(item.id for item in ITEMS).items() if n > 1]


def test_mix():
    kinds = Counter(item.kind for item in ITEMS)
    assert set(kinds) == {"number", "direct", "colloquial", "multi-hop", "out-of-scope"}
    assert len(ITEMS) >= 60


@pytest.mark.parametrize("item", [i for i in ITEMS if i.kind != "out-of-scope"], ids=lambda i: i.id)
def test_fact_is_in_an_expected_question(item: golden.Item):
    assert item.expected and all(n in QUESTIONS for n in item.expected)
    texts = {n: QUESTIONS[n].text for n in item.expected}
    assert any(golden.contains(t, item.fact) for t in texts.values()), f"{item.fact!r} is in none of {item.expected}"


@pytest.mark.parametrize("item", [i for i in ITEMS if i.kind == "multi-hop"], ids=lambda i: i.id)
def test_multi_hop_needs_the_second_question(item: golden.Item):
    first = QUESTIONS[item.expected[0]]
    assert item.hop in item.expected[1:]
    assert golden.contains(QUESTIONS[item.hop].text, item.fact)
    assert not golden.contains(first.text, item.fact), f"{item.fact!r} is already in {first.number}"
    # The manual itself leads from the first question to the second, maybe through another one
    reachable = set(first.see) | {n for m in first.see for n in QUESTIONS[m].see}
    assert item.hop in reachable


@pytest.mark.parametrize("item", [i for i in ITEMS if i.kind == "out-of-scope"], ids=lambda i: i.id)
def test_out_of_scope_has_no_answer(item: golden.Item):
    assert not item.expected and item.fact is None
