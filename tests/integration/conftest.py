import os
import pytest
import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
API_PREFIX = "/api/v1/agents"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c


@pytest.fixture(autouse=True)
def cleanup_agents(client):
    """Remove all registered agents after each test for isolation."""
    yield
    try:
        resp = client.get(f"{API_PREFIX}/search")
        for agent in resp.json():
            aid = agent.get("id")
            if aid:
                client.delete(f"{API_PREFIX}/{aid}")
    except Exception:
        pass


@pytest.fixture
def sample_agent():
    return {
        "name": "test-agent-alpha",
        "capabilities": ["text-generation", "summarization"],
        "endpoint": "https://alpha.internal:9000",
        "availability": "available",
        "metadata": {"version": "1.0.0", "owner": "team-acprompt"},
    }


@pytest.fixture
def sample_agent_beta():
    return {
        "name": "test-agent-beta",
        "capabilities": ["code-review", "testing"],
        "endpoint": "https://beta.internal:9001",
        "availability": "available",
        "metadata": {"version": "2.1.0", "owner": "team-platform"},
    }


def register_agent(client, payload):
    """Helper: register an agent and return its id."""
    resp = client.post(f"{API_PREFIX}/register", json=payload)
    assert resp.status_code == 201, f"Setup register failed: {resp.text}"
    return resp.json()["id"]