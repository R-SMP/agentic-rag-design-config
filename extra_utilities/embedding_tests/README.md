# Embedding tests

Empirical comparison harness for sketch embedding.  Backs the
**"Embedding tests"** view in the web UI.

## What it tests

| Method | Storage embedding | Text-query path | Image-query path |
|--------|-------------------|------------------|-------------------|
| **Voyage** (joint multimodal) | Voyage `voyage-multimodal-3` on the raw image | Voyage text-encoder → cosine vs image vectors | Voyage image-encoder → cosine vs image vectors |
| **Caption-visual** | OpenAI `text-embedding-3-large/1024` on a VLM-generated *visual-style* description | OpenAI text-emb → cosine | Claude VLM (visual prompt) → OpenAI text-emb → cosine |
| **Caption-semantic** | OpenAI `text-embedding-3-large/1024` on a VLM-generated *semantic-content* description | OpenAI text-emb → cosine | Claude VLM (semantic prompt) → OpenAI text-emb → cosine |

## Files

| File | Role |
|------|------|
| `sketches/` | the 13 test sketches (copied once from `extra_utilities/sketches_examples/`) |
| `embeddings.json` | cached descriptions + vectors per sketch (loaded into memory at server start) |
| `searches.jsonl` | append-only search log (one line per search; powers the live right-side panel) |
| `voyage_client.py` | Voyage multimodal-3 API wrapper |
| `caption_generator.py` | Claude Sonnet VLM caption generator |
| `embedding_tests.py` | core: load, search, rebuild |

## Required env vars

* `VOYAGE_API_KEY` — Voyage AI API key
* `OPENAI_API_KEY` — already required by the main app
* `ANTHROPIC_API_KEY` — already required by the main app

## Rebuilding the index

UI path: open the **Embedding tests** view → **Rebuild index** button at the
bottom.

CLI path:

```
python -m extra_utilities.embedding_tests.embedding_tests rebuild
```

This re-reads every file in `sketches/`, regenerates both descriptions per
sketch via Claude, embeds them via OpenAI + Voyage, and overwrites
`embeddings.json`.

## Scope

NOT a production tool. NOT used by any chain agent. The whole module is
sandboxed behind the `/api/embedding_tests/*` endpoints. Deleting this
folder + reverting the web UI changes restores the system to its previous
state.
