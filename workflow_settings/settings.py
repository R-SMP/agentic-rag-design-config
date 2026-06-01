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


# ===========================================================
# 12. LLM routing mode
# ===========================================================
# Controlled exclusively via the LLM-routing chart at the top of
# the Workflow Settings web view.  DO NOT EDIT BY HAND.
#
# When the chart's Global LLM dropdown is set to a provider
# (OpenAI / Anthropic / Google), that provider+model from the
# shared ``agents/.env`` is forced for every agent and every
# ``agents/<agent>/.env`` per-agent override is ignored at
# resolution time (the override files are preserved on disk so
# flipping back to "individual" restores prior choices).
#
# When the dropdown is "Use individual LLMs", each agent's
# provider+model is resolved via the original mechanism:
# per-agent ``.env`` first, then shared ``agents/.env``.
#
# Valid values: "individual" | "openai" | "anthropic" | "google"
# Default is OpenAI global override — a fresh checkout (or any
# session that has never written this value) routes every agent
# through OpenAI rather than the per-agent .env files.
LLM_ROUTING_MODE: str = "openai"


# ===========================================================
# 13. Context Pruner — enable
# ===========================================================
# Whether each chain agent runs a pre-invoke check against its own
# accumulated message history and, when over the configured token
# threshold, asks the Context Pruner to summarise the older portion
# into a single SystemMessage before invoking its LLM.
#
#   True   each of the 8 chain agents (Receptionist, Orchestrator,
#          UII, Planner, DCIC, DCII, DCOI, Tool Caller) checks its
#          history before every LLM call.  When over the threshold,
#          everything but the last KEEP_LAST messages is replaced
#          with a single SystemMessage summary.  The LOG-and-Status
#          chart lights up the Context Pruner box while it runs.
#   False  no pruning; agents accumulate their full message history
#          until they hit a provider context-window error.
#
# The Database Handler is intentionally NOT pruned — it iterates ~28
# schedule entries in one save and relies on the accumulated state
# to ask coherent follow-ups.
#
# Valid values: True, False
CONTEXT_PRUNER_ENABLED: bool = True


# ===========================================================
# 14. Context Pruner — token threshold per agent
# ===========================================================
# The cl100k_base token count above which the pre-invoke check fires.
# When the agent's ``self.messages`` count tokens above this number,
# the Pruner is invoked; otherwise the invoke proceeds as today.
#
# Picking a value: stay well below the cheapest provider's window
# (e.g. ~128k for many tiers) with at least 30-50k headroom for the
# next-hop reply.  80,000 is a conservative starting point.
#
# Valid values: any positive int (token count, cl100k_base)
CONTEXT_PRUNER_THRESHOLD_TOKENS: int = 80000


# ===========================================================
# 15. Context Pruner — messages kept verbatim from the tail
# ===========================================================
# Number of recent messages preserved bit-for-bit when the Pruner
# fires.  Older messages are summarised into a single SystemMessage
# at the front of the new history; the last KEEP_LAST messages stay
# as-is so the agent still has its live working context.
#
# The cut point is automatically extended forward to avoid splitting
# an ``AIMessage(tool_calls=...)`` from its matching ``ToolMessage``
# — tool-call pairs are never orphaned, even if that means keeping
# slightly more than ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES`` messages.
#
# Valid values: any positive int (recommended 4-12; 6 covers a
# typical complete turn)
CONTEXT_PRUNER_KEEP_LAST_MESSAGES: int = 6

# Per-message hard cap for the Context Pruner's pre-tier-1 scan.  Any
# single message whose serialised content exceeds this many cl100k_base
# tokens is replaced in-place with a short placeholder (preserving its
# tool_call_id / tool_calls / name fields) BEFORE any summarisation
# pass runs.  Bounded, lossy, but guarantees no tier ever sees a
# giant message — and protects against the failure mode where one
# huge ToolMessage (e.g. an inline .obj mesh dump) exceeds the
# Pruner's own LLM per-call input cap and 429s the whole sequence.
# See the 2026-05-31 incident in v9_gotchas.md (top trap #6).
#
# Valid values: any positive int.  0 disables the pre-scan entirely.
# Default 30000 leaves comfortable headroom for typical tool outputs
# while still catching mesh / vertex / image-dump pathologies.
CONTEXT_PRUNER_MAX_INDIVIDUAL_MESSAGE_TOKENS: int = 30000

# Hard cap for the Context Pruner's TIER-2 LLM input.  When tier 2
# fires, its input is the serialised latest-N tail of the history.
# If that text exceeds this many tokens it is HARD-TRUNCATED before
# being sent to the Pruner's LLM, so the call cannot exceed the
# upstream provider's per-call TPM limit (most providers cap a
# single request at 100k–200k input tokens regardless of overall
# context window).
#
# Valid values: any positive int.  0 disables the cap.  Default
# 60000 leaves headroom for the system prompt + framing on top.
CONTEXT_PRUNER_TIER2_INPUT_CAP_TOKENS: int = 60000


# ===========================================================
# 16. Database Handler — retry budget for chunks INSERT
# ===========================================================
# Maximum number of attempts the Database Handler makes to INSERT a
# Q+A row into the Postgres ``chunks`` table when the insert fails
# (CHECK constraint violation, embedding-pipeline error, transient DB
# error, etc.).  If all attempts are exhausted, the Q+A is written
# to the R2 safety folder for the session and skipped from the
# database — no user data is lost.
#
# Set higher if you see transient errors frequently; set lower if
# you want fast failover to safety storage.  UNIQUE violations are
# treated as "already saved" and do NOT consume a retry — they exit
# the retry loop immediately and are not counted against this cap.
#
# Cascade behaviour: if the failing Q+A is the identifying
# attempt-related question for an attempt, ALL subsequent attempt-
# related questions for that same attempt are routed straight to
# the safety folder (no retries) since the attempt's identity row
# is not in a consistent state.  See
# extra_utilities/db_design/database_and_RAG_architecture.md §3.5.
#
# Example: a Semantic Q+A is generated but the embedding-API call
# is rate-limited.  With DATABASE_ENTRY_MAX_RETRIES = 3, the DH
# retries embed-then-insert up to 3 times.  If still failing on the
# 3rd retry, the raw Q+A goes to ``<session_id>/safety/.../<filename>.txt``
# in R2 and the user data is preserved for later recovery.
#
# Valid values: any positive int (recommended 3–5)
DATABASE_ENTRY_MAX_RETRIES: int = 3


# ===========================================================
# 17. Database Handler — stitching model (Option B embedding input)
# ===========================================================
# Cheap LLM the Database Handler calls to rewrite each Q+A into the
# single coherent prose paragraph that gets fed to the embedding
# model (``text-embedding-3-large``).  The stitched paragraph lives
# in ``chunks.embedding_input``; the resulting vector lives in
# ``chunks.embedding``.  The user-facing text (``chunks.body`` /
# ``chunks.question``) stays untouched by stitching — see
# extra_utilities/db_design/database_and_RAG_architecture.md §6.1.
#
# The rewrite prompt lives at
# ``agents/database_handler/stitching_prompt.md`` and is versioned
# in its own frontmatter.  Treat it like a system prompt.
#
# Provider / model are split so the developer can switch one
# without the other (e.g. keep OpenAI but try a different cheap
# model).  The provider switch is gated on the matching API key
# being present in ``.env``:
#   * OpenAI    → OPENAI_API_KEY
#   * Anthropic → ANTHROPIC_API_KEY
#   * Google    → GOOGLE_API_KEY
# A switch attempt that cannot satisfy the API-key requirement is
# rejected by the workflow-settings editor with a clear error.
#
# Stitching failure (timeout, rate limit, API error) is **not**
# papered over with a fallback string — it consumes a retry attempt
# per DATABASE_ENTRY_MAX_RETRIES, and on exhaustion the Q+A is
# routed to the R2 safety folder.  This keeps the chunks corpus
# uniform (every row has a real LLM-stitched embedding_input).
#
# Cost example: gpt-4o-mini at ~$0.15 / 1M input tokens, ~28 Q+A
# per session at ~300 input tokens each ≈ $0.0001 per session.
#
# Valid values:
#   STITCHING_PROVIDER ∈ {"OpenAI", "Anthropic", "Google"}
#   STITCHING_MODEL    : any model name the chosen provider exposes
STITCHING_PROVIDER: str = "OpenAI"
STITCHING_MODEL: str = "gpt-4o-mini"
