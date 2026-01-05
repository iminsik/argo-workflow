"""
Database configuration and models for storing task logs.
"""
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
import os

# Database connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@postgres:5432/postgres"
)

# Create engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class Task(Base):
    """Model for storing logical tasks (can have multiple runs)."""
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True, index=True)  # Stable task ID
    python_code = Column(Text, nullable=False)
    dependencies = Column(Text, nullable=True)  # Can be package list or "requirements.txt"
    requirements_file = Column(Text, nullable=True)  # Requirements file content if used
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship to runs
    runs = relationship("TaskRun", back_populates="task", order_by="desc(TaskRun.run_number)", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, runs={len(self.runs) if self.runs else 0})>"


class TaskRun(Base):
    """Model for storing individual task runs (each workflow execution)."""
    __tablename__ = "task_runs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    workflow_id = Column(String, index=True, nullable=False)  # Argo workflow name
    run_number = Column(Integer, nullable=False)  # Sequential run number for this task
    phase = Column(String, nullable=False, default="Pending")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    task = relationship("Task", back_populates="runs")
    logs = relationship("TaskLog", back_populates="run", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, run_number={self.run_number}, workflow_id={self.workflow_id}, phase={self.phase})>"


class TaskLog(Base):
    """Model for storing task logs (per run)."""
    __tablename__ = "task_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("task_runs.id", ondelete="CASCADE"), index=True, nullable=True)  # Nullable for migration
    node_id = Column(String, nullable=False)
    pod_name = Column(String, nullable=False)
    phase = Column(String, nullable=False)
    logs = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    run = relationship("TaskRun", back_populates="logs")
    
    def __repr__(self):
        return f"<TaskLog(run_id={self.run_id}, pod={self.pod_name}, phase={self.phase})>"


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

