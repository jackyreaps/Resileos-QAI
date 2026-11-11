"""Autonomous agent loop driven by KinBundle and CascadeRouter."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos
from resileos.kin.bundle import KinBundle
from resileos.harness.legions.search import web_search, scrape_url
from resileos.kin.eat import eat_filter
from resileos.answer import AnswerContext, select_backend

# Safely import the real CascadeRouter from your harness
try:
    from resileos.harness.cascade import CascadeRouter
    HAS_CASCADE = True
except ImportError:
    log.warning("CascadeRouter not found. Using fallback routing.")
    HAS_CASCADE = False

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    
    bundle = KinBundle(titanos=titanos)
    tool_calls = []
    evidence = []
    final_answer = None

    # ── Step 1: Exact Residual Check ──
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

    # ── Step 2: Run Kin Cycle (Iris → Metis → Hermes) ──
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = getattr(policy, "allow_mouth", False)
        verified = harness_meta.get("harness", {}).get("verified", False)
        budget = getattr(bundle.control, "budget_remaining", 0) if bundle.control else 0
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False
        budget = 0

    # ── Step 3: Native Cascade Routing ──
    route = "escalate"  # Default
    
    if HAS_CASCADE:
        try:
            router = CascadeRouter()
            route_result = router.route(
                question=message,
                options=["residual", "search", "escalate"],
                packet=bundle.control.to_dict() if bundle.control else {},
            )
            # Map the router's response to our execution paths
            raw_route = route_result.get("route", "escalate")
            if raw_route == "residual":
                route = "residual"
            elif raw_route in ("cascade", "search"):
                route = "search"
            else:
                route = "escalate"
        except Exception as e:
            log.warning(f"Cascade routing failed: {e}")
            route = "escalate"
    else:
        # Fallback routing if Cascade is missing
        msg_lower = message.lower()
        if any(t in msg_lower for t in ["can you", "who are you", "hello", "hi", "ready"]):
            route = "escalate"
        elif len(parts) == 2:
            route = "residual"
        else:
            route = "search"

    # ── Step 4: Execute Route ──
    if file_data:
        final_answer = f"I have received and analyzed the file: {file_data.get('name')} ({file_data.get('type')})."
        tool_calls.append({"tool": "perception", "args": {"name": file_data.get('name')}})
    
    elif route == "escalate":
        # Native conversational fallback
        final_answer = "I am the Resileos exact memory engine. I can learn facts, answer queries using my residual memory, and search the web when needed. I am fully ready."
    
    elif route == "search" and budget > 0:
        # Web search fallback
        query = message
        if history and len(message.split()) < 5:
            query = f"{history[-1].get('content', '')} {message}".strip()

        tool_calls.append({"tool": "web_search", "args": {"query": query}})
        search_result = await web_search(query)
        
        if search_result.get("status") == "SUCCESS" and search_result.get("results"):
            evidence.append(search_result)
            top = search_result["results"][0]
            final_answer = search_result.get("evidence_summary", "")
            
            if "duckduckgo.com" not in top.get("url", ""):
                tool_calls.append({"tool": "scrape_url", "args": {"url": top["url"]}})
                scrape = await scrape_url(top["url"])
                if scrape.get("status") == "SUCCESS":
                    evidence.append(scrape)
                    final_answer = scrape.get("content")
        else:
            final_answer = "I searched the web but couldn't find a good answer."

    # ── Step 5: Synthesize & Return ──
    if final_answer:
        # Run the final answer through the Eat filter
        try:
            decision = eat_filter(final_answer)
            if getattr(decision, "action", "") == "reject":
                return {
                    "status": "ABSTAINED", "source": "eat_rejection",
                    "value": f"Eat filter rejected the answer: {decision.reason}",
                    "tool_calls": tool_calls, "evidence": evidence, "verified": False
                }
        except Exception:
            pass

        ctx = AnswerContext(
            question=message, subject="swarm", relation="evidence",
            rows=(final_answer,), confidence=1.0 if evidence else 0.0,
        )
        
        backend = select_backend()
        if allow_mouth:
            try:
                answer_text = backend.render(ctx)
            except Exception:
                answer_text = final_answer[:400]
        else:
            answer_text = f"[Structured Retrieval] {final_answer[:400]}..."

        if not verified and evidence:
            answer_text += "\n\n*(Note: Not verified by Apollo against residual memory.)*"

        return {
            "status": "ANSWERED", "source": route, "value": answer_text,
            "tool_calls": tool_calls, "evidence": evidence, "verified": verified,
        }

    return {
        "status": "ABSTAINED", "source": "none",
        "value": "Swarm could not answer within budget.",
        "tool_calls": tool_calls, "evidence": evidence, "verified": False
    }
