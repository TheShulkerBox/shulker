from typing import Any
from pydantic.v1 import BaseModel

class CustomResource(BaseModel):
    """Defines a custom resource which can be registered via a bolt macro"""
    
    @classmethod
    def generate(cls, data: Any):
        data = next(data).evaluate()
        return cls.parse_obj(data)
