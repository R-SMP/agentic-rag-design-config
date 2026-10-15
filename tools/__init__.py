"""The engine's own tools: ``calculate``, the database tools
(``database_search``, ``retrieve_attempt``, ``retrieve_user_inputs``) and
``visualize_3d_model``.

The design configurator's tools -- the propeller generator and the
blade-sections visualizer -- live in the pack, ``dc_pack/tools/<name>/``, and
are loaded and bound by role by ``engine/pack_tools.py`` (MAS-blueprint P3c).
Their settings (geometry backend, render library, mesh checks, render views,
the blade-sections switch) are tool settings: declared in each tool's
``tool.yaml``, changed in Workflow Settings.

Import submodules directly (``from tools.calculate.calculate import
calculate``); this package imports nothing itself.
"""
