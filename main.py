from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from fastapi import Depends
from app.database import SessionLocal, engine
from app.model.models import Project, Code
import json
from app.service.cfg_builder import build_cfg
from app.service.path_builder import generate_execution_paths
from app.utils.unreachable_nodes import detect_unreachable_code
from app.model.request_model import CodeRequest, TestCaseRequest
from app.service.execution_tester import test_code_with_parameters, trace_execution_path
from app.model import models
from app.model.request_model import ProjectCreate
from app.model.request_model import SaveAnalysisRequest
from typing import List

models.Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

origins = [
    "http://localhost:5173",
    "https://tesflow.haloridho.my.id", 
    "https://www.tesflow.haloridho.my.id"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
async def ping():
    return {"status": "ok"}

@app.post("/projects/")
async def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@app.post("/projects/{project_id}/save_analysis/")
async def save_analysis_to_project(
    project_id: int, 
    request: SaveAnalysisRequest, 
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    code_record = Code(
        name=request.name,
        source_code=request.code,
        project_id=project_id,
        path_list=json.dumps(request.path_list),
        coverage_path=request.coverage_path,
        cyclomatic_complexity=request.cyclomatic_complexity,
        test_cases=json.dumps(request.test_cases),
        
        # --- KONVERSI KE STRING ---
        # Data [{id: "1"...}, {id: "2"...}] diubah jadi '[{"id": "1"...}]'
        nodes_list=json.dumps(request.nodes), 
        edges_list=json.dumps(request.edges)
    )

    db.add(code_record)
    db.commit()
    db.refresh(code_record)

    return {"message": "Saved", "code_id": code_record.id}

@app.get("/projects/{project_id}/export/")
async def export_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    data = {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": str(project.created_at),
            "codes": []
        }
    }

    for code in project.codes:
        data["project"]["codes"].append({
            "id": code.id,
            "name": code.name,
            "source_code": code.source_code,
            "path_list": json.loads(code.path_list or "[]"),
            "coverage_path": code.coverage_path,
            "cyclomatic_complexity": code.cyclomatic_complexity,
            "test_cases": json.loads(code.test_cases or "[]"),
            
            # --- KONVERSI BALIK KE ARRAY ---
            # String JSON dari DB diubah kembali jadi Array Object untuk Frontend
            "nodes_list": json.loads(code.nodes_list or "[]"),
            "edges_list": json.loads(code.edges_list or "[]"),
            
            "created_at": str(code.created_at)
        })

    return data

@app.get("/projects/")
async def get_all_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at,
        }
        for p in projects
    ]

@app.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}

@app.delete("/codes/{code_id}/")
async def delete_code_analysis(code_id: int, db: Session = Depends(get_db)):
    """Hapus satu record analisis berdasarkan ID."""
    code = db.query(Code).filter(Code.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="Analisis tidak ditemukan.")
    db.delete(code)
    db.commit()
    return {"message": "Analisis berhasil dihapus", "deleted_id": code_id}

@app.get("/projects/{project_id}/export/")
async def export_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    data = {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": str(project.created_at),
            "codes": []
        }
    }

    for code in project.codes:
        data["project"]["codes"].append({
            "id": code.id,
            "name": code.name,
            "source_code": code.source_code,
            "path_list": json.loads(code.path_list or "[]"),
            "coverage_path": code.coverage_path,
            "cyclomatic_complexity": code.cyclomatic_complexity,
            "test_cases": json.loads(code.test_cases or "[]"),
            "created_at": str(code.created_at)
        })

    return data

@app.post("/analyze/")
async def analyze_code(request: CodeRequest):
    code = request.code
    cfg = build_cfg(code)
    
    if cfg is None or "message" in cfg:
        return {"message": "Unable to process the code."}
        
    paths = generate_execution_paths(cfg)
    cfg["execution_paths"] = paths
    
    # Calculate cyclomatic complexity: E - N + 2
    cfg["cyclomatic_complexity"] = len(cfg["edges"]) - len(cfg["nodes"]) + 2
    cfg["nodes_count"] = len(cfg["nodes"])
    cfg["edges_count"] = len(cfg["edges"])
    
    unreachable = detect_unreachable_code(cfg)
    cfg["unreachable_code"] = unreachable
        
    return cfg

# @app.post("/projects/{project_id}/save_analysis/")
# async def save_analysis_to_project(project_id: int, request: SaveAnalysisRequest, db: Session = Depends(get_db)):
#     # Cek project ada atau tidak
#     project = db.query(Project).filter(Project.id == project_id).first()
#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found.")

#     # Simpan record baru dengan data lengkap dari Frontend
#     code_record = Code(
#         name=request.name,
#         source_code=request.code,
#         project_id=project_id,
#         path_list=json.dumps(request.path_list),
#         coverage_path=request.coverage_path,
#         cyclomatic_complexity=request.cyclomatic_complexity,
#         test_cases=json.dumps(request.test_cases)
#     )

#     db.add(code_record)
#     db.commit()
#     db.refresh(code_record)

#     return {"message": "Analysis saved successfully.", "code_id": code_record.id}

@app.post("/test_execution/")
async def test_execution_code(request: TestCaseRequest):
    code = request.code
    parameters = request.parameters
    
    try:
        # Build the CFG for the provided code
        cfg = build_cfg(code)
        
        if cfg is None or "message" in cfg:
            raise HTTPException(status_code=400, detail="Unable to process the code.")
        
        # Generate execution paths based on the CFG
        possible_paths = generate_execution_paths(cfg)
        
        # Test the actual execution with the provided parameters
        execution_result = test_code_with_parameters(code, parameters)
        
        # Trace the exact execution path with the given parameters
        actual_path = trace_execution_path(code, parameters)
        
        # Convert all path nodes to strings
        string_possible_paths = []
        for path in possible_paths:
            string_path = [str(node) for node in path]
            path_info = {
                "path_id": f"path_{len(string_possible_paths) + 1}",
                "nodes": string_path,
                "description": f"Path through nodes: {' -> '.join(string_path)}"
            }
            string_possible_paths.append(path_info)
        
        # Convert actual path line numbers to strings
        string_actual_path = [str(line) for line in actual_path]
        
        # Format the actual execution path
        formatted_actual_path = {
            "line_numbers": string_actual_path,
            "description": f"Code executed lines: {', '.join(string_actual_path)}"
        }
        
        # Create a response object with the code, parameters, test results and paths
        response = {
            "code": code,
            "parameters": parameters,
            "execution_result": {
                "success": execution_result["success"],
                "output": execution_result["stdout"],
                "return_value": execution_result["return_value"],
                "error": execution_result["error"]
            },
            "possible_paths": string_possible_paths,
            "actual_execution_path": formatted_actual_path
        }
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")