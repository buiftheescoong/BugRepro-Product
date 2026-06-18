import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from src.database.db import engine, Base, get_db
from src.database.models import ReproductionHistory
from src.core.graph import create_rebugger_graph
from pydantic import BaseModel
import asyncio
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from src.tools.browsers import browser_manager
from src.core.config import settings
from src.utils.b2_storage import b2_storage
import base64
from src.utils.memory_manager import memory_manager
import json
from fastapi.responses import StreamingResponse
from src.utils.logger import get_logger, setup_session_logger, teardown_session_logger
logger = get_logger("server")

def format_sse(event: str, data: dict) -> str:
    """Chuyển đổi event name + data dict thành chuỗi SSE format"""
    json_str = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {json_str}\n\n"

async def stream_agent_run(agent_app, input_data, config, thread_id, db, **db_kwargs):
    """
    Async generator: chạy agent graph và yield SSE events.
    Parameters:
        agent_app   — LangGraph compiled graph
        input_data  — initial state dict (hoặc None cho resume)
        config      — {"configurable": {"thread_id": "..."}}
        thread_id   — session ID
        db          — SQLAlchemy session
        **db_kwargs — bug_description, root_url, screenshot_path
    """
    all_logs = []
    if input_data:
        final_state = dict(input_data)
    else:
        snapshot = await agent_app.aget_state(config)
        final_state = dict(snapshot.values) if snapshot.values else {}

    try:
        async for event in agent_app.astream(input_data, config=config):
            for node_name, node_output in event.items():
                if node_name == "__end__":
                    final_state = node_output
                    continue
                new_logs = node_output.get("log", [])
                if new_logs:
                    all_logs.extend(new_logs)
                    for log_entry in new_logs:
                        yield format_sse("log", log_entry)
                final_state.update(node_output)
        final_state["log"] = all_logs
        if final_state.get("wait_for_input"):
            upsert_history(db, thread_id, final_state, status="need_input")
            logger.info("Session need input", extra={"data": {
                "thread_id": thread_id,
                "status": "need_input",
                "request_message":final_state.get("input_request_message", "Additional input required from user."),
            }})
            yield format_sse("need_input", {
                "thread_id": thread_id,
                "message": final_state.get("input_request_message", 
                                           "Additional input required from user.")
            })
            return
    
        elif final_state.get("is_reproduced") or final_state.get("steps_count",0) >= settings.MAX_STEPS:
            await browser_manager.close_session(thread_id)
            memory_manager.save_task_to_memory(final_state)
            status = "success" if final_state.get("is_reproduced") else "failed"
            upsert_history(db, thread_id, final_state, status=status, **db_kwargs)
            metrics_list = final_state.get("metrics", [])
            logger.info("Session completed", extra={"data": {
                "thread_id": thread_id,
                "status": status,
                "steps_count": final_state.get("steps_count"),
                "total_input_tokens": sum(m.get("input_tokens", 0) for m in metrics_list),
                "total_output_tokens": sum(m.get("output_tokens", 0) for m in metrics_list),
                "total_llm_time_seconds": round(sum(m.get("time_seconds", 0) for m in metrics_list), 2),
                "llm_call_count": len(metrics_list),
            }})
            teardown_session_logger(thread_id)
            yield format_sse("done", {
                "status": status,
                "log": all_logs
            })
        else:
            await browser_manager.close_session(thread_id)
            upsert_history(db, thread_id, final_state, status="failed", **db_kwargs)
            teardown_session_logger(thread_id)
            yield format_sse("done", {"status": "failed", "log": all_logs})
    except Exception as e:
        logger.error(f"Session failed: {str(e)}", exc_info=True, 
                     extra={"data": {"thread_id": thread_id}})
        db.rollback()
        await browser_manager.close_session(thread_id)
        upsert_history(db, thread_id, final_state, status="error")
        teardown_session_logger(thread_id)
        yield format_sse("error", {"detail": f"Agent Error: {str(e)}"})


class ResumeInput(BaseModel):
    thread_id: str
    user_input:str

def upsert_history(db: Session, thread_id: str, state: dict, **kwargs):
    record = db.query(ReproductionHistory).filter(ReproductionHistory.thread_id == thread_id).first()
    
    history_data = state.get("log", [])
    is_success = state.get("is_reproduced", False)

    if record:
        record.actions = history_data
        record.is_success = is_success
        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)
    else:
        record = ReproductionHistory(
            thread_id=thread_id,
            bug_description=kwargs.get("bug_description"),
            root_url=kwargs.get("root_url"),
            screenshot_path=kwargs.get("screenshot_path"),
            actions=history_data,
            is_success=is_success,
            status=kwargs.get("status", "running")
        )
        db.add(record)
    
    db.commit()
    db.refresh(record)
    return record

def search_knowledge_from_past_experiences(bug_description: str, root_url: str):
    success_cases, failed_cases = memory_manager.search_similar_experiences(
            bug_description, root_url
        )
    
    past_experiences_text = ""
    if success_cases:
        past_experiences_text += "\n### SUCCESSFUL PAST EXAMPLES:\n"
        for i, c in enumerate(success_cases):
            past_experiences_text += f"Example {i+1}: {c['desc']}\nActions: {c['actions']}\n"
                
    if failed_cases:
        past_experiences_text += "\n### FAILED ATTEMPTS TO AVOID:\n"
        for i, c in enumerate(failed_cases):
            past_experiences_text += f"Avoid this path for: {c['desc']}\nFailed Actions: {c['actions']}\n"
    return len(success_cases), len(failed_cases), past_experiences_text

os.makedirs('./data', exist_ok=True)
Base.metadata.create_all(bind=engine)
CHECKPOINT_PATH = "./data/checkpoints_server_multi.db"

app = FastAPI(title="Rebugger API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/data",
    StaticFiles(directory="data"),
    name="data"
)

@app.post("/reproduce")
async def reproduce_bug_api(
    bug_description: str = Form(...),
    target_screenshot: UploadFile = File(...),
    root_url: str = Form(...),
    db: Session = Depends(get_db)
):
    thread_id = str(uuid.uuid4())
    setup_session_logger(thread_id)
    logger.info("New reproduction session", extra={"data": {
        "thread_id": thread_id,
        "bug_description": bug_description[:200],
        "root_url": root_url,
    }})
    content = await target_screenshot.read()
    file_name = f"targets/{thread_id}_{target_screenshot.filename}"
    target_url = b2_storage.upload_file(content, file_name, target_screenshot.content_type)
    target_b64 = base64.b64encode(content).decode('utf-8') 
    count_success_cases, count_failed_cases, past_experiences = search_knowledge_from_past_experiences(bug_description, root_url)
    logger.info(f"RAG lookup: {count_success_cases} success, {count_failed_cases} failed cases found",extra={"data": {"thread_id": thread_id}})
    logger.debug(f"Past experiences detail: {past_experiences}",extra={"data": {"thread_id": thread_id}})
    final_state = {}
    upsert_history(db, thread_id, {}, 
                    bug_description=bug_description, 
                    root_url=root_url, 
                    screenshot_path=target_url, 
                    status="running")
    
    async def event_stream():
        """
        Wrapper generator: mở checkpoint connection → chạy agent → stream events.
        """
        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_PATH) as memory:
            agent_app = create_rebugger_graph(memory)
            config = {"configurable": {"thread_id": thread_id}}
            
            initial_input = {
                "bug_report": bug_description,
                "target_screenshot": target_url,
                "root_url": root_url,
                "history": [],
                "log": [],
                "steps_count": 0,
                "is_reproduced": False,
                "wait_for_input": False,
                "user_provided_input": None,
                "target_screenshot_base64": target_b64,
                "past_experiences": past_experiences
            }
            
            async for chunk in stream_agent_run(
                agent_app, initial_input, config, thread_id, db,
                bug_description=bug_description,
                root_url=root_url,
                screenshot_path=target_url
            ):
                yield chunk
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",      
        headers={
            "Cache-Control": "no-cache",     
            "Connection": "keep-alive",      
            "X-Accel-Buffering": "no"        
        }
    )

@app.post("/reproduce/resume")
async def resume_reproduction(data: ResumeInput, db: Session = Depends(get_db)):
    current_state = {}
    setup_session_logger(data.thread_id)
    logger.info("Session resumed", extra={"data": {
        "thread_id": data.thread_id,
        "user_input": data.user_input[:200],
    }})
    async def event_stream():
        async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_PATH) as memory:
            agent_app = create_rebugger_graph(memory)
            config = {"configurable": {"thread_id": data.thread_id}}
            
            await agent_app.aupdate_state(config, {
                "user_provided_input": data.user_input,
                "wait_for_input": False,
                "next_action": None,
                "input_request_message": None
            })            
            async for chunk in stream_agent_run(
                agent_app, None, config, data.thread_id, db
            ):
                yield chunk
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



@app.get("/history")
async def get_all_history(db: Session = Depends(get_db)):
    histories = db.query(ReproductionHistory).order_by(ReproductionHistory.created_at.desc()).all()
    return histories

@app.get("/history/{item_id}")
async def get_history_detail(item_id: int, db: Session = Depends(get_db)):
    history = db.query(ReproductionHistory).filter(ReproductionHistory.id == item_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="History item not found")
    return history

@app.on_event("shutdown")
async def shutdown_event():
    await browser_manager.close()