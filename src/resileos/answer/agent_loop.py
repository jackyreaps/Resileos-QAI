"""Autonomous agent loop driven by the KinBundle and CascadeRouter."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos

from resileos.kin.bundle import build_kin_bundle
from resileos.harness.cascade import CascadeRouter
from resileos.harness.legions.search import web_search, scrape_url
from resileos.kin.eat import eat_filter
from resileos.answer import AnswerContext, select_backend

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

    # 2. Run Kin Cycle & Safely Get Budget
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

    # 3. Handle File Upload Context
    file_context = ""
    if file_data:
        tool_calls.append({"tool": "perception", "args": {"name": file_data.get("name")}})
        file_context = f" [User uploaded file: {file_data.get('name')} ({file_data.get('type')})]"

    # 4. Native Cascade Routing
    route = "escalate"
    try:
        router = CascadeRouter()
        route_result = router.route(
            question=message,
            options=["residual", "search", "escalate"],
            packet=bundle.control.to_dict() if bundle.control else {},
        )
        route = route_result.get("route", "escalate")
    except Exception as e:
        log.warning(f"Cascade routing failed: {e}")

    # 5. Execute Route
    if route == "search" and budget > 0:
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

    # 6. Synthesize with Native Backend
    if scraped_content or route == "escalate":
        # Run web scraped content through your Eat Filter
        if scraped_content:
            decision = eat_filter(scraped_content)
            if decision.action == "reject":
                return {
                    "status": "ABSTAINED", "source": "eat_rejection",
                    "value": f"Eat filter rejected the web content: {decision.reason}",
                    "tool_calls": tool_calls, "evidence": evidence, "verified": False,
                }

        # Build the context for your native AnswerBackend
        # FIXED: Added inverse=False to prevent the TypeError crash
        ctx = AnswerContext(
            question=message + file_context,
            subject="web_search" if scraped_content else "conversational",
            relation="evidence" if scraped_content else "answer",
            inverse=False,
            rows=(scraped_content,) if scraped_content else tuple(h.get('content', '') for h in history),
            confidence=1.0 if (scraped_content or route == "escalate") else 0.0,
        )

        backend = select_backend()
        if allow_mouth:
            try:
                # This is where your actual backend generates the response
                answer_text = backend.render(ctx)
            except Exception as e:
                log.warning(f"Backend render failed: {e}")
                answer_text = scraped_content[:400] if scraped_content else "I am unable to render a response right now."
        else:
            answer_text = f"[Structured Retrieval] {scraped_content[:400] if scraped_content else 'Mouth policy denied.'}"

        if not verified and scraped_content:
            answer_text += "\n\n*(Note: Not verified against exact memory.)*"

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
