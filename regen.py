"""Generate register definitions for every consumer from registers.yaml.

Targets:
    sv  -> SystemVerilog register block   (gcb-rtl/rtl/generated/)
    hpp -> C++ named constants            (gcb-host/include/generated/)
    py  -> Python address map for proxy   (gcb-host/proxy/generated/)
    ts  -> TypeScript enum for dashboard  (gcb-dashboard/src/generated/)

Every emitted file carries a DO NOT EDIT banner and the map_version.
"""

raise NotImplementedError("Step 2: implement after registers.yaml is populated.")
