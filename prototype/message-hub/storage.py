"""
APS Message Hub - Durable Storage Layer (SQLite).

Implements durable persistence for:
- Threads
- Messages
- Events

Enforces:
- Unique message_id / request_id
- Idempotent deduplication on duplicate message_id create
- Ordered events sequence
- Reply-to & Artifact binding validation
"""

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class Storage:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS threads (
                            thread_id TEXT PRIMARY KEY,
                            title TEXT,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        )
                    """)

                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS messages (
                            message_id TEXT PRIMARY KEY,
                            thread_id TEXT NOT NULL,
                            sender TEXT NOT NULL,
                            recipient TEXT NOT NULL,
                            message_type TEXT NOT NULL,
                            reply_to TEXT,
                            artifact_id TEXT,
                            content TEXT NOT NULL,
                            metadata TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                        )
                    """)

                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS events (
                            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            thread_id TEXT NOT NULL,
                            message_id TEXT,
                            event_type TEXT NOT NULL,
                            payload TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                        )
                    """)

                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS send_claims (
                            request_id TEXT PRIMARY KEY,
                            thread_id TEXT NOT NULL,
                            claimed_by TEXT NOT NULL,
                            claimed_at REAL NOT NULL,
                            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                        )
                    """)

                    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id)")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id)")
            finally:
                conn.close()

    def try_claim_external_send(self, thread_id: str, request_id: str, claimed_by: str) -> bool:
        """
        Atomically attempts to acquire the external-send claim for request_id in SQLite.
        Returns True if acquired (first and only claimant), False if already claimed.
        """
        with self._lock:
            self.ensure_thread(thread_id)
            conn = self._get_connection()
            try:
                now = time.time()
                with conn:
                    cursor = conn.execute("""
                        INSERT OR IGNORE INTO send_claims (request_id, thread_id, claimed_by, claimed_at)
                        VALUES (?, ?, ?, ?)
                    """, (request_id, thread_id, claimed_by, now))
                    return cursor.rowcount == 1
            finally:
                conn.close()

    def ensure_thread(self, thread_id: str, title: str = "") -> None:
        with self._lock:
            conn = self._get_connection()
            try:
                now = time.time()
                with conn:
                    conn.execute("""
                        INSERT INTO threads (thread_id, title, created_at, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(thread_id) DO UPDATE SET updated_at = ?
                    """, (thread_id, title or thread_id, now, now, now))
            finally:
                conn.close()

    def create_message(
        self,
        message_id: str,
        thread_id: str,
        sender: str,
        recipient: str,
        message_type: str,
        content: str,
        reply_to: Optional[str] = None,
        artifact_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "DELIVERED_TO_HUB"
    ) -> Tuple[Dict[str, Any], bool, Optional[Dict[str, Any]]]:
        """
        Creates a message durably.
        Returns (message_dict, is_new, created_event_dict).
        If message_id already exists:
        - If idempotent match -> returns (existing_message, False, None)
        - If conflict -> raises ValueError
        """
        with self._lock:
            self.ensure_thread(thread_id)
            conn = self._get_connection()
            try:
                existing = conn.execute(
                    "SELECT * FROM messages WHERE message_id = ?", (message_id,)
                ).fetchone()

                metadata_json = json.dumps(metadata or {})

                if existing:
                    # Check strict idempotency across authoritative fields
                    existing_meta = json.loads(existing["metadata"]) if existing["metadata"] else {}
                    input_meta = metadata or {}

                    matches = (
                        existing["thread_id"] == thread_id and
                        existing["sender"] == sender and
                        existing["recipient"] == recipient and
                        existing["message_type"] == message_type and
                        (existing["reply_to"] or None) == (reply_to or None) and
                        (existing["artifact_id"] or None) == (artifact_id or None) and
                        existing["content"] == content and
                        existing_meta == input_meta
                    )
                    if not matches:
                        raise ValueError(
                            f"Conflict: message_id '{message_id}' already exists with conflicting authoritative payload"
                        )

                    msg = dict(existing)
                    msg["metadata"] = existing_meta
                    return msg, False, None

                # Validate reply_to if specified
                if reply_to:
                    parent = conn.execute(
                        "SELECT message_id, thread_id, artifact_id FROM messages WHERE message_id = ?", (reply_to,)
                    ).fetchone()
                    if not parent:
                        raise ValueError(f"Parent message '{reply_to}' not found")
                    # Enforce same-thread reply binding
                    if parent["thread_id"] != thread_id:
                        raise ValueError(
                            f"Cross-thread reply rejected: parent '{reply_to}' is in thread '{parent['thread_id']}', but reply is in thread '{thread_id}'"
                        )
                    # If child specifies artifact_id, must match or inherit from parent
                    if artifact_id and parent["artifact_id"] and artifact_id != parent["artifact_id"]:
                        raise ValueError(
                            f"Artifact mismatch: reply specifies '{artifact_id}' but parent has '{parent['artifact_id']}'"
                        )
                    if not artifact_id and parent["artifact_id"]:
                        artifact_id = parent["artifact_id"]

                now = time.time()
                with conn:
                    conn.execute("""
                        INSERT INTO messages (
                            message_id, thread_id, sender, recipient, message_type,
                            reply_to, artifact_id, content, metadata, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        message_id, thread_id, sender, recipient, message_type,
                        reply_to, artifact_id, content, metadata_json, status, now
                    ))

                    # Create initial event
                    event_type = "REQUEST_CREATED" if message_type == "review.request" else "RESPONSE_CREATED"
                    cursor = conn.execute("""
                        INSERT INTO events (thread_id, message_id, event_type, payload, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (thread_id, message_id, event_type, json.dumps({
                        "message_id": message_id,
                        "sender": sender,
                        "recipient": recipient,
                        "message_type": message_type,
                        "status": status,
                        "artifact_id": artifact_id,
                        "reply_to": reply_to
                    }), now))
                    event_id = cursor.lastrowid

                msg_row = conn.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
                msg_dict = dict(msg_row)
                msg_dict["metadata"] = json.loads(msg_dict["metadata"])

                event_dict = {
                    "event_id": event_id,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "event_type": event_type,
                    "payload": json.loads(msg_row["metadata"]),
                    "created_at": now
                }
                return msg_dict, True, event_dict
            finally:
                conn.close()

    def record_event(
        self,
        thread_id: str,
        event_type: str,
        message_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        with self._lock:
            self.ensure_thread(thread_id)
            conn = self._get_connection()
            try:
                now = time.time()
                payload_json = json.dumps(payload or {})
                with conn:
                    cursor = conn.execute("""
                        INSERT INTO events (thread_id, message_id, event_type, payload, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (thread_id, message_id, event_type, payload_json, now))
                    event_id = cursor.lastrowid

                return {
                    "event_id": event_id,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "event_type": event_type,
                    "payload": payload or {},
                    "created_at": now
                }
            finally:
                conn.close()

    def update_message_status(self, message_id: str, new_status: str, event_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        "UPDATE messages SET status = ? WHERE message_id = ?",
                        (new_status, message_id)
                    )
                row = conn.execute("SELECT * FROM messages WHERE message_id = ?", (message_id,)).fetchone()
                if not row:
                    return None
                msg_dict = dict(row)
                msg_dict["metadata"] = json.loads(msg_dict["metadata"])

                event_dict = None
                if event_type:
                    event_dict = self.record_event(
                        thread_id=msg_dict["thread_id"],
                        event_type=event_type,
                        message_id=message_id,
                        payload={"status": new_status, "message_id": message_id}
                    )
                return msg_dict
            finally:
                conn.close()

    def get_thread(self, thread_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                t = conn.execute("SELECT * FROM threads WHERE thread_id = ?", (thread_id,)).fetchone()
                if not t:
                    return None
                return dict(t)
            finally:
                conn.close()

    def get_messages(self, thread_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                    (thread_id,)
                ).fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    d["metadata"] = json.loads(d["metadata"])
                    res.append(d)
                return res
            finally:
                conn.close()

    def get_events(self, thread_id: str, after_id: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute(
                    "SELECT * FROM events WHERE thread_id = ? AND event_id > ? ORDER BY event_id ASC",
                    (thread_id, after_id)
                ).fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    d["payload"] = json.loads(d["payload"])
                    res.append(d)
                return res
            finally:
                conn.close()
