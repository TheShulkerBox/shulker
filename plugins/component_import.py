"""
Generate a bolt module that imports every component module for ordering..
"""

from beet import Context
from bolt import Module


def beet_default(ctx: Context):
    all_components = set()
    for module in ctx.data[Module]:
        if not module.startswith("component:") or "type" in module:
            continue
        
        all_components.add(module)
    
    ctx.data[Module]["component:all"] = Module("\n".join(f"import {component} as _" for component in all_components))
