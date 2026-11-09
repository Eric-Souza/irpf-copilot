# Retrieval alone, with no model answering: for each golden question, where the manual questions
# that answer it come back in each index. A page chunk can hold parts of several questions, so it
# counts as a hit for any of them.
#
# Usage: uv run python -m evals.retrieval   (writes evals/results/retrieval.md and .json)

import json
import statistics
from pathlib import Path

from llama_index.core.schema import NodeWithScore, QueryBundle

from irpf import golden, index

K = 10
OUT = Path("evals/results")


def rank(results: list[NodeWithScore], wanted: list[int]) -> int | None:
    """The 1-based rank of the first node that holds one of the wanted questions"""
    return next((i for i, r in enumerate(results, 1) if set(index.numbers(r)) & set(wanted)), None)


def run(corpus: str, items: list[golden.Item], cache: index.EmbeddingCache) -> list[dict]:
    retriever = index.chroma(corpus).as_retriever(similarity_top_k=K)
    vectors = cache.embed([item.question for item in items], kind="query")
    rows = []
    for item, vector in zip(items, vectors):
        results = retriever.retrieve(QueryBundle(query_str=item.question, embedding=vector))
        rows.append(
            {
                "id": item.id,
                "kind": item.kind,
                "rank": rank(results, item.expected) if item.expected else None,
                "hop_rank": rank(results, [item.hop]) if item.hop else None,
                "top_score": results[0].score,
                "retrieved": [index.numbers(r) for r in results],
                "chars": [len(r.node.text) for r in results[:5]],
            }
        )
    return rows


def summary(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["kind"] != "out-of-scope"]
    hit = lambda k, key="rank", rs=scored: sum(1 for r in rs if r[key] and r[key] <= k) / len(rs)
    multi = [r for r in rows if r["kind"] == "multi-hop"]
    return {
        "hit@1": hit(1),
        "hit@5": hit(5),
        "mrr@10": sum(1 / r["rank"] for r in scored if r["rank"]) / len(scored),
        "by_kind": {k: hit(5, rs=[r for r in scored if r["kind"] == k]) for k in dict.fromkeys(r["kind"] for r in scored)},
        "multi_hop_second@5": hit(5, "hop_rank", multi),
        "multi_hop_both@5": sum(1 for r in multi if r["rank"] and r["rank"] <= 5 and r["hop_rank"] and r["hop_rank"] <= 5) / len(multi),
        "top_score_in_scope": statistics.median(r["top_score"] for r in scored),
        "top_score_out_of_scope": statistics.median(r["top_score"] for r in rows if r["kind"] == "out-of-scope"),
        "context_chars@5": statistics.median(sum(r["chars"]) for r in rows),
    }


def main():
    items, cache = golden.load(), index.EmbeddingCache()
    results = {corpus: run(corpus, items, cache) for corpus in index.CORPORA}
    sums = {corpus: summary(rows) for corpus, rows in results.items()}
    pct = lambda x: f"{x * 100:.0f}%"
    kinds = list(next(iter(sums.values()))["by_kind"])
    lines = [
        f"# Retrieval: {index.EMBED_MODEL}, top {K}",
        "",
        f"{len(items)} golden questions, {sum(i.kind != 'out-of-scope' for i in items)} with an answer in the manual.",
        "",
        "| Index | hit@1 | hit@5 | MRR@10 | " + " | ".join(f"hit@5 {k}" for k in kinds) + " | Multi-hop, second question @5 | Both @5 | Context at 5 (chars) |",
        "|---|" + "---|" * (6 + len(kinds)),
        *(
            f"| {c} | {pct(s['hit@1'])} | {pct(s['hit@5'])} | {s['mrr@10']:.2f} | "
            + " | ".join(pct(s["by_kind"][k]) for k in kinds)
            + f" | {pct(s['multi_hop_second@5'])} | {pct(s['multi_hop_both@5'])} | {s['context_chars@5']:,.0f} |"
            for c, s in sums.items()
        ),
        "",
        "Median similarity of the top result: "
        + "; ".join(f"{c}: {s['top_score_in_scope']:.3f} in scope, {s['top_score_out_of_scope']:.3f} out of scope" for c, s in sums.items())
        + ".",
        "",
        "## Misses at 5",
        "",
        "| Question | Kind | Expected | " + " | ".join(f"{c} rank" for c in results) + " |",
        "|---|---|---|" + "---|" * len(results),
    ]
    by_id = {i.id: i for i in items}
    for n, item in enumerate(items):
        ranks = [results[c][n]["rank"] for c in results]
        if item.expected and any(not r or r > 5 for r in ranks):
            lines.append(f"| {item.id}: {item.question} | {item.kind} | {', '.join(map(str, by_id[item.id].expected))} | " + " | ".join(str(r or "-") for r in ranks) + " |")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "retrieval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "retrieval.json").write_text(json.dumps({"summary": sums, "results": results}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
