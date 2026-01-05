"""
Database configuration and models for storing task logs.
"""
from sqlalchemy import create_engine, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session, relationship, Mapped, mapped_column
from datetime import datetime
from typing import Generator
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
class Base(DeclarativeBase):
    pass


class Task(Base):
    """Model for storing logical tasks (can have multiple runs)."""
    __tablename__ = "tasks"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)  # Stable task ID
    python_code: Mapped[str] = mapped_column(Text, nullable=False)
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # Can be package list or "requirements.txt"
    requirements_file: Mapped[str | None] = mapped_column(Text, nullable=True)  # Requirements file content if used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship to runs
    runs: Mapped[list["TaskRun"]] = relationship("TaskRun", back_populates="task", order_by="desc(TaskRun.run_number)", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, runs={len(self.runs) if self.runs else 0})>"


class TaskRun(Base):
    """Model for storing individual task runs (each workflow execution)."""
    __tablename__ = "task_runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    workflow_id: Mapped[str] = mapped_column(String, index=True, nullable=False)  # Argo workflow name
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequential run number for this task
    phase: Mapped[str] = mapped_column(String, nullable=False, default="Pending")
    python_code: Mapped[str] = mapped_column(Text, nullable=False)  # Snapshot of code used for this run
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # Snapshot of dependencies used for this run
    requirements_file: Mapped[str | None] = mapped_column(Text, nullable=True)  # Snapshot of requirements file used for this run
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="runs")
    logs: Mapped[list["TaskLog"]] = relationship("TaskLog", back_populates="run", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<TaskRun(id={self.id}, task_id={self.task_id}, run_number={self.run_number}, workflow_id={self.workflow_id}, phase={self.phase})>"


class TaskLog(Base):
    """Model for storing task logs (per run)."""
    __tablename__ = "task_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("task_runs.id", ondelete="CASCADE"), index=True, nullable=True)  # Nullable for migration
    node_id: Mapped[str] = mapped_column(String, nullable=False)
    pod_name: Mapped[str] = mapped_column(String, nullable=False)
    phase: Mapped[str] = mapped_column(String, nullable=False)
    logs: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship
    run: Mapped["TaskRun"] = relationship("TaskRun", back_populates="logs")
    
    def __repr__(self):
        return f"<TaskLog(run_id={self.run_id}, pod={self.pod_name}, phase={self.phase})>"


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

