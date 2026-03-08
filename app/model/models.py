from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.database import Base
import datetime

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    codes = relationship("Code", back_populates="project", cascade="all, delete-orphan")

class Code(Base):
    __tablename__ = "codes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    source_code = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    
    path_list = Column(Text) 
    nodes_list = Column(Text) 
    edges_list = Column(Text) 
    test_cases = Column(Text) 

    cyclomatic_complexity = Column(Integer)
    coverage_path = Column(Float)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    project = relationship("Project", back_populates="codes")