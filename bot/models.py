import enum
from sqlalchemy import Column, String, Integer, JSON, Enum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class WorkflowStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WorkflowState(Base):
    __tablename__ = "workflows"
    workflow_id = Column(String, primary_key=True, index=True)
    tasks = Column(JSON)
    current_task_index = Column(Integer, default=0)
    initial_data = Column(JSON)
    output = Column(JSON)
    status = Column(Enum(WorkflowStatus), default=WorkflowStatus.ACTIVE)
