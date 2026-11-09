from irpf import answer


def test_check_keeps_citations_it_saw_and_drops_the_rest():
    text, cited, dropped = answer.check("Sim, pode [045]. O limite é R$ 2.275,08 [046] [999].", {45, 46})
    assert text == "Sim, pode [045]. O limite é R$ 2.275,08 [046]."
    assert cited == [45, 46] and dropped == [999]


def test_check_tidies_the_space_a_dropped_citation_leaves():
    text, cited, dropped = answer.check("Não [012], conforme [013] .", {13})
    assert text == "Não, conforme [013]."
    assert cited == [13] and dropped == [12]


def test_citations_need_three_digits():
    assert answer.check("Veja [45] e [0450].", {45}) == ("Veja [45] e [0450].", [], [])


def test_refusal_is_recognized_in_any_case():
    assert answer.refused("não encontrei isso no Perguntas e Respostas do IRPF 2026")
    assert not answer.refused("Sim [045].")


def test_finish_reports_what_was_seen_once():
    a = answer.finish(answer.REFUSAL, [3, 3, 4], calls=1)
    assert a.refused and a.seen == [3, 4] and a.cited == [] and a.calls == 1


def test_check_splits_grouped_citations():
    text, cited, dropped = answer.check("Não está sujeito [129, 266]. Veja também [012 e 999; 013].", {12, 13, 129, 266})
    assert text == "Não está sujeito [129] [266]. Veja também [012] [013]."
    assert cited == [129, 266, 12, 13] and dropped == [999]
