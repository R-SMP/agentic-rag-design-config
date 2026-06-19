When a blade-sections image has been rendered (the Tool Caller's
`render_blade_sections` tool reports the saved path), you can view it exactly
like a render: pass that path to `load_render_images`.

When you are checking blade sections, view the rendered sections
(`load_render_images`) alongside the user's drawing / reference
(`load_input_images`) and compare them.  Give clear, precise feedback aimed at
refining the section parameters; the fast sections loop may need many
iterations, so keep each round focused and do not waste it on irrelevant
remarks.
