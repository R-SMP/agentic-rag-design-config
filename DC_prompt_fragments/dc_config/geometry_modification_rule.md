The ONLY way to change the generated geometry is by changing the 17
design parameters via the **DC Input Creator** and regenerating.
You must NEVER invent or request operations such as:
  - boolean unions / welding / vertex merging
  - remeshing / retessellation / hole filling
  - normal recomputation / manifold repair
  - small-component pruning
  - adding struts, supports, or any feature not derivable from the 17
    parameters
  - custom output filenames
  - any "mesh-fix pipeline", external script, or manual post-processing
If the DC Output Inspector reports issues, call the Planner to propose
a parameter change, then let the chain execute.  Do NOT ask the Tool
Caller to "fix" the mesh — it cannot.
