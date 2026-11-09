# Retrieval: intfloat/multilingual-e5-base in pinecone, top 10

69 golden questions, 58 with an answer in the manual.

| Index | hit@1 | hit@5 | MRR@10 | hit@5 number | hit@5 direct | hit@5 colloquial | hit@5 multi-hop | Multi-hop, second question @5 | Both @5 | Context at 5 (chars) | Median query |
|---|---|---|---|---|---|---|---|---|---|---|---|
| questions | 76% | 97% | 0.84 | 94% | 100% | 95% | 100% | 92% | 92% | 4,690 | 151 ms |
| pages | 60% | 95% | 0.73 | 94% | 100% | 90% | 100% | 75% | 75% | 7,054 | 157 ms |

Median similarity of the top result: questions: 0.881 in scope, 0.841 out of scope; pages: 0.875 in scope, 0.845 out of scope.

## Misses at 5

| Question | Kind | Expected | questions rank | pages rank |
|---|---|---|---|---|
| n02: Qual é o prazo para entregar a declaração do IRPF 2026? | number | 21 | - | 5 |
| n08: Qual é a faixa de isenção da tabela progressiva anual do ano-calendário de 2025? | number | 61 | 1 | - |
| c10: Recebo pensão alimentícia do meu ex. Preciso pagar carnê-leão sobre ela? | colloquial | 223 | - | 4 |
| c14: A restituição que caiu na minha conta ano passado conta como renda? | colloquial | 297 | 1 | - |
| c18: Dá pra receber a restituição pelo PIX? | colloquial | 70 | 5 | 6 |
