import asyncio
from src.core.graph import create_rebugger_graph
from src.tools.browsers import browser_manager
import sys
import os
import uuid
import traceback
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver 




async def main():
    async with AsyncSqliteSaver.from_conn_string("././data/checkpoints.db") as memory:

        agent_app = create_rebugger_graph(memory)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_input = {
            "bug_report": "Admin can create a flight with a departure time in the past",
            "target_screenshot": r"C:\Users\admin\OneDrive\Pictures\Screenshots\Screenshot 2026-01-29 153206.png",
            "root_url": "http://qairline.ui-testing.io.vn/login",
            "history": [],
            "steps_count": 0,
            "is_reproduced": False,
            "wait_for_input": False,
            "user_provided_input": None,
        }

        try:
            print(f"Starting Rebugger Agent (Thread: {thread_id})...")
            
            
            current_input = initial_input
            
            while True:
                async for event in agent_app.astream(current_input, config=config):
                    for node, output in event.items():
                        if "history" in output:
                            last_log = output["history"][-1]
                            print(f"[{node.upper()}]: {last_log['content']}")
                state = await agent_app.aget_state(config)
                values = state.values
                if values.get("wait_for_input"):
                    print("\n" + "="*30)
                    print("AGENT NEEDS YOUR HELP!")
                    print(f"Question: {values.get('input_request_message')}")
                    print("="*30)
                    user_val = input("Enter the required info (or type 'exit' to quit): ")
                    if user_val.lower() == 'exit':
                        break
                    print(f"Updating state with: {user_val}...")
                    await agent_app.aupdate_state(config, {
                        "user_provided_input": user_val,
                        "wait_for_input": False
                    })                    
                    current_input = None
                    print("Resuming agent...\n")
                else:
                    print("\n--- WORKFLOW FINISHED ---")
                    print(f"Final Result (is_reproduced): {values.get('is_reproduced')}")
                    break
        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()
        finally:
            await browser_manager.close()
            
if __name__ == "__main__":
    asyncio.run(main())