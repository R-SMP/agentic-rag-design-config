"""Embedding tests — empirical sketch-embedding comparison playground.

Self-contained module. Backs the "Embedding tests" web UI view. Compares:

* Joint multimodal embedding (Voyage multimodal-3, image-as-vector)
* Caption-based via VLM-generated descriptions (Claude Sonnet → OpenAI
  text-embedding-3-large)

Two retrieval modes (text-to-image, image-to-image) × three "methods"
(Voyage, caption-visual, caption-semantic). The 13 sketches in
``sketches/`` form the test database; ``embeddings.json`` holds the
cached vectors + descriptions.

NOT a production tool. NOT consumed by any agent. Only the new
``/api/embedding_tests/*`` endpoints in ``web_app.py`` and the
``Embedding tests`` view in ``web/index.html`` reference this module.
"""
