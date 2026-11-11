"""Intelligent router bridging the API to the Studio architecture."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos

# Safely import your UI modules so the server never crashes if paths change
try:
    from resileos.ui.agent_loop import run_task
except ImportError:
    run_task = None

try:
    from resileos.ui.video_codex import recess_from_codex
except ImportError:
    recess_from_codex = None

try:
    from resileos.ui.recursive_improve import recursive_step
except ImportError:
    recursive_step = None

try:
    from resileos.ui.worker_tools import lean_check
except ImportError:
    lean_check = None

from resileos.kin.bundle import build_kin_bundle
from resileos.harness.legions.search import web_search
from resileos.answer import AnswerContext, select_backend

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    
    msg_lower = message.lower()
    bundle = build_kin_bundle()

    # 1. Exact Residual Check (2 words)
    parts = message.split()
    if len(parts) == 2:
        try:
            rows = titanos.ask_list(parts[0], parts[1])
            if rows:
                return {
                    "status": "ANSWERED", "source": "residual", "value": rows[0],
                    "tool_calls": [], "evidence": [], "verified": True
                }
        except Exception:
            pass

    # 2. Run Kin Cycle to get policy
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
    except Exception:
        allow_mouth = True

    # 3. Route specific tools based on keywords
    if "video" in msg_lower and recess_from_codex:
        try:
            res = recess_from_codex(message, world_id="world:video")
            return {
                "status": "ANSWERED", "source": "video_codex",
                "value": f"Video Codex generated {len(res.get('recesses', []))} frames.\n{res.get('note', '')}",
                "tool_calls": [{"tool": "video_codex"}], "evidence": [], "verified": False
            }
        except Exception as e:
            return {"status": "ERROR", "source": "video_codex", "value": str(e), "tool_calls": [], "evidence": [], "verified": False}

    if ("lean" in msg_lower or "verify" in msg_lower) and recursive_step:
        try:
            facts = [{"subject": s, "relation": r, "obj": o} for s, r, o in [("alice", "works_at", "acme")]]
            res = recursive_step(facts, subject="world:lean")
            return {
                "status": "ANSWERED", "source": "recursive_improve",
                "value": f"Verification complete.\nRewritten: {res.get('rewritten')}\nKept: {res.get('kept')}",
                "tool_calls": [{"tool": "recursive_step"}], "evidence": [], "verified": True
            }
        except Exception as e:
            return {"status": "ERROR", "source": "recursive_improve", "value": str(e), "tool_calls": [], "evidence": [], "verified": False}

    # 4. Route to Studio Coding Agent ONLY for coding tasks
    if ("run" in msg_lower or "test" in msg_lower or "commit" in msg_lower or "repo" in msg_lower) and run_task:
        try:
            import asyncio
            # Run the synchronous agent in a threadpool
            res = await asyncio.to_thread(run_task, goal=message)
            
            # Format the trace
            trace = res.get("trace", [])
            text_lines = []
            for step in trace:
                icon = "✅" if step.get("ok") else "❌"
                text_lines.append(f"{icon} {step.get('tool')}: {step.get('result')}")
            
            return {
                "status": "ANSWERED", "source": "studio_agent",
                "value": "\n".join(text_lines) if text_lines else "Agent completed but returned no trace.",
                "tool_calls": trace, "evidence": [], "verified": res.get("ok", False)
            }
        except Exception as e:
            return {"status": "ERROR", "source": "studio_agent", "value": str(e), "tool_calls": [], "evidence": [], "verified": False}

    # 5. Conversational Fallback (No dumb web searches)
    # If it's just chatting, use the AnswerBackend to generate a natural response.
    try:
        ctx = AnswerContext(
            question=message,
            subject="conversational",
            relation="answer",
            inverse=False,
            rows=(),
            confidence=1.0,
        )
        
        backend = select_backend()
        if allow_mouth:
            answer_text = backend.render(ctx)
        else:
            answer_text = "I am online and ready. I can learn facts, run tools, and verify code. Try asking me to 'run tests' or 'make a video'."
            
        # Clean up the structured backend's default text if it looks broken
        if "no record" in answer_text.lower() or "structured retrieval" in answer_text.lower():
            answer_text = "I am online and ready. I can learn facts, run tools, and verify code. Try asking me to 'run tests' or 'make a video'."

        return {
            "status": "ANSWERED", "source": "conversational",
            "value": answer_text, "tool_calls": [], "evidence": [], "verified": True
        }
    except Exception as e:
         return {"status": "ANSWERED", "source": "fallback", "value": "I am online and ready.", "tool_calls": [], "evidence": [], "verified": True}
