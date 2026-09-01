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
# Whether the render step of ``generate_and_render_propeller`` runs the
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
# Which library powers the render step of ``generate_and_render_propeller``
# (its metric computations).  Both backends report the same metrics
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
# 2b. Geometry backend — RhinoCompute vs headless FEG
# ===========================================================
# Which engine the AGENT workflow uses to generate the propeller
# mesh it renders and inspects each attempt:
#
#   "feg"    headless Node running the SAME web/feg/* modules the
#            browser 3D preview uses — local, fast, no external
#            server; a visually-faithful sub-mm approximation of
#            the Grasshopper geometry.
#   "rhino"  RhinoCompute + the Grasshopper definition — the exact
#            geometry, but depends on an external server that can be
#            unreachable.
#
# Whichever is chosen, the workflow AUTOMATICALLY falls back to the
# other backend if the first fails, so a RhinoCompute outage no
# longer blocks a run.  The downloadable deliverable is regenerated
# via RhinoCompute regardless of this setting.
#
# Valid values: "feg", "rhino"
GEOMETRY_BACKEND: str = "feg"


# ===========================================================
# 3.  RAG retrieval — master switch for the database_search tool
# ===========================================================
# Global gate for the database_search tool that was implemented
# in Phase 4 (architecture doc §4 + §9.7 + §9.11).
#
#   True   the 8 chain agents (Receptionist, Orchestrator, Planner,
#          UII, DCIC, DCII, DCOI, Tool Caller) get database_search
#          bound at session start AND the $database_search_tool
#          fragment in their system prompts — *subject to* each
#          agent's individual DBa flag in workflow_settings/
#          database_access.json.  Per-agent default is True so all
#          8 are enabled by default.
#
#   False  NO agent gets database_search, regardless of any
#          per-agent DBa flag.  Use this as a kill-switch when you
#          want to run a session without RAG entirely (e.g. for
#          A/B comparison or to debug retrieval-independent
#          behaviour).
#
# Per-agent DBa flags live in workflow_settings/database_access.json
# and are edited via the LLM-routing chart's DBa toggle buttons in
# the Workflow Settings web view.  Changes take effect on the next
# session (settings + per-agent flags are read fresh at session
# build, matching the broader "next session" semantics).
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
# 5b.  Routing retry after a prose-only turn
# ===========================================================
# The six CHAIN agents (Planner, UII, DC Input Creator, DC Input
# Inspector, Tool Caller, DC Output Inspector) must end every turn with
# a ``call_<agent>`` routing tool call -- prose alone is never delivered.
# When one ends in prose instead, the turn used to abort immediately
# with an error hop to the hub: the agent was never told, got no second
# chance, and whatever it had written was demoted to an error string.
# (2026-08-22 test runs: one agent did this seven times in one session,
# roughly tripling the hop count.)
#
#   True   send the agent a one-line reminder and re-invoke it ONCE.
#          If it still does not route, the original error hop is sent
#          exactly as before -- so this can only improve on the old
#          behaviour, never degrade it.
#   False  historic behaviour: abort the turn on the first prose reply.
#
# The Receptionist and the Orchestrator are deliberately NOT covered:
# for them a response with no tool call IS the user-facing reply, not a
# fault.
#
# Valid values: True, False
ROUTING_RETRY_ENABLED: bool = True


# ===========================================================
# 6.  Keep loaded images in agent context
# ===========================================================
# What happens to image bytes loaded via view_images /
# retrieve_user_inputs / retrieve_attempt
# AT THE MOMENT THE AGENT HANDS OFF to another agent (= when
# its LLM invokes a routing tool).  This is the only point at
# which the strip runs — NOT after the LLM reads the image once.
# Within a single agent's run, an image loaded on the first LLM
# call stays available for every subsequent LLM call and every
# subsequent tool call inside that agent's run, all the way
# until the routing tool fires.
#
# IMAGES NEVER CROSS AGENTS, under EITHER value.  ``AgentHop.message``
# is a plain ``str`` and no agent's history is ever seeded from
# another's, so this flag only ever affects the LOADING agent's own
# history.  An agent that wants to inspect an image must load it
# itself either way.  (An earlier version of this comment claimed the
# receiving agent inherits the images; that never matched the code.)
#
#   True   image content blocks persist in that agent's own history
#          after it hands off, so they are still there the next time
#          the SAME agent is activated
#   False  image bytes are stripped the moment the agent hands off
#          (its ``on_operation_end`` hook); only the paired
#          ``Loaded image (path: ...):`` text labels remain.  Within
#          one agent's run the image stays loaded for every LLM call
#
# WHY THIS STAYS False.  The reason is ATTENTION, not cost: an agent
# carrying every image it ever loaded gets worse at using them.  The
# DCOI is the clearest case -- with persistence ON it would hold
# renders from every previous attempt, and its prompt would then have
# to warn it that those images describe PAST designs.  Cost agrees as
# a secondary argument: False costs one cheap text re-write per
# re-activation (flat), while True adds stale image tokens to EVERY
# call and grows with session length (~15 stale composites, ~17k
# tokens, on a 10-attempt run).  Prompt caching does NOT change this
# -- it narrows the gap by billing kept images at 0.1x, but a growing
# cost still loses to a flat one.  See design_prompt_caching.md 7.
#
# It is also a BEHAVIOURAL switch, so it is deliberately global and
# not a per-run setting: varying it inside a benchmark set would make
# the runs non-comparable.
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
# Valid values: "individual" | "openai" | "anthropic" | "google" | "openrouter"
# Default is "individual" — a fresh checkout (or any session
# that has never written this value) honours per-agent .env
# overrides AND the per-agent baked-in defaults in
# ``workflow_settings/llm_defaults.py``.  Switch to a specific
# provider name to force ALL agents through that provider's
# shared default (ignoring per-agent .env files and the per-agent
# baked-in defaults).
LLM_ROUTING_MODE: str = "individual"


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
# The Database Handler is intentionally NOT pruned — it iterates its
# whole schedule in one save and relies on the accumulated state
# to ask coherent follow-ups.
#
# Valid values: True, False
CONTEXT_PRUNER_ENABLED: bool = True


# ===========================================================
# 14. Context Pruner — token threshold per agent
# ===========================================================
# The threshold is derived per agent, from the context window of the model
# THAT agent is running on:
#
#     threshold = max(MIN, min(WINDOW_FRACTION x window, MAX))
#
# and the count it is compared against includes the agent's SYSTEM PROMPT as
# well as its message history — so the number means "total context sent",
# not "history only".  (Before v9 the system prompt sat on top of the
# threshold, so a nominal 80k meant ~95k of real context for the Tool Caller
# and ~110k for the Planner.)
#
# Why both a fraction and a cap: current windows span 200k (Claude Haiku 4.5)
# to 1.05M (gpt-5.4 / gpt-5.5 / gpt-5.6).  A pure fraction would let an agent
# on a 1M model accumulate ~600k tokens of history, which costs far more in
# re-sent context on every turn than pruning would save, long before it is
# ever unsafe.  The CAP therefore governs on large-window models, while the
# FRACTION still binds on small-window ones (200k x 0.60 = 120k).
#
# Windows are resolved by agents/shared/model_windows.py — from the Anthropic
# Models API when reachable, else a static table verified against provider
# docs.  An unrecognised model falls back to the smallest window in use, so
# it prunes early rather than overflowing.
#
# Valid values: fraction 0 < f <= 1; MIN/MAX positive ints (cl100k_base)
CONTEXT_PRUNER_WINDOW_FRACTION: float = 0.60
CONTEXT_PRUNER_MAX_THRESHOLD_TOKENS: int = 150000
CONTEXT_PRUNER_MIN_THRESHOLD_TOKENS: int = 20000

# DEPRECATED (v9): replaced by the three settings above.  Kept so the
# settings UI and any saved profile that still references it keep loading;
# the pruning path no longer reads it.
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
# an ``AIMessage(tool_calls=...)`` from its matching ``ToolMessage``:
# the ToolMessage is pulled back into the summarised part, so a pair is
# never orphaned — even if that means keeping slightly FEWER than
# ``CONTEXT_PRUNER_KEEP_LAST_MESSAGES`` messages verbatim.
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
# 18. User Input Inspector — read previous extracted_inputs.txt?
# ===========================================================
# Whether the User Input Inspector receives the prior turn's
# ``extracted_inputs.txt`` as part of the ``read_user_inputs``
# bundle.
#
#   True   (default) UII sees the previous extraction as one of
#          the files in /app/inputs.  It may consult it for
#          continuity (e.g. "did anything actually change?"), but
#          the prompt forbids copying lines forward — the
#          extraction is always recomputed from ``user_query.txt``
#          + the FIXED-set walk described in the UII prompt's
#          "Temporal scope and Parameters Inputs interface blocks"
#          section.
#   False  the previous ``extracted_inputs.txt`` is FILTERED OUT
#          of the bundle by ``load_user_inputs_bundle``.  The UII
#          never sees it.  Use this when you suspect the UII is
#          accidentally carrying stale state forward despite the
#          prompt rules — a stronger guarantee than relying on the
#          prompt alone.
#
# Default is True so the historical behaviour is preserved on
# upgrade.  Flipping to False is the breaking change.
#
# Valid values: True, False
UII_MAY_READ_PREVIOUS_EXTRACTION: bool = True


# ===========================================================
# 19. Database Search — response token cap
# ===========================================================
# Maximum size (in cl100k_base tokens) of one database_search XML
# response.  When the assembled response exceeds this cap, the
# tool drops anchors from the bottom of the ranking (lowest-
# similarity first) until the result fits, then appends a
# <truncated ... omitted_anchors="K" .../> footer so the calling
# agent knows some content was dropped.  See architecture doc §4.5
# (invariant 3 — never partial-anchor truncation).
#
# Picking a value: 30000 leaves comfortable room for ~5-10 anchors'
# worth of question/answer prose without dominating the agent's
# remaining context window.  Lower the cap if a calling agent's
# downstream context is tight; raise it if you want richer
# multi-anchor responses at the cost of upstream tokens.
#
# Valid values: any positive int (cl100k_base tokens).  Default 30000.
DATABASE_SEARCH_MAX_RESPONSE_TOKENS: int = 30_000


# ===========================================================
# 20. Database Search — candidate pool magnifier
# ===========================================================
# The database_search tool ranks ANCHORS (distinct sessions or
# attempts), not chunks.  To get N anchors back, it first fetches
# DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER × N chunk candidates in
# a single ANN query, then deduplicates by anchor (each anchor's
# best-matching chunk wins) and returns the top N.
#
# Picking a value: 10 is a reasonable balance for our typical corpus
# shape (~120 chunks per saved session).  Lower it if you want
# faster queries and accept under-returning the requested N more
# often when results cluster heavily into one session.  Raise it
# if heavy clustering is producing too many "n_returned < n_requested"
# warnings in rag_queries.  Diminishing returns above ~20 because
# the partial HNSW index is approximate and pulls more nodes when k
# grows.
#
# When the deduplicated anchor count falls short of N (e.g. all
# candidates clustered into 2 sessions when N=5), the tool returns
# what it has and records n_returned < n_requested in rag_queries.
#
# Valid values: any positive int (recommended 5–20).  Default 10.
DATABASE_SEARCH_CANDIDATE_POOL_MAGNIFIER: int = 10


# ===========================================================
# 21. Attempt render views — generate, save AND retrieve
# ===========================================================
# ONE flag per view.  A flag ON means that view's render is:
#   * CREATED at save time if it is missing (from the attempt's
#     parameters.json, using the same tools the live workflow uses);
#   * UPLOADED to R2 with the attempt;
#   * FETCHED when an agent calls retrieve_attempt.
#
# SAVING IS IRREVERSIBLE, RETRIEVAL IS NOT.  A view left OFF is
# unrecoverable for every attempt archived while it was off — turning
# it back ON cannot reach back.  Turning a view OFF is a decision about
# the PERMANENT RECORD, not a display preference.  Turning one ON only
# affects attempts saved from then on.
#
# (These replaced RETRIEVE_ATTEMPT_INCLUDE_<VIEW>_VIEW, whose name became
# misleading once the flag governed saving too.)
#
# Blade sections render from parameters.json ALONE — no mesh needed —
# which is why that one is always attemptable.  The other three come from
# the 3D render core, which writes all three in ONE call, so enabling any
# of them generates the set; the flags then govern upload and retrieval.
#
# Future work: F30 tracks letting the calling agent choose views per-call
# rather than the developer choosing globally.
#
# Valid values: True, False
ATTEMPT_VIEW_ISOMETRIC:      bool = True
ATTEMPT_VIEW_TOP:            bool = True
ATTEMPT_VIEW_BLADE_SECTIONS: bool = True
ATTEMPT_VIEW_SIDE:           bool = False

# Master off-switch for the save-time render-completion pass.  When False,
# attempts are archived with whatever renders they happen to have — the
# behaviour before completion existed.  Turn it off if End Session becomes
# slow; the cost is incomplete archives, permanently.
#
# Valid values: True, False
ATTEMPT_RENDER_COMPLETION_ON_SAVE: bool = True

# Per-attempt budget for that pass.  Completing a 3D view when the mesh is
# absent means invoking the geometry backend inside the save — an external
# call on the one path that must not fail — so it is bounded.  On timeout
# the pass gives up on the remaining renders and the save CONTINUES.
#
# Valid values: any positive int (seconds).  Default 120.
ATTEMPT_RENDER_COMPLETION_TIMEOUT_S: int = 120


# ===========================================================
# 22. Retrieve tools — response token cap
# ===========================================================
# Maximum cl100k_base token count for the XML body returned by
# ``retrieve_user_inputs`` or ``retrieve_attempt``.  Image bytes are
# NOT counted in this cap — they attach as separate content blocks
# and ship as requested via the ``images_flag`` argument.  When the
# assembled XML text exceeds this cap, the tool drops sessions /
# attempts from the END of the requested ID list (lowest priority
# first) and appends a ``<truncated omitted="K"/>`` footer.
#
# Same trim strategy as database_search (see settings block #19).
# Single shared cap covering both retrieve tools is simpler than
# per-tool caps.
#
# Valid values: any positive int (cl100k_base tokens).  Default 30000.
RETRIEVE_MAX_RESPONSE_TOKENS: int = 30_000


# ===========================================================
# 24. OCR — read text written on user-supplied images
# ===========================================================
# When ON, the image tools (``view_images``, ``read_user_inputs``,
# ``retrieve_user_inputs``) additionally run OCR (Google Cloud Vision
# text detection) on each loaded image and append the detected text —
# grouped into callout regions — to the tool's result, so the agent
# gets a clean, quotable reading of any dimension callouts /
# annotations alongside the image itself.  Also exposes the
# ``reread_text_regions`` zoom-in tool.  See
# extra_utilities/docs/reference/OCR_technology_notes.md for the full design.
#
# Requires GOOGLE_CLOUD_VISION_API_KEY in the environment (Railway
# dashboard Variables / local .env).
#
#   OCR_ENABLED              master switch.  False = the OCR pass
#                            never runs, the per-call ``extract_text``
#                            flag + ``reread_text_regions`` tool are
#                            hidden, and
#                            the image tools behave exactly as before.
#                            Validated 2026-06-17 (UII whole-image OCR
#                            + reread_text_regions zoom-in confirmed) → now
#                            default True; set False to disable OCR
#                            everywhere.
#   OCR_ENGINE               which engine backs OCR.  Only
#                            "google_vision" exists today; the value
#                            selects the swappable engine module so a
#                            different one can slot in later.
#   OCR_WHOLE_IMAGE_DEFAULT  default of view_images' per-call
#                            ``extract_text`` flag — whether the agent
#                            gets OCR text unless it opts out on a
#                            given call.
#   OCR_MAX_TEXT_CHARS       cap on the OCR text appended per image so
#                            a dense image cannot blow up context.
#
# Valid values: OCR_ENABLED / OCR_WHOLE_IMAGE_DEFAULT True|False;
# OCR_ENGINE a string; OCR_MAX_TEXT_CHARS a positive int.
OCR_ENABLED: bool = True
OCR_ENGINE: str = "google_vision"
OCR_WHOLE_IMAGE_DEFAULT: bool = True
OCR_MAX_TEXT_CHARS: int = 2000


# ===========================================================
# 25. Blade sections visualizer tool
# ===========================================================
# When ON, the Tool Caller gets the ``render_blade_sections`` tool: it
# takes the path to a parameters JSON file and renders a PNG of the
# three blade cross-sections (Inner / Middle / Outer) stacked
# vertically — the same airfoils the in-browser Parameters Inputs
# "Blade sections" view draws — written under the attempt folder so it
# auto-displays in chat and can be read back by ``view_images``.
# The tool also takes a ``grid`` flag (default False): when True a light
# 1 mm × 1 mm grid is drawn behind the sections.
#
# The whole workflow is told (briefly) that this capability exists, so
# agents can decide to use it; the Tool Caller is the only agent that
# can call it.  This is a NEW capability — turning it OFF makes the
# system behave exactly as before, and the agents are told only that
# the capability exists but is currently OFF (minimal mention).
#
#   BLADE_SECTIONS_VISUALIZER_ENABLED
#       master switch.  True  = the tool is bound to the Tool Caller and
#                               the full prompt fragments are included.
#                       False = the tool is NOT bound; the system works
#                               exactly like before and the prompts carry
#                               only the minimal "exists but OFF" note.
#
# Valid values: True, False
BLADE_SECTIONS_VISUALIZER_ENABLED: bool = True


# DC_PARAMS_PRIMER_ENABLED - the DC-parameter reference diagram.
#
# When ON, the DC-side agents (UII, DCIC, DCII, DCOI - plus Creator and
# Designer in the 5/3-agent systems) receive a fixed reference at every
# LLM call: one image showing how the parameters couple with the design
# (top view + the camber / high-point section grid) with a paired text
# block.  Injected at invoke time between the system prompt and the
# history by agents/shared/dc_primer.py - it is never part of the
# stored conversation, so the image stripper, the Context Pruner and
# the session snapshot never see it.  Costs ~1k tokens per call
# (~383 image + ~600 text), cached as part of the prompt prefix.
#
# CAUTION when OFF is needed: with this ON, DCIC and DCII become VISION
# consumers.  Routing either to a text-only model (e.g. DeepSeek via
# OpenRouter) fails while the primer is enabled - turn it OFF for such
# runs.
#
# Valid values: True, False
DC_PARAMS_PRIMER_ENABLED: bool = True


# UII_PARAMETER_LIST_ENABLED - show the parameter list to the User Input
# Inspector.
#
# The UII records what the USER said, in the user's own words; it does not
# map anything onto configurator parameters (that is the DC Input Creator's
# job).  With this OFF - the default - the "Design Configurator Parameters
# (for reference)" section is stripped from the UII's system prompt, and the
# UII also receives a parameter-free variant of the DC-parameter primer text
# (the reference DIAGRAM is unchanged and still carries labels).
#
# Turn it ON to put the names, units and ranges back in front of the UII,
# e.g. to compare extraction behaviour with and without them.
#
# Valid values: True, False
UII_PARAMETER_LIST_ENABLED: bool = False


# DCOI_KNOWS_PARAMS_RANGES - show allowed ranges to the DC Output Inspector.
#
# The DCOI is given the parameter NAMES and units but, by default, not their
# allowed ranges: judging the render is its job, not validating numbers.
#
# The cost of that is real: without the ranges it cannot tell that a value
# the user asked for is unreachable, so it can recommend moving a parameter
# past a bound that no attempt could ever satisfy (e.g. asking for a 100 mm
# radius when the ring caps at 80).
#
# ON  = the bracketed ranges appear beside each parameter in the DCOI's list,
#       and the prompt says it has the names AND the ranges.
# OFF = as before: names and units only.
#
# Valid values: True, False
DCOI_KNOWS_PARAMS_RANGES: bool = False


# ===========================================================
# 26. Image compression (model-facing images)
# ===========================================================
# Images are billed to the LLM by PIXEL COUNT, not file size, so the only
# lever that lightens an agent's token window is downscaling an image's
# resolution before a model sees it.  The full-resolution original is
# always kept and is what OCR + the embedding pipeline read; only the copy
# sent to a model is downscaled.  The per-image amount is a 0-100
# "compression degree" the user tunes in the Image Inputs view (0 = original
# resolution, 100 = the floor below), stored in a <name>.compression.json
# sidecar beside the image and re-applied when a past image is retrieved.
#
#   IMAGE_COMPRESSION_ENABLED       master switch.  False = images reach
#                                   models at full resolution exactly as
#                                   before (the choke-point passes bytes
#                                   through untouched).
#   IMAGE_COMPRESSION_MIN_LONG_EDGE the long edge (px) reached at 100%
#                                   ("max compression").  Slider floor;
#                                   never upscales.
#   IMAGE_COMPRESSION_DEFAULT_CAP   size-based auto-default: an untuned
#                                   image whose long edge exceeds this is
#                                   compressed down to it; images already
#                                   under it default to 0%.
#   IMAGE_COMPRESSION_CROSS_SECTIONS_DEGREE / _3D_RENDER_DEGREE
#                                   per-render-type compression degree (0-100)
#                                   for the AGENT-facing copy of a render:
#                                   0 = full resolution, 100 = the render floor
#                                   below.  Cross-section diagrams
#                                   (render_blade_sections*) and 3D mesh views
#                                   (render_isometric / _top / _side) are tuned
#                                   SEPARATELY (a 3D view tolerates more
#                                   downscale than a labelled diagram).  Set +
#                                   previewed in the "Render compression" panel
#                                   of the Workflow settings UI.  The saved
#                                   render file is always full-res.
#   IMAGE_COMPRESSION_RENDER_MIN_LONG_EDGE
#                                   the long edge (px) a render reaches at 100%
#                                   degree — a lower floor than user images so
#                                   schematic renders can compress further.
#
# Valid values: IMAGE_COMPRESSION_ENABLED True|False; the sizes positive ints
# (px) with the floors <= DEFAULT_CAP; the two degrees ints in [0, 100].
IMAGE_COMPRESSION_ENABLED: bool = True
IMAGE_COMPRESSION_MIN_LONG_EDGE: int = 512
IMAGE_COMPRESSION_DEFAULT_CAP: int = 1024

# IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE - an ABSOLUTE ceiling on the long edge
# of every MODEL-FACING image, applied whatever the per-image degree says and
# even when IMAGE_COMPRESSION_ENABLED is False.  It is an API constraint, not a
# tuning preference.
#
# Anthropic allows 8000 px per dimension in a SINGLE-image request but only
# 2000 px once a request carries MANY images - and a long agent turn keeps
# accumulating images until it crosses that line.  Run ID291 died there: the
# UII made 18 view_images calls in one turn and the request came back
# "At least one of the image dimensions exceed max allowed size for
# many-image requests: 2000 pixels".
#
# Two paths could exceed it, and this closes both: an image whose sidecar
# stores an explicit degree of 0 ("no downscale" - what the compression slider
# writes at 0%), and a side-by-side composite, which is stitched from panels
# already at the cap and so runs ~3x the cap wide.
#
# 1900 rather than 2000 leaves room for rounding in the resize.  OCR and
# embeddings are unaffected: they read the on-disk original.
#
# Valid values: a positive integer, or 0 to disable the ceiling entirely.
IMAGE_COMPRESSION_HARD_MAX_LONG_EDGE: int = 1900
IMAGE_COMPRESSION_CROSS_SECTIONS_DEGREE: int = 35
IMAGE_COMPRESSION_3D_RENDER_DEGREE: int = 55
IMAGE_COMPRESSION_RENDER_MIN_LONG_EDGE: int = 320


# ===========================================================
# 27. Agent topology
# ===========================================================
# SYSTEM_TOPOLOGY — how many agents the design workflow runs with.
#
# The same job can be done by more agents with narrower roles, or by
# fewer agents each doing more.  The value IS the agent count, and the
# prompts for each variant live in ``agents/<N>agent/`` (the 7-agent
# set is the default and lives at ``agents/<agent>/prompt.md``):
#
#   7  Receptionist, Orchestrator, User Input Inspector, Planner,
#      DC Input Creator, DC Input Inspector, Tool Caller,
#      DC Output Inspector.  The original topology: every role is
#      separate, so each parameter set is authored by one agent and
#      independently audited by another.
#   5  Receptionist, User Input Inspector, CONDUCTOR, CREATOR,
#      Tool Caller, DC Output Inspector.  The Conductor merges the
#      Planner and Orchestrator; the Creator merges the DC Input
#      Creator and DC Input Inspector, authoring the parameters AND
#      self-validating them before writing.  Fewer hand-offs and fewer
#      LLM calls per cycle, but the parameter set is checked by the
#      agent that wrote it — the Tool Caller's independent range check
#      before generating is what compensates.
#
# Changing this takes effect on the NEXT session; a run already in
# flight keeps the topology it started with.
#
# Adding a further variant needs no code change here: create
# ``agents/<N>agent/`` with that variant's prompts and fragments and
# add N to the dropdown.
#
# Valid values: 7, 5, 3
SYSTEM_TOPOLOGY: int = 7


# ===========================================================
# 28. Step budgets - every agent and the dispatcher
# ===========================================================
# How many LLM turns each agent gets, and how many hops the dispatcher
# allows, before the system stops them.  ALL of them live here now so
# they can be retuned from the Workflow Settings UI between queued runs.
# Previously only the merged agents' caps were settings and the twelve
# 7-agent caps were hardcoded in agents/step_caps.py, so a run that died
# overnight needed a code edit and a redeploy to rescue.
#
# WHAT THESE ARE NOT: they are not per-session budgets and they do not
# accumulate.  A *_STEPS cap is spent inside ONE agent.run() call and
# resets every time that agent is activated; a *_VISITS cap and
# MAX_DISPATCH_HOPS reset every user turn.  Nothing here carries across
# turns, let alone across queued overnight sessions.
#
# A cap is a RUNAWAY-LOOP GUARD, not a ration on normal work.  Hitting
# one is not a soft warning: the agent returns an error hop, the
# dispatcher stops, and the Receptionist tells the user the run halted -
# in an unattended overnight queue that is a burnt run found in the
# morning.  So err generous: a cap slightly too high wastes some tokens
# on a stuck model, one slightly too low kills a legitimate design run.
#
# SIZED FROM A REAL RUN (ID237, 5-agent, three-image precision job).
# Observed peaks per activation were UII 10, Creator 5, DCOI 5,
# Conductor 3, Tool Caller 3.  Targets are roughly 3x the observed peak,
# with a floor of 40 for the two VISION agents (UII, DCOI) because image
# reads and OCR dominate their turns and scale with the drawing count.
# The UII is why this pass happened: it used 10 of 10.
#
# Changing any of these takes effect on the next process start.

# MAX_RECEPTIONIST_STEPS - LLM turns inside ONE Receptionist run (validate_input or
# format_outgoing).  It does zero or one utility-tool call and then
# either routes or replies, so 20 is deep headroom; the raise covers
# turns where it inspects several past attempts before answering.
#
# Was 10; raised to 20.
# Valid values: positive int.
MAX_RECEPTIONIST_STEPS: int = 20

# MAX_UII_STEPS - LLM turns inside ONE User Input Inspector run.
#
# RAISED FROM 10 ON EVIDENCE.  In run ID237 the UII used exactly 10 of
# 10 on a three-image task - it routed on its last allowed step, with
# zero margin.  One more image or OCR region and that run would have
# died.  It is vision-bound: every view_images call plus its OCR is a
# turn, and image-heavy jobs are exactly the ones worth running.
#
# Was 10; raised to 40.
# Valid values: positive int.
MAX_UII_STEPS: int = 40

# MAX_PLANNER_STEPS - LLM turns inside ONE Planner run.  Reads the extraction, optionally
# the raw queries, thinks, then routes.  Doubled for recovery turns
# that consult several past attempts before re-planning.
#
# Was 20; raised to 40.
# Valid values: positive int.
MAX_PLANNER_STEPS: int = 40

# MAX_DCIC_STEPS - LLM turns inside ONE DC Input Creator run.  Already generous
# (observed peak 4-5); raised in proportion with the rest so no agent
# becomes the accidental bottleneck of a long precision job.
#
# Was 50; raised to 80.
# Valid values: positive int.
MAX_DCIC_STEPS: int = 80

# MAX_DCII_STEPS - LLM turns inside ONE DC Input Inspector run.  Kept equal to the
# DCIC's: the pair is a writer and checker of the same parameter set,
# and an asymmetry between them has no principled basis.
#
# Was 50; raised to 80.
# Valid values: positive int.
MAX_DCII_STEPS: int = 80

# MAX_TC_STEPS - LLM turns inside ONE Tool Caller run.  Observed peak 3, but a render
# that fails and is retried with adjusted parameters consumes several
# turns, and it is the agent most exposed to tool errors.
#
# Was 15; raised to 40.
# Valid values: positive int.
MAX_TC_STEPS: int = 40

# MAX_DCOI_STEPS - LLM turns inside ONE DC Output Inspector run.
#
# The second vision agent, so it gets the same floor as the UII.  In
# ID237 it made 7 view_images calls across the run, each comparing a
# render against a user sketch; a job with more views to check scales
# that directly.
#
# Was 15; raised to 40.
# Valid values: positive int.
MAX_DCOI_STEPS: int = 40

# MAX_DH_STEPS - LLM turns inside ONE Database Handler run.  The DH interviews agents
# post-session; a stall here costs the session's saved knowledge rather
# than the design, but it is unattended work so headroom is cheap.
#
# Was 10; raised to 20.
# Valid values: positive int.
MAX_DH_STEPS: int = 20

# MAX_DH_TURNS_PER_FIELD - How many LLM turns the DH may spend on ONE schedule field before
# moving on.  Doubled so a field needing several clarifying passes is
# not silently abandoned mid-interview.
#
# Was 6; raised to 12.
# Valid values: positive int.
MAX_DH_TURNS_PER_FIELD: int = 12

# MAX_ORCHESTRATOR_STEPS - How many times the dispatcher may RE-ENTER the Orchestrator during a
# single user turn.  NOT a per-session budget - it resets every turn.
# Doubled because a long precision job re-enters the hub once per
# refine round, and MAX_SECTIONS_REFINE_ROUNDS was raised too.
#
# Was 60; raised to 120.
# Valid values: positive int.
MAX_ORCHESTRATOR_STEPS: int = 120

# MAX_ORCH_INNER_STEPS - LLM turns inside ONE Orchestrator run.  Deliberately the tightest cap
# in the system - the Orchestrator should relay, not deliberate - but 6
# leaves no room to consult an attempt before deciding.  15 keeps the
# intent while removing the cliff.
#
# Was 6; raised to 15.
# Valid values: positive int.
MAX_ORCH_INNER_STEPS: int = 15
# MAX_PLANNER5_STEPS - LLM turns inside ONE run of the 5-agent HUB (the
# Planner acting as Planner + Orchestrator; agents/planner5/).
#
# SEPARATE from MAX_PLANNER_STEPS on purpose.  That one is the 7-agent
# chain Planner, which only plans; this one is the same agent key doing
# both jobs in one loop under topology 5.  Two names so topology 5 can be
# retuned without moving topology 7.
#
# Above the Orchestrator's 15: the Orchestrator was kept tight because it
# should "relay, not deliberate", but here the deliberating half is what
# needs the room.  Same figure the retired Conductor used for the same
# merged role.
#
# Valid values: positive int.
MAX_PLANNER5_STEPS: int = 40

# MAX_PLANNER5_VISITS - how many times the dispatcher may RE-ENTER the
# 5-agent hub during a single user turn.  The MAX_ORCHESTRATOR_STEPS
# analogue for topology 5.
#
# Higher than the Orchestrator's 120 because the hub ABSORBS the Planner:
# in the 7-agent system a planning turn happened inside the Planner and
# cost the hub nothing, whereas here every plan, re-plan and approval is
# itself a re-entry, so identical work consumes more visits.
#
# Raise this FIRST if long precision sessions stop early: it is the cap a
# multi-round refine loop reaches before any other.
#
# Valid values: positive int.
MAX_PLANNER5_VISITS: int = 150

# MAX_DISPATCH_HOPS - Total inter-agent hops allowed in ONE user turn, across all agents.
# The outermost runaway guard: it bounds the whole dispatch loop no
# matter which agents are ping-ponging.  Raised in step with the
# per-agent caps so it stays the LAST thing to trip, not the first.
#
# Was 200; raised to 400.
# Valid values: positive int.
MAX_DISPATCH_HOPS: int = 400

# MAX_SECTIONS_REFINE_ROUNDS - How many refine rounds the precision section-matching loop may run
# before the hub must finalise.
#
# NOTE, because this one differs in kind: the others are runaway
# guards, but this bounds how hard the system TRIES.  Raising it changes
# what the system does, not merely when it gives up, so a precision
# benchmark run at 12 is not directly comparable with one run at 8.
# ID237 converged in 3 sections rounds + 1 3D round, well inside either
# figure.  Keep it FIXED across any runs you intend to compare.
#
# Was 8; raised to 12.
# Valid values: positive int.
MAX_SECTIONS_REFINE_ROUNDS: int = 12

# MAX_ARCHITECT_STEPS - LLM turns allowed inside ONE Architect.run()
# invocation (3-agent topology).
#
# The Architect merges THREE agents: the UII (perceive - reads images,
# runs OCR, writes the extraction), the Planner (plan) and the
# Orchestrator (route/approve).  Its first turn of a design job is the
# expensive one: image reads dominate, and in a live 5-agent run the
# UII alone took 10 LLM calls on a three-image task.  Set above the
# Conductor's 20 to cover that perception pass on top of planning.
#
# Valid values: positive int.
MAX_ARCHITECT_STEPS: int = 60

# MAX_ARCHITECT_VISITS - how many times the dispatcher may RE-ENTER the
# Architect during a single user turn (3-agent topology).
#
# The MAX_PLANNER5_VISITS analogue.  Same value: absorbing perception
# adds work INSIDE one visit rather than adding visits - the extraction
# is written once per turn, not once per cycle.
#
# Valid values: positive int.
MAX_ARCHITECT_VISITS: int = 150

# MAX_DESIGNER_STEPS - LLM turns allowed inside ONE Designer.run()
# invocation (3-agent topology).
#
# The Designer merges the DC Input Creator (author) and the Tool Caller
# (generate + render), and DROPS validation entirely - that is the
# strip-down.  So it needs the DCIC's authoring budget plus the Tool
# Caller's tool calls, but NOT the Creator's self-validation pass.
# Hence a smaller budget than a create-plus-validate agent would need,
# despite merging one more agent.
#
# Valid values: positive int.
MAX_DESIGNER_STEPS: int = 85

# MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT - how many consecutive
# Designer <-> Critic rounds may run before the dispatcher FORCES the next
# hop to the Architect (3-agent topology only).
#
# In the 3-agent system the Critic refines directly with the Designer
# rather than returning to the hub every round, so the brain is not in the
# loop by default.  It is called for three things: an escalation, a
# phase change (e.g. "the sections now match, move to full 3D"), and
# periodically - to see what several rounds of refinement have actually
# achieved.  The Critic's prompt tells it when a checkpoint is worthwhile;
# this is the HARD BACKSTOP for when it does not, so the Architect can
# never be shut out of a long loop by a model that keeps deciding to
# iterate once more.
#
# Distinct from MAX_SECTIONS_REFINE_ROUNDS, which is unchanged and still
# means the same thing in every topology: this is a REPORTING CADENCE,
# that is the per-phase STOPPING CEILING.
#
# Default 3: run ID237's sections phase converged in 3 rounds, so a
# checkpoint at 3 surfaces intermediate progress on anything slower than
# that without interrupting a phase that is converging normally.
#
# Valid values: positive int.
MAX_ROUNDS_BEFORE_ARCHITECT_CHECKPOINT: int = 3

# ===========================================================
# 29. Prompt caching (Anthropic only)
# ===========================================================
# Anthropic prompt caching stores the model's precomputed state for
# a prompt PREFIX, keyed by a hash of that prefix's exact tokens.  A
# later request whose prompt STARTS with the same tokens reads that
# state back at ~0.1x the normal input price instead of re-paying
# full price for it.  See extra_utilities/docs/reference/design_prompt_caching.md
# for the full mechanics (breakpoints, the 20-block lookback, TTL
# economics and the measured behaviour of this system).
#
# TWO ORTHOGONAL KNOBS.  Scope decides WHAT gets a cache breakpoint;
# TTL decides HOW LONG entries live.  They are separate because a
# system-only cache still has a lifetime.
#
#   PROMPT_CACHE_SCOPE
#     "off"             no cache_control is emitted at all; every
#                       call pays full price for the whole prompt.
#     "system"          only the agent's system prompt is cached
#                       (one explicit breakpoint).  This was the
#                       behaviour before scope became configurable.
#     "system+history"  as "system", PLUS Anthropic's top-level
#                       automatic breakpoint, which advances with the
#                       growing conversation so the history is read
#                       back at cache-read price instead of being
#                       re-billed in full on every call.
#
#   PROMPT_CACHE_TTL    lifetime of every entry; ignored when the
#                       scope is "off".  The TTL refreshes for free
#                       on each hit, so a continuously-used entry
#                       stays alive.
#     "5m"              5 minutes.  Cache writes cost 1.25x.
#     "1h"              1 hour.  Writes cost 2x, but nothing expires
#                       mid-session — measured revisit gaps show the
#                       Receptionist exceeds 5 min in every session
#                       and the Planner in most.
#
# ONE TTL FEEDS BOTH BREAKPOINTS.  Anthropic returns a 400 if the
# automatic breakpoint lands on a block that already carries an
# explicit cache_control with a DIFFERENT ttl, so both markers are
# built from this single value and cannot diverge.
#
# ANTHROPIC ONLY.  Other providers never receive these fields:
# OpenAI caches automatically with no API surface, and Google /
# OpenRouter expose no equivalent.  On a non-Anthropic run both
# settings are silently inert.
#
# WHY THE DEFAULT IS "5m" AND NOT "1h".  The measured analysis in
# design_prompt_caching.md §6 concludes 1h is the cheaper choice OVERALL,
# because a single expiry re-writes a whole accumulated prefix while the
# 1h premium applies only to deltas.  "5m" still ships as the Step-1
# default deliberately: the agents that actually exceed 5 minutes are the
# Receptionist and the Planner, and those two carry SMALL histories, so
# their expiries are cheap — while the expensive tight-loop agents (DCIC,
# DCOI, UII, Tool Caller, DCII) revisit every 70–160 s and never expire,
# so they get the cheaper 1.25x write. Flip to "1h" once a live A/B has
# measured the real numbers.
#
# Valid values: PROMPT_CACHE_SCOPE "off"|"system"|"system+history";
# PROMPT_CACHE_TTL "5m"|"1h".
PROMPT_CACHE_SCOPE: str = "system+history"
PROMPT_CACHE_TTL: str = "5m"

# ===========================================================
# 30. Prompt caching for the SESSION-SAVE phase (Anthropic only)
# ===========================================================
# The Database Handler interview that runs AFTER a session ends uses
# the SAME caching machinery as the in-session agents — the same
# helpers, the same breakpoints, the same top-level parameter.  Only
# the two knobs below are separate, so the save can be measured and
# tuned WITHOUT disturbing in-session behaviour (and vice versa).
# The values mean exactly what their §29 counterparts mean.
#
# WHY THE SAVE IS WORTH CACHING AT ALL.  _ask_agent re-seeds
# convo_buffer from the agent's FULL in-session history every time it
# opens a conversation, so that whole history is re-sent at full price
# once per conversation.  Nothing mutates agent_state.messages during
# the save (list() copies; appends land on the copy, and the image
# strip returns copies rather than editing in place), so the repeated
# prefix is byte-stable.
#
# BATCHING CHANGED THE ARITHMETIC, NOT THE CONCLUSION.  This note used
# to count one re-seed PER SCHEDULE FIELD — eight for the User Input
# Inspector, six for the Planner.  Rows going to one agent are now
# asked in batches, so it is one re-seed per BATCH: fewer full-price
# writes to begin with, and the two mechanisms compound rather than
# overlap (batching removes repeats; caching makes the ones that remain
# cheap).  The DH's OWN history is the bigger prize now — it grows
# monotonically across the whole save and every batching tool call
# reads it back through _force_tool_args.
#
# WHAT IS AND IS NOT CACHED TODAY (measured 2026-08-04).  The DH's own
# self.messages grows monotonically and caches FULLY.  The agent side
# caches only PARTLY: within a field, rounds 2+ hit in full, but ACROSS
# fields only the system prompt is read back, because the sole other
# breakpoint sits at the end of the messages and every field ends with
# a different question.  So each field's FIRST round re-writes the base
# history at 1.25x.  Net: a win from 2 rounds per field upward (~32% on
# the UII at 2 rounds), a 25% loss on any field resolved in one round.
# Closing the gap needs the briefing anchor (TODO F55), worth ~83%.
# See design_prompt_caching.md § "The session-save phase".
#
# WHY THE TTL DEFAULT IS "5m" HERE.  SCHEDULE is grouped by agent, so
# one agent's fields run back-to-back seconds apart, and every hit
# refreshes the TTL for free — the prefix stays warm through that
# agent's block however long the whole save takes.  The cheaper 1.25x
# write therefore wins; revisit after the live save measurement.
#
# Valid values: PROMPT_CACHE_SCOPE_SAVE "off"|"system"|"system+history";
# PROMPT_CACHE_TTL_SAVE "5m"|"1h".
PROMPT_CACHE_SCOPE_SAVE: str = "system+history"
PROMPT_CACHE_TTL_SAVE: str = "5m"

# ===========================================================
# 31. Session saving — the End-Session save pipeline
# ===========================================================
# Everything the save uses once the user confirms "Save" at End
# Session: how each row is rewritten for embedding, how it is
# embedded, how hard the writer retries, and what is mirrored to
# R2 when the user does NOT save.  Assembled from the former
# blocks 11, 16, 17 and 23 — the settings themselves are
# unchanged, only their position (and therefore their grouping in
# the Workflow Settings UI).
#
# The blocks are ordered the way a save executes: interview each
# agent, stitch each Q+A into embedding input, embed it, insert it
# (retrying on failure), and finally decide what to mirror when the
# user saves nothing.
#
# NOTE: the EMBEDDING_* values below are ALSO read at QUERY time —
# database_search embeds the user's query with the same model — so
# a change there affects retrieval, not just saving.


# --- Database Handler — interview model ---

# Which LLM answers when the Database Handler interviews an agent
# about the session.
#
# By default every answer is billed at that AGENT's own model — the
# User Input Inspector answers on its model, the DC Output Inspector
# on its, and so on — with the agent's entire session history re-sent
# on every question.  With the standard schedule that is ~36 answers
# per save, on the strongest models in the workflow, and it is the
# single largest cost in a save.
#
# But a DH interview is not design work: the agent is recalling and
# summarising its OWN transcript, which a small model does well.  So
# these two settings let the whole interview run on one cheap model
# regardless of what each agent ran on live.
#
# WHAT IT COVERS.  Every call the Database Handler makes TO an agent:
# the ordinary per-field answers AND the attempt-identifying calls
# (which force a ``save_attempt_data`` tool call — so a model chosen
# here must be able to make a forced tool call, or an identifying
# question drops its whole block of sub-questions after 3 retries).
# It does NOT cover the DH's own question-writing / ASK-or-SAVE
# turns (those follow the ``database_handler`` row of the LLM-routing
# chart) nor the stitching rewrite below (STITCHING_MODEL).
#
# IMAGES.  Image content blocks are stripped from the transcript the
# interview model sees, so a text-only model is always safe here.
# The agent's stored history is not modified; only the copy handed to
# the interview is.  The DH asks about reasoning, not about pixels.
#
# THIS SETTING WINS over ``LLM_ROUTING_MODE``: a global provider
# override (including the Sessions Queue's per-run single-model
# condition) changes the LIVE session, not the interview.  Set
# DH_INTERVIEW_PROVIDER to "Original Agent" when you want a run to be
# single-model end to end.
#
#   DH_INTERVIEW_PROVIDER
#     "Original Agent"  each agent answers on its own live model —
#                       the historic behaviour, and the setting to
#                       pick when the saved text must match sessions
#                       saved before this option existed.
#     "openai" | "anthropic" | "google" | "openrouter"
#                       every interview answer uses this provider
#                       with DH_INTERVIEW_MODEL, whatever the agent
#                       ran on live.
#
#   DH_INTERVIEW_MODEL  the model name, passed verbatim to the
#                       provider.  Ignored when the provider is
#                       "Original Agent".  OpenRouter needs a
#                       vendor-prefixed id (e.g.
#                       "deepseek/deepseek-chat").
#
# The chosen provider's API key must be present the same way every
# other agent's is (agents/.env or the process environment), or the
# save falls back to each agent's own model and logs a warning —
# a missing key must never lose a session's worth of answers.
#
# Valid values: DH_INTERVIEW_PROVIDER ∈ {"Original Agent", "openai",
# "anthropic", "google", "openrouter"}; DH_INTERVIEW_MODEL any model
# name the chosen provider exposes.
DH_INTERVIEW_PROVIDER: str = "openai"
DH_INTERVIEW_MODEL: str = "gpt-5.4-mini"


# --- (was 17) Database Handler — stitching model (Option B embedding input) ---

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
# Cost example: gpt-4o-mini at ~$0.15 / 1M input tokens, one call per
# SAVED ENTRY at ~300 input tokens each ≈ $0.0001 per session on a
# schedule of a few dozen rows.
#
# >>> Currently only the OpenAI provider is implemented.  The
# >>> Anthropic and Google branches are TODO items T16 and T17 in
# >>> the architecture doc.  Until they ship, STITCHING_PROVIDER is
# >>> locked to "OpenAI" in the workflow-settings editor (the
# >>> provider input is rendered as a disabled dropdown — see
# >>> ENUM_OPTIONS in workflow_settings/editor.py).  STITCHING_MODEL
# >>> stays editable so the developer can try a different OpenAI
# >>> model (e.g. gpt-4o-mini → gpt-4o) without code edits.
#
# Valid values:
#   STITCHING_PROVIDER ∈ {"OpenAI"}  (Anthropic / Google = T16 / T17, deferred)
#   STITCHING_MODEL    : any model name the chosen provider exposes
STITCHING_PROVIDER: str = "OpenAI"
STITCHING_MODEL: str = "gpt-4o-mini"

# Maximum number of output tokens the cheap stitching LLM is allowed
# to emit per Q+A rewrite.  Architecture doc §6.1 locks the output
# to "exactly one paragraph and nothing else" — the stitched
# paragraph should never need more than this.  Set lower to enforce
# brevity; set higher only if you see truncation in the embedding
# inputs (a sign that the stitching model is verbose).
#
# Visible in the workflow-settings web UI.
#
# Valid values: any positive int (recommended 400–1600).  Default 800.
STITCHING_MAX_OUTPUT_TOKENS: int = 800


# --- (was 11) Embedding model (used post-session for RAG indexing) ---

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

# Defensive cap (in characters, NOT tokens) on the stitched paragraph
# fed to the embedding model.  text-embedding-3-large enforces an
# 8192-token per-call limit; 30000 characters comfortably stays under
# that limit while leaving headroom.  Over-cap input is truncated at
# this length and a WARNING is logged — the row is still embedded
# (lossy) rather than failing the whole chunks INSERT.  See
# agents/database_handler/db_writer.py.
#
# Hidden from the workflow-settings web UI (internal tuning knob;
# see HIDDEN_FROM_FLAG_LIST in workflow_settings/editor.py).
#
# Valid values: any positive int.  Default 30000 ≈ 7500 cl100k tokens.
EMBEDDING_INPUT_MAX_CHARS: int = 30000


# --- (was 16) Database Handler — retry budget for chunks INSERT ---

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

# Fixed delay (seconds) between successive chunks-INSERT retry
# attempts when DATABASE_ENTRY_MAX_RETRIES > 1.  Architecture doc
# §3.5 locks the backoff strategy as fixed-delay (not exponential).
#
# Hidden from the workflow-settings web UI (internal tuning knob;
# see HIDDEN_FROM_FLAG_LIST in workflow_settings/editor.py).
#
# Valid values: any non-negative float (seconds).  Default 1.0.
DATABASE_ENTRY_RETRY_BACKOFF_SECONDS: float = 1.0


# --- (was 23) Save logs + agent-flow of UNSAVED sessions to R2 ---

# What happens to the session log (logs/<session>.log), the
# agent-flow trace (logs/agent_flow_<ts>.txt), the DH flow trace
# (logs/dh_flow_<ts>.txt), and the per-agent history dumps
# (logs/agent_histories/) at end of session when the user clicked
# "No save" at the End Session dialog.
#
# Local archival to ``previous_sessions/<session>/`` happens
# regardless (the worktree must be cleared for the next session);
# this setting only controls whether those files are ALSO
# mirrored to R2 under ``<session>/logs/`` in the unsaved case.
# Saved sessions (the user clicked "Save") always upload — this
# setting does not affect them.
#
#   True   logs + agent-flow + per-agent histories are pushed to
#          R2 even when the user chose not to save the session.
#          Useful for diagnostics — every session is recoverable
#          from R2 regardless of save state.
#   False  unsaved sessions stay LOCAL ONLY (under
#          previous_sessions/) and never reach R2.  Saves R2
#          storage cost for throwaway sessions and prevents test
#          sessions from polluting the production R2 bucket.
#
# Valid values: True, False
SAVE_LOGS_FOR_UNSAVED_SESSIONS: bool = False


# --- Session log — untruncated payloads for the key tools ---

# Every tool call is written to the session log as
#   [TOOL CALL]  <Agent> -> <tool>
#     args:   ...
#     result: ...
# and both halves are normally cut at 800 characters.  For most tools
# that is the right amount.  For a handful it hides exactly the part
# worth reading: what was written into a file, and what an agent
# actually saw on an image.
#
# The rule is: a file's content is logged ONCE, where it is CREATED, and
# never again where it is read back.  So the writers get their args (a
# writer's result is only a one-line receipt) and every reader stays
# capped — read_attempts, read_extracted_inputs and read_user_inputs all
# re-read text the log already holds in full, so uncapping them would
# repeat the same content once per read.  The two image tools are the
# exception: their result is not a re-read of anything.
#
#   True   these payloads are written IN FULL, uncut:
#            result  view_images, reread_text_regions
#            args    write_extraction, new_attempt_parameters
#                    (write_parameters in the 5-/3-agent topologies)
#          Every other tool, and the other half of these five, keeps
#          the 800-char cap.
#   False  every tool call keeps the 800-char cap on both halves.
#
# ``/api/save_log`` snapshots this same file to R2, so this governs the
# snapshot too.  Nothing feeds the log back into a model, so the cost is
# file size only.
#
# Valid values: True, False
LOG_FULL_TOOL_PAYLOADS: bool = True


# ===========================================================
# 32. OpenAI API style + reasoning effort
# ===========================================================
# WHICH OpenAI endpoint the ``openai`` provider talks to, and how
# hard its reasoning models are allowed to think.  Applies to the
# nine agents, the Database Handler's interview model, and the
# Sessions-Queue FINAL/INTERMEDIATE classifier.  It does NOT apply
# to the ``openrouter`` provider — OpenRouter exposes only the
# chat/completions shape and has no Responses API.
#
# WHY THIS EXISTS.  ``/v1/chat/completions`` rejects the
# combination "function tools + any reasoning effort above none":
#
#     Function tools with reasoning_effort are not supported for
#     gpt-5.6-luna in /v1/chat/completions.  To use function tools,
#     use /v1/responses or set reasoning_effort to 'none'.
#
# Every agent in this system binds tools, so on chat/completions a
# model whose server-side default effort is anything but ``none``
# 400s on its very first call.  Measured 2026-08-27: gpt-5.6-luna
# and gpt-5.6-terra default to ``medium`` and fail; gpt-5.4
# defaults to ``none`` and is why the system worked at all.  The
# corollary is worth stating plainly: on chat/completions this
# system has only ever run OpenAI models with reasoning OFF.
#
#   "responses"  ChatOpenAI(use_responses_api=True) — the
#                /v1/responses endpoint.  Function tools AND
#                reasoning both work.  Verified end to end against
#                the live API: bind_tools, image_url content
#                blocks (langchain rewrites them to input_image),
#                a forced tool_choice (the DH batch-save path),
#                the assistant -> ToolMessage -> assistant
#                round-trip, and usage_metadata including
#                output_token_details.reasoning.
#   "chat"       the historic /v1/chat/completions endpoint, kept
#                for a like-for-like comparison against older runs.
#                With OPENAI_REASONING_EFFORT left at "provider
#                default" this is byte-identical to the pre-2026-08-27
#                request shape — no endpoint kwarg, no effort field.
#                Pinning any effort ABOVE "none" here is a guaranteed
#                400 the moment an agent binds its tools; that is the
#                bug this section exists to explain, not a mode.
#
# COST OF SWITCHING.  The two endpoints COUNT the same request
# differently: an identical text-only prompt with one tool bound
# measured 140 input tokens on chat/completions and 59 on
# responses.  Nothing extra is being sent — but that number feeds
# token_usage.record(), the cost logs and the Context Pruner's
# threshold, so token figures from "chat" runs and "responses"
# runs are not comparable.
#
# Valid values: "responses" | "chat"
OPENAI_API_STYLE: str = "responses"

# How much reasoning the OpenAI model does before answering.
#
#   "provider default"  a SENTINEL, not a value: send no effort at
#                       all and let each model apply its own
#                       default.  Preserves the historic behaviour
#                       of every past run (gpt-5.4 -> none) while
#                       letting the gpt-5.6 family think at its own
#                       default (medium).
#   "none"              no reasoning.  The only value chat/
#                       completions accepts alongside tools — and
#                       even there only on models that HAVE
#                       reasoning: gpt-4.1 and gpt-4o reject the
#                       field outright ("Unrecognized request
#                       argument supplied: reasoning_effort") and
#                       gpt-5-mini rejects this particular value
#                       ("does not support 'none' with this model").
#                       Leave the sentinel selected for those.
#   "low"/"medium"/"high"
#                       pin the SAME effort on every OpenAI model,
#                       so a benchmark compares models at equal
#                       effort rather than at whatever each one
#                       happens to default to.  Note this CHANGES
#                       gpt-5.4 from its historic no-reasoning
#                       behaviour: measured on one prompt, gpt-5.4
#                       spends 0 reasoning tokens at its default,
#                       59 at "low" and 113 at "high".
#
# The sentinel is the only selection guaranteed to work on every
# OpenAI model under both styles; each pinned value is a deliberate
# per-benchmark choice you must match to the models in the queue.
#
# Valid values: "provider default" | "none" | "low" | "medium" | "high"
OPENAI_REASONING_EFFORT: str = "provider default"
