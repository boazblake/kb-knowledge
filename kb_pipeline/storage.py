from __future__ import annotations
import json, sqlite3, uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from .domain import ACL, AuditEvent, CanonicalDocument, SearchHit, SourceVersion

_QUIESCE_LOCKS = {}
_QUIESCE_GUARD = threading.Lock()

def database_quiesce_lock(path):
    key = str(Path(path).resolve())
    with _QUIESCE_GUARD:
        return _QUIESCE_LOCKS.setdefault(key, threading.RLock())

def _dt(v): return datetime.fromisoformat(v) if v else None
def _json(v): return json.dumps(v, sort_keys=True)

class SQLiteStore:
    """Single-writer durable store. SQLite transaction is consistency boundary."""
    def __init__(self, path: Path | str = ":memory:", artifact_root: Path | None = None):
        self.path = str(path); self.artifact_root = artifact_root or Path(str(path) + ".raw")
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row; self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS raw_records(source_id TEXT, version TEXT, uri TEXT, observed_at TEXT, content_hash TEXT, artifact TEXT, metadata TEXT, PRIMARY KEY(source_id,version));
        CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY, source_id TEXT, version TEXT, uri TEXT, observed_at TEXT, title TEXT, text TEXT, readers TEXT, admins TEXT, metadata TEXT, tombstoned INTEGER DEFAULT 0, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS audit(event_id TEXT PRIMARY KEY, action TEXT, actor TEXT, target TEXT, at TEXT);
        CREATE TABLE IF NOT EXISTS checkpoints(connector TEXT PRIMARY KEY, value TEXT, complete INTEGER);
        CREATE TABLE IF NOT EXISTS tombstones(document_id TEXT PRIMARY KEY, deleted_at TEXT);
        CREATE TABLE IF NOT EXISTS revocations(source_id TEXT PRIMARY KEY, suppressed_until TEXT);
        CREATE TABLE IF NOT EXISTS purge_status(purge_id TEXT PRIMARY KEY, scope TEXT NOT NULL, target TEXT NOT NULL, status TEXT NOT NULL, candidates INTEGER NOT NULL DEFAULT 0, purged INTEGER NOT NULL DEFAULT 0, reason TEXT, started_at TEXT NOT NULL, completed_at TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(document_id UNINDEXED, title, text);
        INSERT OR IGNORE INTO schema_migrations VALUES (1);
        """); self.db.commit()
    def _doc(self, r):
        readers = None if r['readers'] is None else frozenset(json.loads(r['readers']))
        acl=ACL(readers, frozenset(json.loads(r['admins'] or '[]')))
        return CanonicalDocument(r['document_id'], SourceVersion(r['source_id'],r['version'],r['uri'],_dt(r['observed_at']) or datetime.now(timezone.utc),r['version']),r['title'],r['text'],acl,json.loads(r['metadata'] or '{}'),bool(r['tombstoned']),_dt(r['deleted_at']))
    def put(self, doc, allow_older=False):
        if self.db.execute("SELECT 1 FROM tombstones WHERE document_id=?",(doc.document_id,)).fetchone(): return False
        old=self.db.execute("SELECT * FROM documents WHERE document_id=?",(doc.document_id,)).fetchone()
        if old and (old['tombstoned'] or (not allow_older and old['observed_at'] and doc.source.observed_at < _dt(old['observed_at']))): return False
        self.db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(doc.document_id,doc.source.source_id,doc.source.version,doc.source.source_uri,doc.source.observed_at.isoformat(),doc.title,doc.text,None if doc.acl.readers is None else _json(list(doc.acl.readers)),_json(list(doc.acl.admins)),_json(dict(doc.metadata)),int(doc.tombstoned),doc.deleted_at.isoformat() if doc.deleted_at else None))
        self.db.execute("DELETE FROM documents_fts WHERE document_id=?",(doc.document_id,));
        if not doc.tombstoned and doc.acl.readers is not None: self.db.execute("INSERT INTO documents_fts VALUES (?,?,?)",(doc.document_id,doc.title,doc.text))
        self.db.commit(); return True
    def save_raw(self, record):
        with database_quiesce_lock(self.path):
            p=self.artifact_root / record.source.content_hash
            if not p.exists(): p.write_bytes(record.payload)
            self.db.execute("INSERT OR IGNORE INTO raw_records VALUES (?,?,?,?,?,?,?)",(record.source.source_id,record.source.version,record.source.source_uri,record.source.observed_at.isoformat(),record.source.content_hash,str(p),_json(dict(record.metadata)))); self.db.commit()
    def save_revocation(self, source_id, suppressed_until):
        self.db.execute("INSERT OR REPLACE INTO revocations VALUES (?,?)", (source_id, suppressed_until.isoformat())); self.db.commit()
    def all_revocations(self):
        return {r["source_id"]: _dt(r["suppressed_until"]) for r in self.db.execute("SELECT * FROM revocations")}
    def validate_artifact_links(self):
        for row in self.db.execute("SELECT artifact FROM raw_records"):
            path = Path(row["artifact"])
            if not path.is_file():
                raise ValueError(f"missing raw artifact: {path}")
        return True
    def get(self, id):
        r=self.db.execute("SELECT * FROM documents WHERE document_id=?",(id,)).fetchone(); return self._doc(r) if r else None
    def all(self): return tuple(self._doc(r) for r in self.db.execute("SELECT * FROM documents"))
    def tombstone(self,id):
        at=datetime.now(timezone.utc).isoformat(); self.db.execute("INSERT OR IGNORE INTO tombstones VALUES (?,?)",(id,at)); self.db.execute("UPDATE documents SET tombstoned=1,deleted_at=? WHERE document_id=?",(at,id)); self.db.execute("DELETE FROM documents_fts WHERE document_id=?",(id,)); self.db.commit()
    def begin_purge(self, scope, target, candidates=0):
        purge_id = uuid.uuid4().hex
        at = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT INTO purge_status VALUES (?,?,?,?,?,?,?,?,?)", (purge_id, scope, target, "running", candidates, 0, None, at, None)); self.db.commit()
        return purge_id
    def finish_purge(self, purge_id, purged, status="complete", reason=None):
        self.db.execute("UPDATE purge_status SET status=?,purged=?,reason=?,completed_at=? WHERE purge_id=?", (status, purged, reason, datetime.now(timezone.utc).isoformat(), purge_id)); self.db.commit()
    def purge_status(self, purge_id=None):
        query = "SELECT * FROM purge_status WHERE purge_id=?" if purge_id else "SELECT * FROM purge_status ORDER BY started_at DESC"
        rows = self.db.execute(query, (purge_id,) if purge_id else ()).fetchall()
        return [dict(row) for row in rows]
    def purge(self,before, *, source_id=None, document_id=None, purge_id=None):
        """Purge tombstoned documents without deleting shared content hashes."""
        clauses = ["tombstoned=1", "deleted_at<?"]; args = [before.isoformat()]
        if source_id is not None: clauses.append("source_id=?"); args.append(source_id)
        if document_id is not None: clauses.append("document_id=?"); args.append(document_id)
        where = " AND ".join(clauses)
        rows=self.db.execute("SELECT document_id,source_id FROM documents WHERE " + where, args).fetchall()
        ids=[r["document_id"] for r in rows]
        source_ids={r["source_id"] for r in rows}
        artifacts=[r["artifact"] for r in self.db.execute("SELECT artifact FROM raw_records WHERE source_id IN (%s)" % ",".join("?" * len(source_ids)), tuple(source_ids))] if source_ids else []
        self.db.executemany("DELETE FROM documents_fts WHERE document_id=?", [(i,) for i in ids])
        self.db.executemany("DELETE FROM documents WHERE document_id=?", [(i,) for i in ids])
        if source_ids:
            # Remove raw row only when no surviving document references source.
            for source in source_ids:
                still = self.db.execute("SELECT 1 FROM documents WHERE source_id=?", (source,)).fetchone()
                if not still: self.db.execute("DELETE FROM raw_records WHERE source_id=?", (source,))
        self.db.commit()
        for artifact in artifacts:
            path=Path(artifact)
            if path.exists() and not self.db.execute("SELECT 1 FROM raw_records WHERE artifact=?", (artifact,)).fetchone(): path.unlink()
        if purge_id: self.finish_purge(purge_id, len(ids))
        return len(ids)
    def search(self,q):
        try: rows=self.db.execute("SELECT d.* FROM documents_fts f JOIN documents d USING(document_id) WHERE documents_fts MATCH ? ORDER BY bm25(documents_fts)",(q,)).fetchall()
        except sqlite3.OperationalError: return []
        return [SearchHit(r['document_id'],r['title'],r['text'][:240],r['uri'],r['version']) for r in rows]
    def rebuild_index(self):
        self.db.execute("DELETE FROM documents_fts"); self.db.execute("INSERT INTO documents_fts SELECT document_id,title,text FROM documents WHERE tombstoned=0 AND readers IS NOT NULL"); self.db.commit()
    def append(self,e): self.db.execute("INSERT OR IGNORE INTO audit VALUES (?,?,?,?,?)",(e.event_id,e.action,e.actor,e.target,e.at.isoformat())); self.db.commit()
    def all_audit(self): return tuple(AuditEvent(r['event_id'],r['action'],r['actor'],r['target'],_dt(r['at']) or datetime.now(timezone.utc)) for r in self.db.execute("SELECT * FROM audit"))
    def checkpoint(self, connector, value, complete): self.db.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)",(connector,value,int(complete))); self.db.commit()
    def status(self): return {"documents":self.db.execute("SELECT count(*) FROM documents WHERE tombstoned=0").fetchone()[0],"tombstones":self.db.execute("SELECT count(*) FROM tombstones").fetchone()[0],"raw_records":self.db.execute("SELECT count(*) FROM raw_records").fetchone()[0],"wal":True}

MemoryDocumentStore = SQLiteStore
class MemoryAuditStore:
    def __init__(self): self.events=[]
    def append(self,e):
        if not any(x.event_id==e.event_id for x in self.events): self.events.append(e)
    def all(self): return tuple(self.events)
class LexicalIndex:
    def __init__(self): self._docs={}
    def replace(self,d, namespace="default"):
        if not isinstance(namespace, str):
            key = (namespace.provider, namespace.tenant, namespace.connector, namespace.source_instance, d.document_id)
        else: key = (namespace, d.document_id)
        self._docs[key]=d
    def remove(self,id, namespace=None):
        if namespace is None:
            for key in [k for k in self._docs if k[1] == id]: self._docs.pop(key, None)
        elif not isinstance(namespace, str):
            self._docs.pop((namespace.provider, namespace.tenant, namespace.connector, namespace.source_instance, id), None)
        else: self._docs.pop((namespace, id), None)
    def search(self,q):
        from .adapters import tokenize
        terms=tokenize(q); return [SearchHit(d.document_id,d.title,d.text[:240],d.source.source_uri,d.source.version) for d in self._docs.values() if terms & tokenize(d.title+' '+d.text)]
