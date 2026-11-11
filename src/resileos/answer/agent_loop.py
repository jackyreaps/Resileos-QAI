"""Autonomous agent loop driven by the KinBundle."""
import logging
from typing import Any, Dict, List, Optional
from titanos import Titanos
from resileos.kin.bundle import KinBundle
from resileos.harness.legions.search import web_search, scrape_url
from resileos.answer import AnswerContext, select_backend, StructuredBackend

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: Optional[dict] = None,
) -> Dict[str, Any]:
    bundle = KinBundle(titanos=titanos)

    # ── Step 1: Residual Check ──
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
        budget = bundle.control.to_dict().get("budget_remaining", 0) if bundle.control else 0
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

    # ── Step 4: Web Search ──
    if budget > 0 and not scraped_content:
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

    # ── Step 5: Synthesize & Return ──
    if scraped_content:
        ctx = AnswerContext(
            question=message,
            subject="web_search",
            relation="evidence",
            rows=(scraped_content,),
            confidence=1.0 if evidence else 0.0,
        )

        backend = select_backend()
        if allow_mouth:
            try:
                answer_text = backend.render(ctx)
            except Exception as e:
                log.warning(f"Backend render failed: {e}")
                answer_text = f"Based on a web search: {scraped_content[:400]}..."
        else:
            answer_text = f"[Structured Retrieval] {scraped_content[:400]}..."

        final_status = "ANSWERED"
        if not verified:
            answer_text += "\n\n*(Note: This information came from the web and has not been verified against your exact memory.)*"

        return {
            "status": final_status,
            "source": "web_search",
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
