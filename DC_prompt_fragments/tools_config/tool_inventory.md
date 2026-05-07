1. **generate_propeller_mesh** — Generate a 3D propeller mesh from
   17 design parameters and save it as ``propeller_mesh.obj`` inside
   an attempt folder.  All 17 parameters must be provided AND the
   attempt folder must be passed via the ``output_dir`` argument.
   ``output_dir`` is the absolute path of the attempt folder for the
   current design generation — the same path the hand-off carries
   under ``Current attempt:``.  Refuses to overwrite an existing
   ``propeller_mesh.obj`` (attempt folders are append-only — start a
   new attempt via ``new_attempt`` if a fresh mesh is needed).
   Returns a message containing the absolute path to the saved
   ``.obj`` mesh file.
2. **render_and_check_mesh** — Render a mesh from three viewpoints
   (isometric, top-down, side) and optionally run geometric quality
   checks.  Takes TWO required arguments:
     - ``mesh_path``: absolute path of the ``.obj`` to render.  Pass
       the path that ``generate_propeller_mesh`` just returned.
     - ``output_dir``: absolute path of the attempt folder where the
       three render PNGs (``render_isometric.png``,
       ``render_top.png``, ``render_side.png``) should be written.
       Pass the same attempt folder that holds the mesh.  Refuses
       when any of those three files already exist there (attempt
       folders are append-only).
   When mesh checks are enabled the tool produces a fixed set of
   metrics, and ONLY these:
     - watertightness and volume
     - number of degenerate faces
   No other metric is available — do not plan or reason around
   metrics outside this list.
3. **calculate** — Evaluate one or more Python expressions in a
   SINGLE batched call.  Takes ``expressions: list[str]`` and returns
   one ``<expression> = <result>`` line per input, in input order, in
   one tool result.  ALWAYS batch every expression you currently need
   into one call (e.g. ``calculate(expressions=['2 * 3.14159 * 75',
   '20 / 75', '4 + 3', '30 > 25'])``); do not issue several
   single-expression calls in the same turn.

   **Expression syntax is Python.**  This is enforced by the
   underlying ``eval`` — any non-Python operator returns a syntax
   error and the result is unusable.  Use:

     - arithmetic: ``+``, ``-``, ``*``, ``/``, ``//``, ``%``, ``**``
     - comparison: ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``
     - boolean:    ``and``, ``or``, ``not``
     - grouping:   parentheses
     - callables:  ``abs()``, ``round()``, ``min()``, ``max()`` (and
       nothing else — no imports, no name lookups, no other
       functions)

   **Do NOT use** ``&&`` / ``||`` / ``!`` (those are JavaScript / C
   and produce ``invalid syntax`` errors), and do NOT chain checks
   with shell-style ``[ … ]`` or SQL-style ``BETWEEN``.  A range
   check is written ``x >= 3 and x <= 11`` (Python boolean ``and``),
   or equivalently ``3 <= x <= 11`` (Python's chained-comparison
   shorthand) — both are valid; ``x >= 3 && x <= 11`` is NOT.

   When you receive ``-> error: invalid syntax`` from this tool, the
   most common cause is a non-Python operator slipping in: re-issue
   the batch with ``and`` / ``or`` / ``not`` in place of ``&&`` /
   ``||`` / ``!``.
4. **list_attempts** — List every attempt folder created so far in
   this session.  Returns the attempt number, folder name, the
   ``Has:`` roles present (parameters / mesh / renders /
   description), and the file list per attempt.  Useful for finding
   prior parameter sets, prior renders, or partial folders that
   could be filled in.
5. **read_attempt(n, file)** — Read one specific file from the n-th
   attempt folder.  Text files (``parameters.json``,
   ``description.txt``, ``.obj``, etc.) are returned inline; image
   files return their absolute path so you can hand it to
   ``load_render_images``.
6. **new_attempt(slug, description)** — Create a new, EMPTY attempt
   folder for an upcoming design generation.  The slug appears in
   the folder name after the timestamp + sequence number; the
   optional description is written to ``description.txt`` inside
   the folder.  Returns the absolute path of the new folder — copy
   that path verbatim into your hand-offs as ``Current attempt:``
   so downstream agents target the same folder.
