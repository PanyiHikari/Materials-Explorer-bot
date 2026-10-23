from typing import Dict, Optional
from dataclasses import dataclass

@dataclass
class CrystalContext:
    material_id: str
    formula: str = ""
    last_updated: float = 0.0

_contexts: Dict[str, CrystalContext] = {}

def set_context(group_id: str, material_id: str, formula: str = ""):
    import time
    _contexts[group_id] = CrystalContext(
        material_id=material_id,
        formula=formula,
        last_updated=time.time(),
    )

def get_context(group_id: str) -> Optional[CrystalContext]:
    return _contexts.get(group_id)

def clear_context(group_id: str):
    _contexts.pop(group_id, None)