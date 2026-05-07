"""Workflow settings for the multi-agent design configurator.

Edit the values below to change the system's startup behaviour.
The loader (``agents/loader.py``) reads this module instead of
asking interactive questions, so you don't have to answer the same
prompts every time you launch the app.

Each setting carries a short explanation and the list of valid
values directly above it.  Read the explanation before changing
anything — some toggles trade reliability against token cost, and
the comparison-mode integer is NOT a free-form number.

After editing this file, just run ``python main.py`` as usual.  The
loader prints the loaded settings at startup so you can confirm
what's active.
"""

import os

# ===========================================================
# 1.  Deterministic mesh quality checks
# ===========================================================
# Whether the bound ``render_and_check_mesh`` tool runs the
# watertight / volume / degenerate-face checks on every generated
# mesh.
#
#   True   the tool reports the four metrics alongside the renders
#   False  only the visual renders are produced; QC numbers are
#          skipped and the agents fall back to visual judgement
#          only
#
# Valid values: True, False
MESH_CHECKS: bool = False


# ===========================================================
# 2.  Mesh-check / rendering library
# ===========================================================
# Which library powers the bound ``render_and_check_mesh`` tool's
# metric computations.  Both backends report the same metrics
# (watertight / volume / degenerate-face count); rendering goes
# through the shared pyrender pipeline either way so the three PNG
# outputs are visually identical.
#
#   "trimesh"  trimesh's mesh.is_watertight / area_faces — the
#              original backend, lighter, simpler API
#   "pyvista"  PyVista (VTK) — older battle-tested library; uses
#              VTK's mesh-quality routines for the metrics
#
# Valid values: "trimesh", "pyvista"
RENDER_LIBRARY: str = "trimesh"


# ===========================================================
# 3.  RAG retrieval
# ===========================================================
# Reserved for future RAG (retrieval-augmented generation) over
# prior sessions.  The flag is currently logged but not yet wired
# to any retrieval path — leave at False until RAG is implemented.
#
# Valid values: True, False
RAG_ENABLED: bool = False


# ===========================================================
# 4.  DC Input Inspector
# ===========================================================
# Whether to run the DC Input Inspector between the DC Input
# Creator and the Tool Caller.
#
#   True   inspector validates parameter ranges + consistency
#          before mesh generation; catches more issues at the
#          cost of extra LLM calls and tokens
#   False  parameter set goes straight from DCIC to Tool Caller
#          without validation; cheaper, riskier
#
# Valid values: True, False
DC_INSPECTOR_ENABLED: bool = True


# ===========================================================
# 5.  Orchestrator chain access
# ===========================================================
# Whether the Orchestrator's LLM sees inter-agent messages
# exchanged while it was waiting.
#
#   True   every chain message is prepended to the Orchestrator's
#          next incoming message — diagnostic gold but expensive
#          in tokens
#   False  the Orchestrator only sees the hand-off text it
#          directly receives; the session .log still records
#          every exchange for offline review
#
# Valid values: True, False
CHAIN_ACCESS: bool = True


# ===========================================================
# 6.  Keep loaded images in agent context
# ===========================================================
# What happens to image bytes loaded via load_render_images /
# load_input_images at the end of each agent operation.
#
#   True   image content blocks persist across hand-offs (along
#          with their absolute-path text labels); the agent can
#          reason about the same images on subsequent turns
#          without reloading them
#   False  image bytes are stripped at every operation end and
#          only their absolute-path labels remain in history;
#          much cheaper but agents must re-load images they want
#          to re-inspect
#
# Valid values: True, False
KEEP_IMAGES_IN_CONTEXT: bool = False


# ===========================================================
# 7.  Rate limiter for LLM API calls
# ===========================================================
# Whether to throttle every LLM ``.invoke()`` call through a
# shared token-bucket rate limiter.  Useful on tight per-minute
# budgets — e.g. Anthropic's standard tier on claude-opus-4-x is
# 30,000 input tokens / minute, which a multi-agent dispatcher
# can blow through in the cold-start window before prompt
# caching kicks in.
#
#   True   every llm.invoke() across all 8 agents waits for a
#          token from the shared bucket before issuing the HTTP
#          request; smooths the call rate to fit the budget at
#          the cost of slower sessions
#   False  no throttling; calls fire as fast as the agents
#          produce them (current behaviour)
#
# This is implemented via ``langchain_core.rate_limiters.
# InMemoryRateLimiter`` passed to every ChatAnthropic /
# ChatOpenAI / ChatGoogleGenerativeAI constructor.  One shared
# limiter across all 8 agents enforces a global request-rate
# ceiling, so the per-agent share scales naturally with the
# number of agents currently running.
#
# Valid values: True, False
RATE_LIMIT_ENABLED: bool = True


# ===========================================================
# 8.  Rate-limit budget — requests per second
# ===========================================================
# When RATE_LIMIT_ENABLED is True, this is the steady-state
# call rate the limiter targets across ALL 8 agents combined.
# Only consulted when the limiter is enabled.
#
# Picking a value: estimate your average input tokens per call
# and divide your provider's per-minute token budget by that
# estimate, then divide by 60 to get requests per second.  For
# the Anthropic 30,000 tokens/minute tier with ~3,000-token
# average calls (cold-start dominated): ~10 calls/min ≈ 0.16
# requests/second.  For paid Anthropic tiers or for OpenAI,
# this constant is largely cosmetic.
#
#   0.5   one call every 2 seconds (a reasonable starting point
#         for the Anthropic standard tier when paired with
#         retry/back-off on 429)
#   0.16  ~10 calls per minute — strict, slow, but safest on
#         the 30,000 tokens/min tier without back-off
#
# Valid values: any positive float
RATE_LIMIT_REQUESTS_PER_SECOND: float = 1


# ===========================================================
# 9.  DC Output Inspector — comparison mode
# ===========================================================
# How the DC Output Inspector compares the generated design
# against user expectations.
#
#   1  Compare ONLY with USER INPUTS (user_query.txt + paired
#      reference image(s) and note(s) under inputs/input_images/).
#      Forbids reading extracted_inputs.txt.
#
#   2  Compare ONLY with the UII's EXTRACTED INPUTS (the
#      QUANTITATIVE INPUTS + DESIGN INTENT sections of
#      extracted_inputs.txt).  Forbids loading the user's raw
#      inputs.
#
#   3  Compare PRIMARILY with the extraction; SECONDARILY with
#      the user inputs when the DCOI judges it necessary or the
#      design intent explicitly calls for it.  (Most thorough —
#      recommended default.)
#
# Valid values: 1, 2, 3
DCOI_COMPARISON_MODE: int = 3


# ===========================================================
# 10. Planner / UII order along the standard pipeline
# ===========================================================
# Whether the Planner runs BEFORE the User Input Inspector (the
# original v5 flow) or AFTER it.
#
#   True   Standard v5 flow:
#            user → Receptionist → Orchestrator → Planner → UII
#            → DCIC → [DCII] → TC → DCOI → Orchestrator
#            → Receptionist → user
#          The Planner kicks off, glances at the raw user inputs,
#          decides on a strategy, and hands off to the UII.
#
#   False  UII-first flow:
#            user → Receptionist → Orchestrator → UII → Planner
#            → DCIC → [DCII] → TC → DCOI → Orchestrator
#            → Receptionist → user
#          The UII writes extracted_inputs.txt first; the Planner
#          then reads the structured extraction and (only if it
#          judges necessary) the raw user inputs (texts + notes
#          preferred over images).  Recommended when you want the
#          Planner's strategy to be informed by the structured
#          extraction rather than the raw user text.
#
# Valid values: True, False
PLANNER_FIRST: bool = False


# ===========================================================
# 11. Embedding model (used post-session for RAG indexing)
# ===========================================================
# The embedding model that the (yet-to-be-implemented) RAG layer
# will use to turn the saved per-field SEMANTIC answers under
# ``database/<session>/<agent>/<field>.txt`` into vectors.
#
# The Database Handler (DH) is told these values via its system
# prompt so it can shape SEMANTIC answers to fit the model:
#   * stay below ``EMBEDDING_MAX_RESPONSE_TOKENS`` (preferring
#     <600) when the field's Type is Semantic
#   * apply the embedding-friendly rewrite rules baked into
#     ``agents/database_handler/prompt.md``
# Quantitative answers are NOT capped — they are saved verbatim
# as numerical / structured payloads.
#
# ``EMBEDDING_API_KEY`` is read from environment, never hard-coded
# here.  Set ``OPENAI_API_KEY`` (or change the env var name below)
# in your shell or in a project .env you load before launching.
EMBEDDING_PROVIDER: str = "OpenAI"
EMBEDDING_MODEL: str = "text-embedding-3-large"
EMBEDDING_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# Number of dimensions to request from the embedding model.
# ``text-embedding-3-large`` natively returns 3072-dim vectors but
# supports MRL truncation via the ``dimensions`` argument; 1024
# is the recommended storage default for this corpus.
# Valid values: any positive int the chosen model supports
EMBEDDING_VECTOR_DIMS: int = 1024

# Maximum number of tokens allowed in the SEMANTIC answer the DH
# saves into the corresponding ``.txt`` file.  Counted with the
# ``cl100k_base`` tokenizer (the tokenizer used by
# ``text-embedding-3-large`` and the GPT-4 family).  The DH's
# system prompt instructs it to stay below 600 when feasible.
# Valid values: any positive int (recommended <= 8000, the
# embedding model's per-input limit)
EMBEDDING_MAX_RESPONSE_TOKENS: int = 700
