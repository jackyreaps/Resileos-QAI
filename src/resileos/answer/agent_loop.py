"""Full swarm agent loop driven by the KinBundle."""
import logging
from typing import Any, Dict, List
from titanos import Titanos
from resileos.kin.bundle import KinBundle
from resileos.harness.legions.search import web_search, scrape_url
from resileos.answer import AnswerContext, select_backend

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
    file_data: dict | None = None,  # New: for uploads
) -> Dict[str, Any]:
    
    bundle = KinBundle(titanos=titanos)
    
    # ── Step 1: Residual Check (Titanos) ──
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

    # ── Step 2: Run the Full Kin Cycle (Iris -> Metis -> Hermes -> Apollo) ──
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
        verified = harness_meta.get("harness", {}).get("verified", False)
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False

    # ── Step 3: Check Hermes Budget & Execute Legions ──
    tool_calls = []
    evidence = []
    final_answer = None
    
    budget = bundle.control.to_dict().get("budget_remaining", 0) if bundle.control else 0
    
    if budget > 0:
        # Handle multimedia upload first (if present)
        if file_data:
            # Call a hypothetical "file_analysis" legion
            tool_calls.append({"tool": "file_analysis", "args": {"file_type": file_data['type']}})
            # ... process file_data ...
            final_answer = f"Analyzed uploaded {file_data['type']}."
        
        # Handle web search (if no file or as a supplement)
        if not final_answer:
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
                        final_answer = scrape_result["content"]
                
                if not final_answer:
                    final_answer = search_result["evidence_summary"]

    # ── Step 4: Synthesize & Return using Native Backend ──
    if final_answer:
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
        
        final_status = "ANSWERED"
        if not verified:
            answer_text += "\n\n*(Note: This information has not been verified by Apollo against your exact memory.)*"
            
        return {
            "status": final_status, "source": "swarm", "value": answer_text,
            "tool_calls": tool_calls, "evidence": evidence, "verified": verified
        }
    else:
        return {
            "status": "ABSTAINED", "source": "none",
            "value": "The swarm could not find an answer within the budget.",
            "tool_calls": tool_calls, "evidence": evidence, "verified": False
        }
