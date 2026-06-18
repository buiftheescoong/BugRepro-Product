from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from .db import Base
import datetime

class ReproductionHistory(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String, unique=True, index=True) 
    bug_description = Column(String)
    root_url = Column(String)
    screenshot_path = Column(String) 
    actions = Column(JSON)
    # Trạng thái của Task: 'running', 'need_input', 'success', 'failed', 'error'
    status = Column(String, default="running") 
    is_success = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    

