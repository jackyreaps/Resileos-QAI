"""Bridge from the API to the Studio agent."""
import logging
import json
from typing import Any, Dict, List, Optional
from titanos import Titanos
from fastapi.concurrency import run_in_threadpool

# Import YOUR actual Studio agent loop
from resileos.ui.agent_loop import run_task

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Delegates the message to the Studio's built-in run_task function.
    This uses your worker_tools (web_search, lean_check, run_tests, etc.).
    """
    try:
        # Include file context if uploaded
        goal = message
        if file_data:
            goal += f"\n[User uploaded file: {file_data.get('name')} ({file_data.get('type')})]"

        # Run the synchronous run_task in a threadpool to avoid blocking the API
        result = await run_in_threadpool(run_task, goal=goal)
        
        # Format the tool trace into a readable string for the chat UI
        trace = result.get("trace", [])
        if not trace:
            answer_text = "Task completed, but no tools were executed."
        else:
            parts = []
            for step in trace:
                tool = step.get("tool", "unknown")
                res = step.get("result", {})
                
                # Extract the most relevant text from the tool result
                if isinstance(res, dict):
                    text = res.get("text") or res.get("out") or res.get("result") or res.get("url") or res.get("note")
                    if not text:
                        text = json.dumps(res, indent=2)
                else:
                    text = str(res)
                
                # Mark success/failure clearly
                status_icon = "✅" if step.get("ok") else "❌"
                parts.append(f"{status_icon} **[{tool}]**\n{text}")
            
            answer_text = "\n\n".join(parts)

        return {
            "status": "ANSWERED",
            "source": "studio_agent",
            "value": answer_text,
            "tool_calls": trace,
            "evidence": [],
            "verified": result.get("ok", False),
        }

    except Exception as e:
        log.error(f"Studio run_task failed: {e}")
        return {
            "status": "ERROR",
            "source": "studio_error",
            "value": f"Internal error: {str(e)}",
            "tool_calls": [],
            "evidence": [],
            "verified": False,
        }
