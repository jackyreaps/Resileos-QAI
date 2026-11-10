"""Autonomous agent loop for open chat."""
import logging
from typing import Any, Dict
from titanos import Titanos
from resileos.harness.legions.search import web_search

log = logging.getLogger(__name__)

async def run_agent_chat(
    titanos: Titanos,
    message: str,
    max_steps: int = 3
) -> Dict[str, Any]:
    """
    Runs an autonomous loop:
    1. Attempts exact residual retrieval.
    2. If failed, attempts tool calling (web search).
    3. Returns structured answer with evidence.
    """
    steps = 0
    tool_calls = []
    evidence = []
    
    # ── Step 1: Residual Check ──
    # Try to parse "subject relation" out of the message
    parts = message.split()
    if len(parts) == 2:
        subject, relation = parts[0], parts[1]
        try:
            rows = titanos.ask_list(subject, relation)
            if rows:
                return {
                    "status": "ANSWERED",
                    "source": "residual",
                    "value": rows[0],
                    "tool_calls": [],
                    "evidence": [],
                    "verified": True
                }
        except Exception as e:
            log.warning(f"Residual query failed: {e}")

    # ── Step 2: Agent Tool Loop ──
    while steps < max_steps:
        steps += 1
        
        tool_calls.append({"tool": "web_search", "args": {"query": message}})
        search_result = await web_search(message)
        
        if search_result["status"] == "SUCCESS" and search_result["results"]:
            evidence.append(search_result)
            
            answer_text = (
                f"Based on a web search: {search_result['evidence_summary'][:300]}... "
                f"(Source: {search_result['results'][0]['url']})"
            )
            
            return {
                "status": "ANSWERED",
                "source": "web_search",
                "value": answer_text,
                "tool_calls": tool_calls,
                "evidence": evidence,
                "verified": False # Web search is never auto-verified
            }
            
    # ── Step 3: Abstain ──
    return {
        "status": "ABSTAINED",
        "source": "none",
        "value": "I could not find this in exact memory, and my web search failed to return results.",
        "tool_calls": tool_calls,
        "evidence": evidence,
        "verified": False
    }
