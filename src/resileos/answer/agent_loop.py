"""Autonomous agent loop driven by the KinBundle and CascadeRouter."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos

# Your actual infrastructure
from resileos.kin.bundle import build_kin_bundle
from resileos.harness.cascade import CascadeRouter
from resileos.harness.legions.search import web_search, scrape_url
from resileos.kin.eat import eat_filter
from resileos.kin.athena import judge
from resileos.ui.video_codex import recess_from_codex
from resileos.ui.recursive_improve import recursive_step
from resileos.answer import AnswerContext, select_backend, StructuredBackend

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    
    bundle = build_kin_bundle()

    # 1. Exact Residual Check
    parts = message.split()
    if len(parts) == 2:
        subject, relation = parts[0], parts[1]
        try:
            rows = titanos.ask_list(subject, relation)
            if rows:
                return {
                    "status": "ANSWERED", "source": "residual", "value": rows[0],
                    "tool_calls": [], "evidence": [], "verified": True
                }
        except Exception:
            pass

    # 2. Run Kin Cycle
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
        verified = harness_meta.get("harness", {}).get("verified", False)
        
        raw_budget = bundle.control.budget_remaining if bundle.control else 0
        budget = int(raw_budget.get("remaining", raw_budget.get("budget", 0))) if isinstance(raw_budget, dict) else int(raw_budget)
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False
        budget = 0

    tool_calls = []
    evidence = []
    scraped_content = None
    final_answer = None

    # 3. Handle File Context (Athena Perception)
    file_context = ""
    if file_data:
        tool_calls.append({"tool": "perception", "args": {"name": file_data.get("name")}})
        try:
            athena_result = judge([file_data], subject=f"file:{file_data.get('name')}")
            file_context = f" [User uploaded file: {file_data.get('name')} ({file_data.get('type')}). Athena reading: {athena_result.get('reading')}]"
        except Exception as e:
            file_context = f" [User uploaded file: {file_data.get('name')}]"

    # 4. Native Cascade Routing
    route = "escalate"
    try:
        router = CascadeRouter()
        route_result = router.route(
            question=message,
            options=["residual", "search", "escalate"],
            packet=bundle.control.to_dict() if bundle.control else {},
        )
        raw_route = route_result.get("route", "escalate")
        route = "search" if raw_route in ("cascade", "search") else raw_route
    except Exception as e:
        log.warning(f"Cascade routing failed: {e}")

    # 5. Handle Specific Tool Commands
    msg_lower = message.lower()
    
    if "video" in msg_lower or "make a video" in msg_lower:
        tool_calls.append({"tool": "video_codex", "args": {"codex": message}})
        try:
            video_result = recess_from_codex(message, world_id="world:video")
            final_answer = f"Video Codex Result:\n{video_result.get('note')}\nGenerated {len(video_result.get('recesses', []))} frames."
            route = "video"
        except Exception as e:
            final_answer = f"Video generation failed: {e}"
            route = "escalate"

    elif any(t in msg_lower for t in ["lean", "verify", "formal", "prove"]):
        tool_calls.append({"tool": "recursive_improve", "args": {"subject": "world:lean"}})
        try:
            facts = [{"subject": s, "relation": r, "obj": o} for s, r, o in [("alice", "works_at", "acme")]]
            verify_result = recursive_step(facts, subject="world:lean")
            final_answer = f"Verification Result:\nRewritten: {verify_result.get('rewritten')}\nKept: {verify_result.get('kept')}\nNote: {verify_result.get('note')}"
            route = "lean"
        except Exception as e:
            final_answer = f"Verification failed: {e}"
            route = "escalate"

    elif route == "search" and budget > 0:
        current_query = message + file_context
        if history and len(history) > 0 and len(message.split()) < 5:
            current_query = f"{history[-1].get('content', '')} {current_query}"

        tool_calls.append({"tool": "web_search", "args": {"query": current_query}})
        search_result = await web_search(current_query)

        if search_result["status"] == "SUCCESS" and search_result["results"]:
            evidence.append(search_result)
            top_url = search_result["results"][0]["url"]

            if "duckduckgo.com" not in top_url:
                tool_calls.append({"tool": "scrape_url", "args": {"url": top_url}})
                scrape_result = await scrape_url(top_url)
                if scrape_result["status"] == "SUCCESS":
                    evidence.append(scrape_result)
                    scraped_content = scrape_result["content"]

            if not scraped_content:
                scraped_content = search_result["evidence_summary"]

    # 6. Synthesize
    if scraped_content or route == "escalate" or final_answer:
        # Run web scraped content through your Eat Filter
        if scraped_content:
            decision = eat_filter(scraped_content)
            if decision.action == "reject":
                return {
                    "status": "ABSTAINED", "source": "eat_rejection",
                    "value": f"Eat filter rejected the web content: {decision.reason}",
                    "tool_calls": tool_calls, "evidence": evidence, "verified": False,
                }

        # --- THE FIX ---
        # If it's a conversation (escalate), we do NOT use AnswerContext. 
        # AnswerContext is for memory lookups (subject/relation).
        # We return the text directly to the user.
        if route == "escalate" and not scraped_content and not final_answer:
            final_answer = f"I am online and listening. You said: '{message}'. I am currently running without an LLM connected to my mouth, so I am using direct native routing."

        if scraped_content:
            ctx = AnswerContext(
                question=message + file_context,
                subject="web_search",
                relation="evidence",
                inverse=False,
                rows=(scraped_content,),
                confidence=1.0,
            )
            backend = select_backend()
            if allow_mouth:
                try:
                    answer_text = backend.render(ctx)
                except Exception:
                    answer_text = scraped_content[:400]
            else:
                answer_text = f"[Structured Retrieval] {scraped_content[:400]}"
                
            if not verified:
                answer_text += "\n\n*(Note: Not verified against exact memory.)*"
        else:
            # Direct native response (no AnswerContext lookup)
            answer_text = final_answer

        return {
            "status": "ANSWERED", 
            "source": route, 
            "value": answer_text,
            "tool_calls": tool_calls, 
            "evidence": evidence, 
            "verified": verified,
        }

    return {
        "status": "ABSTAINED", 
        "source": "none", 
        "value": "The swarm could not find an answer.",
        "tool_calls": tool_calls, 
        "evidence": evidence, 
        "verified": False,
    }
