"""Per-topic tool descriptors.

`tool_registry.py` historically held everything — schema helpers, ~80 param
builders, and ~106 `ToolDescriptor` literals — in one ~2900-LOC file. This
package extracts the load-bearing reusables (helpers + param builders) so
`tool_registry.py` can shrink to the actual registration logic, and so
future topic-specific descriptor modules (devices/, ui/, debug/, …) can
slot in without re-importing the world.

Today's exports:
- `_shared`: `JsonDict`, `ToolDescriptor`, schema helpers (`_string`, `_int`,
  `_bool`, `_number`, `_enum`, `_schema`, `_path`), and `_params_no`.
- `_param_builders`: every `_params_*` function that maps an arguments dict
  to a typed Params dataclass.

`tool_registry.py` re-exports `ToolDescriptor` for backward compatibility
(many tests import it from there).
"""

from __future__ import annotations
