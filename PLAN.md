# IRPF Copilot: plan

An agent that answers questions about the Brazilian income tax return (IRPF 2026) from the Receita Federal's own "Perguntas e Respostas" manual, in Portuguese. Every answer cites the manual's question numbers, follows the manual's "Consulte as perguntas ..." cross-references when one answer isn't enough, and says so when the manual doesn't cover the question. It complements doc-extraction-copilot: that project reads an informe de rendimentos, this one explains what to do with it in the declaração.

## Stack (free)

| Part | Choice |
|---|---|
| Corpus | `P&R IRPF 2026` v1.00 (23/04/2026), 340 pages, parsed with pypdf into 745 questions |
| Framework | LlamaIndex 0.14: ingestion pipeline, `VectorStoreIndex`, Workflows |
| LLM | Gemini 3.5 Flash Lite (free tier) through `llama-index-llms-google-genai` |
| Embeddings | `intfloat/multilingual-e5-base`, locally on CPU. Gemini's free tier allows 1000 embedding requests a day, each text counting as one: less than the 1,925 nodes, before any query. `gemini-embedding-001` stays selectable for a comparison |
| Vector store | Chroma on disk locally, Pinecone serverless (free Starter plan) hosted, same embeddings in both |
| Tracing | Phoenix, locally, through `openinference-instrumentation-llama-index` |
| Tooling | uv, Python 3.12, pytest, GitHub Actions |

LlamaParse (LlamaCloud's free credits) is an optional comparison against the pypdf parser, not a dependency.

## Corpus

The manual is a list of numbered questions (001 to 745) grouped under chapters and topics. Each answer may end with "Consulte a(s) pergunta(s) ...", and 261 of them do. `irpf/manual.py` turns the PDF into `data/questions.jsonl`, one record per question: number, chapter, topic, question, answer, the questions it points to, and its page.

A question is the natural unit: it's how the manual is meant to be read, and it's what an answer should cite. Long answers (the median is 716 characters, the longest 21,647) are split under their question, so a chunk always knows which question it belongs to. Two baselines keep that choice honest: fixed-size chunks over the raw page text, and question-level nodes with no agent.

## Answering

1. A LlamaIndex Workflow retrieves the top questions for the user's question.
2. The model answers from them, or calls a tool:
   - `search_manual(query)`: another retrieval, with a reworded query.
   - `read_question(number)`: the full text of one question, for the cross-references the retrieved ones point to.
3. The answer cites the numbers it used. Code checks that every cited number was actually retrieved or read in this conversation, and drops the citation otherwise.
4. When nothing retrieved covers the question (another tax, another year, legal advice about a specific case), it says so and doesn't answer from general knowledge.

A step limit (4 tool calls) keeps a confused agent from spending the free tier's quota.

## Golden set

Questions written as a taxpayer would ask them, each labeled with the manual questions that answer it and a fact the answer must contain (a limit, a deadline, a yes or no). Every fact is checked by code against the labeled question's text, so a label can't drift from the manual. The mix:

- direct: close to the manual's own wording
- colloquial: the same question the way people ask it ("posso declarar minha mãe como dependente?")
- multi-hop: the answer needs a question the first one points to
- numbers: limits and values (R$ 35.584,00, the deduction per dependent)
- out of scope: questions the manual doesn't answer, which should be refused

## Metrics

Retrieval: hit@5 and MRR on the labeled questions. Answers: fact correct, citations right (cites a labeled question, cites nothing it didn't read), refusals right on out-of-scope questions and wrong on in-scope ones. Cost: model calls, tokens and latency per question. Every run is traced to Phoenix and logged there as an experiment on the golden set, as doc-extraction-copilot does.

## Milestones

1. **Parse** (done): download the manual, parse it into 745 questions with none missing, their chapters, topics and cross-references. Still rough: soft line wraps stay as line breaks, and some chapter headings that wrap across lines are cut short.
2. **Golden set** (done): 69 questions in `evals/golden.json`: 16 on numbers and dates, 10 in the manual's wording, 20 colloquial, 12 multi-hop and 11 out of scope. A test checks that each fact is in a labeled question's text, and for the multi-hop ones that it is only in a question the first one points to, so retrieving the first one alone isn't enough. Building it turned up numbers pypdf had split ("R$ 3. 561,50", "20 26"), which the parser now joins.
3. **Index and baseline RAG** (done): 1,106 question-level nodes (long answers split under their question) and 819 fixed-size page chunks, both in Chroma, with embeddings cached on disk. `irpf/rag.py` answers from the top 5 in one model call, and `irpf/answer.py` checks the citations. Retrieval alone (`python -m evals.retrieval`, top 5 on the 58 answerable questions):

   | Index | hit@1 | hit@5 | MRR@10 | Multi-hop, both questions @5 | Context at 5 |
   |---|---|---|---|---|---|
   | questions | 76% | 97% | 0.84 | 92% | 4,690 chars |
   | pages | 60% | 95% | 0.73 | 75% | 7,054 chars |

   Question-level nodes rank the right question first more often, with a third less context. Two things this changes for the agent: the second question of a multi-hop pair is usually retrieved already (11 of 12), so following cross-references has less to win than expected; and out-of-scope questions score almost as high as answerable ones (median top similarity 0.853 against 0.888), so refusing has to be the model's call, not a threshold's.
4. **Agent** (built, eval pending): the Workflow with `search_manual` and `read_question`, the citation check and refusals. Compared against the baseline on the multi-hop and out-of-scope questions, where it should help, and on cost, where it shouldn't.
5. **Pinecone**: the same nodes and embeddings in a Pinecone serverless index on the free plan, behind the same retriever interface. Same eval, so any difference is the store, plus query latency from here.
6. **Eval and tracing**: `python -m evals.run` over the golden set with cached answers (so reruns cost no quota), a report per run, Phoenix traces and experiments.
7. **Tests, CI and write-up**: pytest for the parser, the citation check and the workflow with a mocked model; GitHub Actions; README with the results; Medium article and LinkedIn project (drafts).
