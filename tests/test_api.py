def test_ready_endpoint_returns_ok(client):
    """Readiness probe. Returns 200 once the store is open."""
    r = client.get("/api/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert isinstance(body["facts"], int)


def test_sparql_endpoint_returns_rows(client):
    """Single-hop SPARQL against a known fact."""
    # Seed one fact so the query is answerable
    client.post("/api/v1/learn", json={
        "subject": "alice", "relation": "knows", "obj": "bob",
    })
    r = client.post("/api/v1/sparql", json={
        "query": "SELECT ?o WHERE alice --knows--> ?o",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert ["bob"] in body["rows"]


def test_sparql_endpoint_rejects_syntax_error(client):
    """Malformed query returns 400, not 500."""
    r = client.post("/api/v1/sparql", json={
        "query": "not a valid query",
    })
    assert r.status_code == 400
