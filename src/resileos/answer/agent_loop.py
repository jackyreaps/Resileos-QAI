"""Autonomous agent loop driven by the KinBundle and CascadeRouter."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos
from resileos.kin.bundle import KinBundle
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
    bundle = KinBundle(titanos=titanos)

    # ── Step 1: Exact Residual Check ──
    parts = message.split()
    if len(parts) == 2:
        try:
            rows = titanos.ask_list(parts[0], parts[1])
            if rows:
                return {
                    "status": "ANSWERED",
                    "source": "residual",
                    "value": rows[0],
                    "tool_calls": [],
                    "evidence": [],
                    "verified": True,
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

    tool_calls = []
    evidence = []
    final_answer = None

    # ── Step 3: Native Cascade Routing ──
    # Use the real CascadeRouter from the harness
    router = CascadeRouter()
    
    # The router expects options like ["residual", "search", "escalate"]
    route_result = router.route(
        question=message,
        options=["residual", "search", "escalate"],
        packet=bundle.control.to_dict() if bundle.control else {},
    )

    route = route_result.get("route", "escalate")

    # ── Step 4: Execute Route ──
    if route == "residual":
        # The router decided the residual memory is sufficient
        try:
            rows = titanos.ask_list(parts[0], parts[1])
            if rows:
                final_answer = rows[0]
                evidence.append({"source": "residual", "value": rows[0]})
        except Exception:
            final_answer = None

    elif route == "search" and budget > 0:
        # The router decided we need to search
        query = message
        if history and len(message.split()) < 5:
            query = f"{history[-1].get('content', '')} {message}".strip()

        tool_calls.append({"tool": "web_search", "args": {"query": query}})
        search_result = await web_search(query)

        if search_result.get("status") == "SUCCESS" and search_result.get("results"):
            evidence.append(search_result)
            top = search_result["results"][0]
            context_text = search_result.get("evidence_summary", "")

            if "duckduckgo.com" not in top.get("url", ""):
                tool_calls.append({"tool": "scrape_url", "args": {"url": top["url"]}})
                scrape = await scrape_url(top["url"])
                if scrape.get("status") == "SUCCESS":
                    evidence.append(scrape)
                    context_text += f"\n\nDetailed context: {scrape.get('content')[:2000]}"

            # We have the web content; now we need to synthesize an answer
            final_answer = context_text

    # ── Step 5: Synthesize with Native Backend ──
    if final_answer:
        # Run the final answer through the Eat filter
        decision = eat_filter(final_answer)
        if decision.action == "reject":
            return {
                "status": "ABSTAINED",
                "source": "eat_rejection",
                "value": f"Eat filter rejected the answer: {decision.reason}",
                "tool_calls": tool_calls,
                "evidence": evidence,
                "verified": False,
            }

        # Build context for the native backend
        ctx = AnswerContext(
            question=message,
            subject="swarm",
            relation="evidence",
            rows=(final_answer,),
            confidence=1.0 if evidence else 0.0,
        )

        backend = select_backend()
        if allow_mouth:
            try:
                answer_text = backend.render(ctx)
            except Exception as e:
                log.warning(f"Backend render failed: {e}")
                answer_text = final_answer[:400]
        else:
            answer_text = f"[Structured Retrieval] {final_answer[:400]}..."

        if not verified:
            answer_text += "\n\n*(Note: Not verified by Apollo against residual memory.)*"

        return {
            "status": "ANSWERED",
            "source": route,
            "value": answer_text,
            "tool_calls": tool_calls,
            "evidence": evidence,
            "verified": verified,
            "eat_decision": decision.to_dict() if hasattr(decision, "to_dict") else {"action": decision.action},
        }

    return {
        "status": "ABSTAINED",
        "source": "none",
        "value": "Swarm could not answer within budget.",
        "tool_calls": tool_calls,
        "evidence": evidence,
        "verified": False,
    }
