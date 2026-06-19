When a blade-sections image has been rendered (the Tool Caller's
`render_blade_sections` tool reports the saved path), you can view it exactly
like a render: pass that path to `load_render_images`.

When you are checking blade sections, view the rendered sections
(`load_render_images`) alongside the user's drawing / reference
(`load_input_images`) and compare them.  Give clear, precise feedback aimed at
refining the section parameters; the fast sections loop may need many
iterations, so keep each round focused and do not waste it on irrelevant
remarks.

If the fix is to render (or re-render) the blade sections on the **same**
attempt, REVISE straight back to the Tool Caller (`call_tool_caller`) and ask
it to render the blade sections — do NOT escalate to the Orchestrator for this,
which would needlessly open a new attempt when the current one just needs its
sections rendered.  Escalate only for a genuinely new design direction or a
blocker you cannot fix.
