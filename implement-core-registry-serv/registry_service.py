import sqlite3
import uuid
import json
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Agent Capability Registry", version="1.0.0")

DB_PATH = "registry.db"

# --- Database ---

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'available'
                    CHECK(status IN ('available','busy','offline')),
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS capabilities (
                cap_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                skill TEXT NOT NULL,
                proficiency INTEGER NOT NULL DEFAULT 1 CHECK(proficiency BETWEEN 1 AND 10),
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_caps_skill ON capabilities(skill);
            CREATE INDEX IF NOT EXISTS idx_caps_agent ON capabilities(agent_id);
            CREATE TABLE IF NOT EXISTS collab_history (
                record_id TEXT PRIMARY KEY,
                agent_a TEXT NOT NULL,
                agent_b TEXT NOT NULL,
                task_desc TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(agent_a) REFERENCES agents(agent_id),
                FOREIGN KEY(agent_b) REFERENCES agents(agent_id)
            );
            CREATE INDEX IF NOT EXISTS idx_collab_agent ON collab_history(agent_a, agent_b);
        """)

# --- Models ---

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    status: str = Field("available")
    metadata: dict = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("available", "busy", "offline"):
            raise ValueError("status must be 'available', 'busy', or 'offline'")
        return v

class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in ("available", "busy", "offline"):
            raise ValueError("status must be 'available', 'busy', or 'offline'")
        return v

class CapabilityCreate(BaseModel):
    skill: str = Field(..., min_length=1, max_length=120)
    proficiency: int = Field(1, ge=1, le=10)
    description: str = Field("", max_length=500)

class CapabilityUpdate(BaseModel):
    skill: Optional[str] = Field(None, min_length=1, max_length=120)
    proficiency: Optional[int] = Field(None, ge=1, le=10)
    description: Optional[str] = Field(None, max_length=500)

class CollabRecord(BaseModel):
    agent_a: str = Field(..., min_length=1)
    agent_b: str = Field(..., min_length=1)
    task_desc: str = Field("", max_length=500)
    outcome: str = Field("", max_length=500)

# --- Helpers ---

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def agent_row_to_dict(row):
    return {
        "agent_id": row["agent_id"], "name": row["name"],
        "description": row["description"], "status": row["status"],
        "metadata": json.loads(row["metadata_json"]),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    }

def cap_row_to_dict(row):
    return {
        "cap_id": row["cap_id"], "agent_id": row["agent_id"],
        "skill": row["skill"], "proficiency": row["proficiency"],
        "description": row["description"], "created_at": row["created_at"],
    }

def collab_row_to_dict(row):
    return {
        "record_id": row["record_id"], "agent_a": row["agent_a"],
        "agent_b": row["agent_b"], "task_desc": row["task_desc"],
        "outcome": row["outcome"], "recorded_at": row["recorded_at"],
    }

# --- Health ---

@app.get("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "db": "connected", "timestamp": now_iso()}
    except Exception as e:
        raise HTTPException(503, {"status": "unhealthy", "error": str(e)})

# --- Agents CRUD ---

@app.post("/agents", status_code=201)
def create_agent(body: AgentCreate):
    aid = str(uuid.uuid4())
    ts = now_iso()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO agents (agent_id,name,description,status,metadata_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (aid, body.name, body.description, body.status, json.dumps(body.metadata), ts, ts),
        )
    return {"agent_id": aid, "created_at": ts}

@app.get("/agents")
def list_agents(status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    with get_db() as conn:
        q = "SELECT * FROM agents"
        params = []
        if status:
            q += " WHERE status=?"
            params.append(status)
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = conn.execute(q, params + [limit, offset]).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM agents" + (" WHERE status=?" if status else ""),
                             ([status] if status else [])).fetchone()[0]
    return {"agents": [agent_row_to_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

@app.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Agent not found")
    result = agent_row_to_dict(row)
    with get_db() as conn:
        caps = conn.execute("SELECT * FROM capabilities WHERE agent_id=?", (agent_id,)).fetchall()
    result["capabilities"] = [cap_row_to_dict(c) for c in caps]
    return result

@app.patch("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Agent not found")
        sets, vals = [], []
        if body.name is not None: sets.append("name=?"); vals.append(body.name)
        if body.description is not None: sets.append("description=?"); vals.append(body.description)
        if body.status is not None: sets.append("status=?"); vals.append(body.status)
        if body.metadata is not None: sets.append("metadata_json=?"); vals.append(json.dumps(body.metadata))
        if not sets:
            return {"agent_id": agent_id, "updated": False}
        sets.append("updated_at=?"); vals.append(now_iso()); vals.append(agent_id)
        conn.execute(f"UPDATE agents SET {','.join(sets)} WHERE agent_id=?", vals)
    return {"agent_id": agent_id, "updated": True}

@app.delete("/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT agent_id FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Agent not found")
        conn.execute("DELETE FROM agents WHERE agent_id=?", (agent_id,))

# --- Capabilities CRUD ---

@app.post("/agents/{agent_id}/capabilities", status_code=201)
def add_capability(agent_id: str, body: CapabilityCreate):
    cid = str(uuid.uuid4())
    ts = now_iso()
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone():
            raise HTTPException(404, "Agent not found")
        conn.execute(
            "INSERT INTO capabilities (cap_id,agent_id,skill,proficiency,description,created_at) VALUES (?,?,?,?,?,?)",
            (cid, agent_id, body.skill, body.proficiency, body.description, ts),
        )
    return {"cap_id": cid, "created_at": ts}

@app.get("/capabilities/search")
def search_capabilities(skill: str = Query(..., min_length=1), min_proficiency: int = Query(1, ge=1, le=10)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT c.*, a.name as agent_name, a.status as agent_status "
            "FROM capabilities c JOIN agents a ON c.agent_id=a.agent_id "
            "WHERE c.skill LIKE ? AND c.proficiency >= ? ORDER BY c.proficiency DESC",
            (f"%{skill}%", min_proficiency),
        ).fetchall()
    return {"capabilities": [cap_row_to_dict(r) | {"agent_name": r["agent_name"], "agent_status": r["agent_status"]} for r in rows]}

@app.patch("/capabilities/{cap_id}")
def update_capability(cap_id: str, body: CapabilityUpdate):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM capabilities WHERE cap_id=?", (cap_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Capability not found")
        sets, vals = [], []
        if body.skill is not None: sets.append("skill=?"); vals.append(body.skill)
        if body.proficiency is not None: sets.append("proficiency=?"); vals.append(body.proficiency)
        if body.description is not None: sets.append("description=?"); vals.append(body.description)
        if not sets:
            return {"cap_id": cap_id, "updated": False}
        vals.append(cap_id)
        conn.execute(f"UPDATE capabilities SET {','.join(sets)} WHERE cap_id=?", vals)
    return {"cap_id": cap_id, "updated": True}

@app.delete("/capabilities/{cap_id}", status_code=204)
def delete_capability(cap_id: str):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM capabilities WHERE cap_id=?", (cap_id,)).fetchone():
            raise HTTPException(404, "Capability not found")
        conn.execute("DELETE FROM capabilities WHERE cap_id=?", (cap_id,))

# --- Collaboration History ---

@app.post("/collaborations", status_code=201)
def record_collaboration(body: CollabRecord):
    rid = str(uuid.uuid4())
    ts = now_iso()
    with get_db() as conn:
        for aid in (body.agent_a, body.agent_b):
            if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (aid,)).fetchone():
                raise HTTPException(404, f"Agent {aid} not found")
        conn.execute(
            "INSERT INTO collab_history (record_id,agent_a,agent_b,task_desc,outcome,recorded_at) VALUES (?,?,?,?,?,?)",
            (rid, body.agent_a, body.agent_b, body.task_desc, body.outcome, ts),
        )
    return {"record_id": rid, "recorded_at": ts}

@app.get("/agents/{agent_id}/collaborations")
def get_agent_collaborations(agent_id: str, limit: int = Query(20, ge=1, le=100)):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone():
            raise HTTPException(404, "Agent not found")
        rows = conn.execute(
            "SELECT * FROM collab_history WHERE agent_a=? OR agent_b=? ORDER BY recorded_at DESC LIMIT ?",
            (agent_id, agent_id, limit),
        ).fetchall()
    return {"collaborations": [collab_row_to_dict(r) for r in rows]}

# --- Startup ---

@app.on_event("startup")
def startup():
    init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)