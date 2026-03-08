from pydantic import BaseModel
from typing import List, Dict, Any, Tuple, Set, Optional, Union

class CodeRequest(BaseModel):
    code: str

class TestCaseRequest(BaseModel):
    code: str
    parameters: Dict[str, Any]
    
class ProjectCreate(BaseModel):
    name: str
    description: str = "" 
    
class SaveAnalysisRequest(BaseModel):
    name: str
    code: str
    cyclomatic_complexity: int
    coverage_path: float
    path_list: List[Dict[str, Any]]
    test_cases: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]