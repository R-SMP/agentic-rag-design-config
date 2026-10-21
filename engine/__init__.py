"""Engine-level pieces of the MAS blueprint that are not agents or tools.

``pack.py`` reads the design-configurator pack (``setups/<setup>/``) and the slot
registry (``slot_registry.yaml``).  Deliberately dependency-light -- the
standard library, PyYAML and ``config`` -- so tools and the web layer can
use it without importing the prompt stack.
"""
