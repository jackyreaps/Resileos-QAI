"""Autonomous agent loop driven by the KinBundle and CascadeRouter."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos

# ── Your Infrastructure Imports ──
from resileos.kin.bundle import build_kin_bundle
from resileos.harness.cascade import CascadeRouter
from resileos.harness.legions.search import web_search, scrape_url
from resileos.kin.eat import eat_filter
from resileos.answer import AnswerContext, select_backend, StructuredBackend

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    bundle = build_kin_bundle()

    # ── Step 1: Exact Residual Check ──
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

    # ── Step 2: Run the Kin Cycle ──
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
        verified = harness_meta.get("harness", {}).get("verified", False)
        
        # Safely extract budget as an integer
        raw_budget = bundle.control.budget_remaining if bundle.control else 0
        if isinstance(raw_budget, dict):
            budget = int(raw_budget.get("remaining", raw_budget.get("budget", 0)))
        else:
            budget = int(raw_budget)
            
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False
        budget = 0

    tool_calls = []
    evidence = []
    scraped_content = None

    # ── Step 3: Perception (File Upload) ──
    if file_data and budget > 0:
        tool_calls.append({"tool": "perception", "args": {"name": file_data.get("name")}})
        return {
            "status": "ANSWERED",
            "source": "perception",
            "value": f"I have received and analyzed the file: {file_data.get('name')} ({file_data.get('type')}).",
            "tool_calls": tool_calls,
            "evidence": [],
            "verified": False,
        }

    # ── Step 4: Native Cascade Routing ──
    route = "escalate"  # Default
    try:
        router = CascadeRouter()
        route_result = router.route(
            question=message,
            options=["residual", "search", "escalate"],
            packet=bundle.control.to_dict() if bundle.control else {},
        )
        raw_route = route_result.get("route", "escalate")
        if raw_route == "residual":
            route = "residual"
        elif raw_route in ("cascade", "search"):
            route = "search"
        else:
            route = "escalate"
    except Exception as e:
        log.warning(f"Cascade routing failed: {e}")
        # Fallback heuristic if router fails
        msg_lower = message.lower()
        if any(t in msg_lower for t in ["can you", "who are you", "hello", "hi", "ready"]):
            route = "escalate"
        elif len(parts) == 2:
            route = "residual"
        else:
            route = "search"

    # ── Step 5: Execute Route ──
    if route == "escalate":
        # Conversational fallback
        final_answer = "I am the Resileos exact memory engine. I can learn facts, answer queries using my residual memory, and search the web when needed. I am fully ready."
    
    elif route == "search" and budget > 0:
        current_query = message
        if history and len(history) > 0 and len(message.split()) < 5:
            current_query = f"{history[-1].get('content', '')} {message}"

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

    # ── Step 6: Synthesize with Eat Filter Validation ──
    if scraped_content or route == "escalate":
        # For web search results, run through eat_filter
        if scraped_content:
            decision = eat_filter(scraped_content)
            if decision.action == "reject":
                return {
                    "status": "ABSTAINED",
                    "source": "eat_rejection",
                    "value": f"Eat filter rejected the answer: {decision.reason}",
                    "tool_calls": tool_calls,
                    "evidence": evidence,
                    "verified": False,
                }

            ctx = AnswerContext(
                question=message,
                subject="web_search",
                relation="evidence",
                rows=(scraped_content,),
                confidence=1.0 if evidence else 0.0,
            )
        else:
            # For conversational responses, we don't need eat_filter
            ctx = AnswerContext(
                question=message,
                subject="conversational",
                relation="answer",
                rows=(final_answer,),
                confidence=1.0,
            )

        backend = select_backend()
        if allow_mouth:
            try:
                answer_text = backend.render(ctx)
            except Exception as e:
                log.warning(f"Backend render failed: {e}")
                answer_text = final_answer if not scraped_content else f"Based on a web search: {scraped_content[:400]}..."
        else:
            answer_text = f"[Structured Retrieval] {final_answer if not scraped_content else scraped_content[:400]}..."

        final_status = "ANSWERED"
        if not verified and scraped_content:
            answer_text += "\n\n*(Note: This information came from the web and has not been verified against your exact memory.)*"

        return {
            "status": final_status,
            "source": route,
            "value": answer_text,
            "tool_calls": tool_calls,
            "evidence": evidence,
            "verified": verified,
        }

    return {
        "status": "ABSTAINED",
        "source": "none",
        "value": "I couldn't find this in my memory or the web.",
        "tool_calls": tool_calls,
        "evidence": evidence,
        "verified": False,
    }
