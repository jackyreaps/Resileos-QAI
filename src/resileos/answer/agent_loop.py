""""""Autonomous agent loop driven by the KinBundle."""
import logging
from typing import Any, Dict, List
from titanos import Titanos

from resileos.kin.bundle import KinBundle
from resileos.harness.legions.search import web_search, scrape_url
from resileos.answer import AnswerContext, select_backend, StructuredBackend

log = logging.getLogger(__name__)


async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
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

    # ── Step 2: Run the Kin Cycle (Iris -> Metis -> Hermes) ──
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
        verified = harness_meta.get("harness", {}).get("verified", False)
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False

    # ── Step 3: Check Hermes Budget & Execute Legion ──
    tool_calls = []
    evidence = []
    scraped_content = None
    
    budget = bundle.control.to_dict().get("budget_remaining", 0) if bundle.control else 0
    
    if budget > 0:
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

    # ── Step 4: Synthesize & Return using Native Backend ──
    if scraped_content:
        # Build a context for the native backend to render
        ctx = AnswerContext(
            question=message,
            subject="web_search",
            relation="evidence",
            rows=(scraped_content,), # Put evidence in rows
            confidence=1.0 if evidence else 0.0,
        )
        
        # Use your native backend instead of an external LLM
        backend = select_backend()
        
        if allow_mouth:
            try:
                answer_text = backend.render(ctx)
            except Exception as e:
                log.warning(f"Backend render failed: {e}")
                answer_text = f"Based on a web search: {scraped_content[:400]}..."
        else:
            # Metis says no mouth
            answer_text = f"[Structured Retrieval] {scraped_content[:400]}..."
        
        final_status = "ANSWERED"
        if not verified:
            answer_text += "\n\n*(Note: This information came from the web and has not been verified against your exact memory.)*"
            
        return {
            "status": final_status, "source": "web_search", "value": answer_text,
            "tool_calls": tool_calls, "evidence": evidence, "verified": verified
        }
    else:
        return {
            "status": "ABSTAINED", "source": "none",
            "value": "I couldn't find this in my memory or the web. (Hermes budget might be exhausted).",
            "tool_calls": tool_calls, "evidence": evidence, "verified": False
        }Autonomous agent loop driven by the KinBundle."""
import logging
import os
import httpx
from typing import Any, Dict, List
from titanos import Titanos

# Import the Kin architecture
from resileos.kin.wiring import get_kin_bundle
from resileos.kin.legions import register_legion, kin_catalogue
from resileos.harness.legions.search import web_search, scrape_url
from resileos.kin.mouth_policy import should_render_prose

log = logging.getLogger(__name__)

# Register the web_search as a legion under Hermes (context/budget Kin)
# This means it inherits Hermes's budget checks and risk gates.
try:
    register_legion("hermes", "web_search", web_search)
    register_legion("hermes", "scrape_url", scrape_url)
except Exception as e:
    log.warning(f"Could not register legions: {e}")


async def synthesize_answer(query: str, evidence: str, history: List[dict], allow_mouth: bool) -> str:
    """Uses an LLM to turn raw web snippets into a fluid answer, IF the Kin allows it."""
    if not allow_mouth:
        # If Metis says no mouth, return structured data
        return f"[Structured Retrieval] {evidence[:400]}..."

    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return f"Based on a web search: {evidence[:400]}..."

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    prompt = (
        f"You are Resileos, an exact memory engine. The user asked: '{query}'. "
        f"You didn't know this from memory, so you searched the web. "
        f"Web Data: {evidence}. "
        f"Answer the user's question clearly and fluidly based ONLY on the web data."
    )
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 150
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.warning(f"LLM synthesis failed: {e}")
        return f"Based on a web search: {evidence[:400]}..."


async def run_agent_chat(
    titanos: Titanos,
    message: str,
    history: List[dict],
) -> Dict[str, Any]:
    
    bundle = get_kin_bundle()
    
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

    # ── Step 2: Run the Kin Cycle (Iris -> Metis -> Hermes) ──
    # This loads the harness guards, checks budgets, and sets the policy.
    try:
        report, policy, harness_meta = bundle.cycle(apply_policy=True)
        allow_mouth = policy.allow_mouth
        verified = harness_meta.get("harness", {}).get("verified", False)
    except Exception as e:
        log.warning(f"Kin cycle failed: {e}")
        allow_mouth = False
        verified = False

    # ── Step 3: Check Hermes Budget & Execute Legion ──
    # Hermes controls context depth and budget.
    tool_calls = []
    evidence = []
    scraped_content = None
    
    # Check if we have budget remaining in the control packet
    budget = bundle.control.to_dict().get("budget_remaining", 0) if bundle.control else 0
    
    if budget > 0:
        # Resolve context (if user says "Not me, you", we use history)
        current_query = message
        if history and len(history) > 0 and len(message.split()) < 5:
            current_query = f"{history[-1].get('content', '')} {message}"

        tool_calls.append({"tool": "web_search", "args": {"query": current_query}})
        search_result = await web_search(current_query)
        
        if search_result["status"] == "SUCCESS" and search_result["results"]:
            evidence.append(search_result)
            top_url = search_result["results"][0]["url"]
            
            # Scrape the top result if it's a direct link
            if "duckduckgo.com" not in top_url:
                tool_calls.append({"tool": "scrape_url", "args": {"url": top_url}})
                scrape_result = await scrape_url(top_url)
                if scrape_result["status"] == "SUCCESS":
                    evidence.append(scrape_result)
                    scraped_content = scrape_result["content"]
            
            if not scraped_content:
                scraped_content = search_result["evidence_summary"]

    # ── Step 4: Synthesize & Return ──
    if scraped_content:
        answer_text = await synthesize_answer(message, scraped_content, history, allow_mouth)
        
        # Use Apollo's verification status
        final_status = "ANSWERED"
        if not verified:
            # If Apollo didn't verify it, we mark it as a candidate web result
            answer_text += "\n\n*(Note: This information came from the web and has not been verified against your exact memory.)*"
            
        return {
            "status": final_status, "source": "web_search", "value": answer_text,
            "tool_calls": tool_calls, "evidence": evidence, "verified": verified
        }
    else:
        return {
            "status": "ABSTAINED", "source": "none",
            "value": "I couldn't find this in my memory or the web. (Hermes budget might be exhausted).",
            "tool_calls": tool_calls, "evidence": evidence, "verified": False
        }
