"""Web search and scrape legions for the autonomous agent loop."""
import httpx
import re

async def web_search(query: str, max_results: int = 3) -> dict:
    """
    Executes a web search and returns structured evidence.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    data = {"q": query}
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data, headers=headers, timeout=10.0)
            resp.raise_for_status()
            
            results = []
            # Extract titles/URLs and snippets from DDG HTML
            titles = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', resp.text)
            snippets = re.findall(r'<a class="result__snippet" href=".*?">(.*?)</a>', resp.text)
            
            for i in range(min(len(titles), len(snippets), max_results)):
                results.append({
                    "title": titles[i][1],
                    "url": titles[i][0],
                    "snippet": snippets[i]
                })
                
            return {
                "status": "SUCCESS",
                "query": query,
                "results": results,
                "evidence_summary": " ".join([r["snippet"] for r in results])
            }
    except Exception as e:
        return {
            "status": "ERROR",
            "query": query,
            "error": str(e),
            "results": [],
            "evidence_summary": ""
        }

async def scrape_url(url: str) -> dict:
    """
    Fetches the text content of a specific URL.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0, follow_redirects=True)
            resp.raise_for_status()
            
            # Basic HTML stripping to get plain text
            text = re.sub(r'<[^>]+>', ' ', resp.text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            return {
                "status": "SUCCESS",
                "url": url,
                "content": text[:4000]  # Limit to 4000 chars
            }
    except Exception as e:
        return {
            "status": "ERROR",
            "url": url,
            "error": str(e)
        }
