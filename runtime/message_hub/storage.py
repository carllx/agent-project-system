"""Message Hub Durable Storage Layer.

Provides SQLite relational persistence, first-class identities (including
conversation_id and connector_id), atomic send claims bound to real requests,
durable connector cursors with explicit handling outcomes, same-thread reply
hierarchy, DB-level unique response constraints, and transactional exactly-once
RESPONSE_READY response generation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass(frozen=True)
class Thread:
    thread_id: str
    title: str
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Message:
    message_id: str
    thread_id: str
    conversation_id: str
    connector_id: str
    sender: str
    recipient: str
    message_type: str
    reply_to: str | None
    artifact_id: str | None
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Event:
    event_id: int
    thread_id: str
    message_id: str | None
    connector_id: str | None
    event_type: str
    payload: dict[str, Any]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SendClaim:
    request_id: str
    thread_id: str
    claimed_by: str
    claimed_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConnectorCursor:
    connector_id: str
    last_processed_event_id: int
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StorageError(Exception):
    """Base exception for Storage errors."""


class ConflictError(StorageError):
    """Raised when an entity conflicts with existing authoritative state."""


class ThreadIntegrityError(StorageError):
    """Raised when thread or reply hierarchy constraints are violated."""


class CursorError(StorageError):
    """Raised when cursor advancement operations violate monotonicity or integrity."""


class Storage:
    """Production SQLite-backed durable storage engine for APS Message Hub."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self, timeout: float = 30.0) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(
            self.db_path, timeout=timeout, isolation_level=None
        )  # autocommit mode for explicit transaction control
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    connector_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message_type TEXT NOT NULL,
                    reply_to TEXT,
                    artifact_id TEXT,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    message_id TEXT,
                    connector_id TEXT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
                );

                CREATE TABLE IF NOT EXISTS send_claims (
                    request_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    claimed_by TEXT NOT NULL,
                    claimed_at REAL NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(thread_id),
                    FOREIGN KEY (request_id) REFERENCES messages(message_id)
                );

                CREATE TABLE IF NOT EXISTS connector_cursors (
                    connector_id TEXT PRIMARY KEY,
                    last_processed_event_id INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
                CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
                CREATE INDEX IF NOT EXISTS idx_messages_reply ON messages(reply_to);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_review_response_reply ON messages(reply_to)
                WHERE message_type = 'review.response' AND reply_to IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_events_connector ON events(connector_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_events_thread ON events(thread_id);
                CREATE INDEX IF NOT EXISTS idx_events_id ON events(event_id);
                """
            )

    # -------------------------------------------------------------------------
    # Thread Operations
    # -------------------------------------------------------------------------

    def create_thread(self, thread_id: str, title: str = "") -> Thread:
        t_id = thread_id.strip()
        if not t_id:
            raise ValueError("thread_id must be non-empty")
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                cursor = conn.execute(
                    "SELECT thread_id, title, created_at, updated_at FROM threads WHERE thread_id = ?",
                    (t_id,),
                )
                row = cursor.fetchone()
                if row:
                    conn.execute("COMMIT;")
                    return Thread(
                        thread_id=row["thread_id"],
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                conn.execute(
                    "INSERT INTO threads (thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (t_id, title.strip(), now, now),
                )
                conn.execute("COMMIT;")
                return Thread(thread_id=t_id, title=title.strip(), created_at=now, updated_at=now)
            except BaseException:
                conn.execute("ROLLBACK;")
                raise

    def get_thread(self, thread_id: str) -> Thread | None:
        t_id = thread_id.strip()
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT thread_id, title, created_at, updated_at FROM threads WHERE thread_id = ?",
                (t_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return Thread(
                thread_id=row["thread_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    # -------------------------------------------------------------------------
    # Message & Deduplication Operations
    # -------------------------------------------------------------------------

    def create_message(
        self,
        thread_id: str,
        message_id: str,
        conversation_id: str,
        connector_id: str,
        sender: str,
        recipient: str,
        message_type: str,
        content: str,
        reply_to: str | None = None,
        artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "PENDING",
    ) -> tuple[Message, bool]:
        """Create a message with strict deduplication and conflict validation.

        Returns (Message, is_new).
        - If message_type is 'review.response', raises ConflictError (reserved authoritative path).
        - If message_id exists with identical authoritative payload: returns (existing, False).
        - If message_id exists with conflicting payload: raises ConflictError.
        - If reply_to is provided: validates parent message exists in the SAME thread.
        """
        t_id = thread_id.strip()
        m_id = message_id.strip()
        conv_id = conversation_id.strip()
        conn_id = connector_id.strip()
        snd = sender.strip()
        rcp = recipient.strip()
        m_type = message_type.strip()
        rep_to = reply_to.strip() if reply_to else None
        art_id = artifact_id.strip() if artifact_id else None
        meta = metadata if metadata is not None else {}
        meta_json = json.dumps(meta, sort_keys=True)

        if not t_id or not m_id:
            raise ValueError("thread_id and message_id must be non-empty")
        if not conv_id:
            raise ValueError("conversation_id must be non-empty")
        if not conn_id:
            raise ValueError("connector_id must be non-empty")
        if not snd or not rcp or not m_type:
            raise ValueError("sender, recipient, and message_type must be non-empty")

        # Reserved type enforcement: review.response MUST be created via create_response_and_ready_event
        if m_type == "review.response":
            raise ConflictError(
                "Reserved message_type 'review.response' cannot be created via generic create_message; "
                "use create_response_and_ready_event instead"
            )

        now = time.time()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                # Ensure thread exists
                t_row = conn.execute(
                    "SELECT thread_id FROM threads WHERE thread_id = ?", (t_id,)
                ).fetchone()
                if not t_row:
                    conn.execute(
                        "INSERT INTO threads (thread_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        (t_id, f"Thread {t_id}", now, now),
                    )

                # Check existing message with same message_id
                existing_row = conn.execute(
                    "SELECT * FROM messages WHERE message_id = ?", (m_id,)
                ).fetchone()

                if existing_row:
                    # Validate payload equality
                    is_identical = (
                        existing_row["thread_id"] == t_id
                        and existing_row["conversation_id"] == conv_id
                        and existing_row["connector_id"] == conn_id
                        and existing_row["sender"] == snd
                        and existing_row["recipient"] == rcp
                        and existing_row["message_type"] == m_type
                        and existing_row["reply_to"] == rep_to
                        and existing_row["artifact_id"] == art_id
                        and existing_row["content"] == content
                    )
                    if not is_identical:
                        raise ConflictError(
                            f"Message '{m_id}' already exists with conflicting authoritative payload"
                        )
                    try:
                        existing_meta = json.loads(existing_row["metadata"])
                    except Exception:
                        existing_meta = {}
                    conn.execute("COMMIT;")
                    return (
                        Message(
                            message_id=existing_row["message_id"],
                            thread_id=existing_row["thread_id"],
                            conversation_id=existing_row["conversation_id"],
                            connector_id=existing_row["connector_id"],
                            sender=existing_row["sender"],
                            recipient=existing_row["recipient"],
                            message_type=existing_row["message_type"],
                            reply_to=existing_row["reply_to"],
                            artifact_id=existing_row["artifact_id"],
                            content=existing_row["content"],
                            metadata=existing_meta,
                            status=existing_row["status"],
                            created_at=existing_row["created_at"],
                        ),
                        False,
                    )

                # Validate reply_to hierarchy if present
                if rep_to:
                    parent_row = conn.execute(
                        "SELECT thread_id FROM messages WHERE message_id = ?", (rep_to,)
                    ).fetchone()
                    if not parent_row:
                        raise ThreadIntegrityError(
                            f"Parent message '{rep_to}' not found for reply"
                        )
                    if parent_row["thread_id"] != t_id:
                        raise ThreadIntegrityError(
                            f"Cross-thread reply rejected: parent is in thread '{parent_row['thread_id']}', not '{t_id}'"
                        )

                # Insert new message
                conn.execute(
                    """
                    INSERT INTO messages (
                        message_id, thread_id, conversation_id, connector_id,
                        sender, recipient, message_type, reply_to, artifact_id,
                        content, metadata, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m_id,
                        t_id,
                        conv_id,
                        conn_id,
                        snd,
                        rcp,
                        m_type,
                        rep_to,
                        art_id,
                        content,
                        meta_json,
                        status,
                        now,
                    ),
                )

                # Emit REQUEST_CREATED or MESSAGE_CREATED event in the same transaction
                event_type = (
                    "REQUEST_CREATED" if m_type == "review.request" else "MESSAGE_CREATED"
                )
                event_payload = json.dumps(
                    {
                        "message_id": m_id,
                        "conversation_id": conv_id,
                        "connector_id": conn_id,
                        "message_type": m_type,
                        "sender": snd,
                        "recipient": rcp,
                        "artifact_id": art_id,
                    },
                    sort_keys=True,
                )

                conn.execute(
                    """
                    INSERT INTO events (thread_id, message_id, connector_id, event_type, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (t_id, m_id, conn_id, event_type, event_payload, now),
                )

                conn.execute(
                    "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
                    (now, t_id),
                )

                conn.execute("COMMIT;")
                return (
                    Message(
                        message_id=m_id,
                        thread_id=t_id,
                        conversation_id=conv_id,
                        connector_id=conn_id,
                        sender=snd,
                        recipient=rcp,
                        message_type=m_type,
                        reply_to=rep_to,
                        artifact_id=art_id,
                        content=content,
                        metadata=meta,
                        status=status,
                        created_at=now,
                    ),
                    True,
                )
            except BaseException:
                conn.execute("ROLLBACK;")
                raise

    def get_message(self, message_id: str) -> Message | None:
        m_id = message_id.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM messages WHERE message_id = ?", (m_id,)
            ).fetchone()
            if not row:
                return None
            try:
                meta = json.loads(row["metadata"])
            except Exception:
                meta = {}
            return Message(
                message_id=row["message_id"],
                thread_id=row["thread_id"],
                conversation_id=row["conversation_id"],
                connector_id=row["connector_id"],
                sender=row["sender"],
                recipient=row["recipient"],
                message_type=row["message_type"],
                reply_to=row["reply_to"],
                artifact_id=row["artifact_id"],
                content=row["content"],
                metadata=meta,
                status=row["status"],
                created_at=row["created_at"],
            )

    # -------------------------------------------------------------------------
    # Atomic Send Claim Operations
    # -------------------------------------------------------------------------

    def try_claim_external_send(
        self, request_id: str, thread_id: str, claimed_by: str
    ) -> bool:
        """Atomically attempt to acquire the external-send claim for an authoritative request.

        Validates:
        - request exists in DB
        - request belongs to thread_id
        - request.message_type == 'review.request'

        Returns True if acquired (first contender), False if already claimed.
        Raises ThreadIntegrityError or ConflictError on invalid/mismatched requests.
        """
        req_id = request_id.strip()
        t_id = thread_id.strip()
        worker = claimed_by.strip()
        now = time.time()

        if not req_id or not t_id or not worker:
            raise ValueError("request_id, thread_id, and claimed_by must be non-empty")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                # 1. Validate real authoritative request
                req_row = conn.execute(
                    "SELECT thread_id, message_type FROM messages WHERE message_id = ?",
                    (req_id,),
                ).fetchone()

                if not req_row:
                    raise ThreadIntegrityError(
                        f"Cannot claim external send: request '{req_id}' does not exist"
                    )
                if req_row["thread_id"] != t_id:
                    raise ThreadIntegrityError(
                        f"Cannot claim external send: request '{req_id}' belongs to thread '{req_row['thread_id']}', not '{t_id}'"
                    )
                if req_row["message_type"] != "review.request":
                    raise ConflictError(
                        f"Cannot claim external send: message '{req_id}' is of type '{req_row['message_type']}', not 'review.request'"
                    )

                # 2. Atomic claim via primary key insertion
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO send_claims (request_id, thread_id, claimed_by, claimed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (req_id, t_id, worker, now),
                )
                acquired = cursor.rowcount == 1
                conn.execute("COMMIT;")
                return acquired
            except BaseException:
                conn.execute("ROLLBACK;")
                raise

    def get_send_claim(self, request_id: str) -> SendClaim | None:
        req_id = request_id.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT request_id, thread_id, claimed_by, claimed_at FROM send_claims WHERE request_id = ?",
                (req_id,),
            ).fetchone()
            if not row:
                return None
            return SendClaim(
                request_id=row["request_id"],
                thread_id=row["thread_id"],
                claimed_by=row["claimed_by"],
                claimed_at=row["claimed_at"],
            )

    # -------------------------------------------------------------------------
    # Durable Connector Cursor Operations
    # -------------------------------------------------------------------------

    def get_connector_cursor(self, connector_id: str) -> ConnectorCursor | None:
        conn_id = connector_id.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT connector_id, last_processed_event_id, updated_at FROM connector_cursors WHERE connector_id = ?",
                (conn_id,),
            ).fetchone()
            if not row:
                return None
            return ConnectorCursor(
                connector_id=row["connector_id"],
                last_processed_event_id=row["last_processed_event_id"],
                updated_at=row["updated_at"],
            )

    def advance_connector_cursor(
        self, connector_id: str, last_processed_event_id: int, durable_outcome: str
    ) -> ConnectorCursor:
        """Advance connector cursor monotonically after durable handling outcome.

        Validates:
        - durable_outcome is non-empty
        - if last_processed_event_id > 0: event exists and matches connector_id
        - cursor cannot move backwards (enforced atomically in DB)
        """
        conn_id = connector_id.strip()
        outcome = durable_outcome.strip()
        if not conn_id:
            raise ValueError("connector_id must be non-empty")
        if not outcome:
            raise ValueError("durable_outcome must be non-empty")
        if last_processed_event_id < 0:
            raise ValueError("last_processed_event_id must be >= 0")

        now = time.time()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                # Validate referenced event if > 0
                if last_processed_event_id > 0:
                    ev_row = conn.execute(
                        "SELECT event_id, connector_id FROM events WHERE event_id = ?",
                        (last_processed_event_id,),
                    ).fetchone()
                    if not ev_row:
                        raise CursorError(
                            f"Referenced event {last_processed_event_id} does not exist"
                        )
                    if ev_row["connector_id"] != conn_id:
                        raise CursorError(
                            f"Event {last_processed_event_id} belongs to connector '{ev_row['connector_id']}', not '{conn_id}'"
                        )

                # Fetch current cursor
                row = conn.execute(
                    "SELECT last_processed_event_id FROM connector_cursors WHERE connector_id = ?",
                    (conn_id,),
                ).fetchone()

                if row:
                    current_event_id = row["last_processed_event_id"]
                    if last_processed_event_id < current_event_id:
                        raise CursorError(
                            f"Cannot move cursor backwards: current={current_event_id}, attempted={last_processed_event_id}"
                        )
                    conn.execute(
                        "UPDATE connector_cursors SET last_processed_event_id = ?, updated_at = ? WHERE connector_id = ? AND last_processed_event_id <= ?",
                        (last_processed_event_id, now, conn_id, last_processed_event_id),
                    )
                else:
                    conn.execute(
                        "INSERT INTO connector_cursors (connector_id, last_processed_event_id, updated_at) VALUES (?, ?, ?)",
                        (conn_id, last_processed_event_id, now),
                    )

                # Fetch the committed cursor value
                cur_row = conn.execute(
                    "SELECT connector_id, last_processed_event_id, updated_at FROM connector_cursors WHERE connector_id = ?",
                    (conn_id,),
                ).fetchone()

                conn.execute("COMMIT;")
                return ConnectorCursor(
                    connector_id=cur_row["connector_id"],
                    last_processed_event_id=cur_row["last_processed_event_id"],
                    updated_at=cur_row["updated_at"],
                )
            except BaseException:
                conn.execute("ROLLBACK;")
                raise

    # -------------------------------------------------------------------------
    # Transactional Exactly-Once RESPONSE_READY Response Generation
    # -------------------------------------------------------------------------

    def create_response_and_ready_event(
        self,
        thread_id: str,
        response_id: str,
        request_id: str,
        conversation_id: str,
        connector_id: str,
        sender: str,
        recipient: str,
        content: str,
        artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        verdict: str = "APPROVE",
    ) -> tuple[Message, Event, bool]:
        """Atomically create a review.response message and its matching RESPONSE_READY event.

        Validates exact binding against authoritative request:
        - request exists in DB
        - request.message_type == 'review.request'
        - request.thread_id == thread_id
        - request.conversation_id == conversation_id
        - request.connector_id == connector_id
        - request.artifact_id == artifact_id (exact equality)

        Returns (response_message, ready_event, is_new).
        - If a response already exists for this request_id: returns existing (Message, Event, False).
        - If absent: atomically inserts message + event and returns (Message, Event, True).
        """
        t_id = thread_id.strip()
        resp_id = response_id.strip()
        req_id = request_id.strip()
        conv_id = conversation_id.strip()
        conn_id = connector_id.strip()
        snd = sender.strip()
        rcp = recipient.strip()
        art_id = artifact_id.strip() if artifact_id else None
        meta = metadata if metadata is not None else {}
        meta_json = json.dumps(meta, sort_keys=True)
        now = time.time()

        if not t_id or not resp_id or not req_id:
            raise ValueError("thread_id, response_id, and request_id must be non-empty")
        if not conv_id or not conn_id:
            raise ValueError("conversation_id and connector_id must be non-empty")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                # 1. Validate authoritative request binding
                req_row = conn.execute(
                    "SELECT thread_id, conversation_id, connector_id, message_type, artifact_id FROM messages WHERE message_id = ?",
                    (req_id,),
                ).fetchone()

                if not req_row:
                    raise ThreadIntegrityError(f"Authoritative request '{req_id}' not found")
                if req_row["message_type"] != "review.request":
                    raise ConflictError(
                        f"Referenced message '{req_id}' is of type '{req_row['message_type']}', not 'review.request'"
                    )
                if req_row["thread_id"] != t_id:
                    raise ThreadIntegrityError(
                        f"Cross-thread response rejected: request is in thread '{req_row['thread_id']}', not '{t_id}'"
                    )
                if req_row["conversation_id"] != conv_id:
                    raise ConflictError(
                        f"Conversation mismatch: request is bound to '{req_row['conversation_id']}', caller provided '{conv_id}'"
                    )
                if req_row["connector_id"] != conn_id:
                    raise ConflictError(
                        f"Connector mismatch: request is bound to '{req_row['connector_id']}', caller provided '{conn_id}'"
                    )
                if req_row["artifact_id"] != art_id:
                    raise ConflictError(
                        f"Artifact mismatch: request is bound to '{req_row['artifact_id']}', caller provided '{art_id}'"
                    )

                # 2. Check if response for this request_id already exists in thread
                existing_resp = conn.execute(
                    "SELECT * FROM messages WHERE reply_to = ? AND message_type = 'review.response'",
                    (req_id,),
                ).fetchone()

                if existing_resp:
                    # Fetch matching RESPONSE_READY event
                    ev_row = conn.execute(
                        "SELECT * FROM events WHERE message_id = ? AND event_type = 'RESPONSE_READY'",
                        (existing_resp["message_id"],),
                    ).fetchone()

                    try:
                        ex_meta = json.loads(existing_resp["metadata"])
                    except Exception:
                        ex_meta = {}

                    try:
                        ev_payload = json.loads(ev_row["payload"]) if ev_row else {}
                    except Exception:
                        ev_payload = {}

                    resp_msg = Message(
                        message_id=existing_resp["message_id"],
                        thread_id=existing_resp["thread_id"],
                        conversation_id=existing_resp["conversation_id"],
                        connector_id=existing_resp["connector_id"],
                        sender=existing_resp["sender"],
                        recipient=existing_resp["recipient"],
                        message_type=existing_resp["message_type"],
                        reply_to=existing_resp["reply_to"],
                        artifact_id=existing_resp["artifact_id"],
                        content=existing_resp["content"],
                        metadata=ex_meta,
                        status=existing_resp["status"],
                        created_at=existing_resp["created_at"],
                    )

                    ready_event = Event(
                        event_id=ev_row["event_id"] if ev_row else 0,
                        thread_id=existing_resp["thread_id"],
                        message_id=existing_resp["message_id"],
                        connector_id=existing_resp["connector_id"],
                        event_type="RESPONSE_READY",
                        payload=ev_payload,
                        created_at=ev_row["created_at"] if ev_row else existing_resp["created_at"],
                    )

                    conn.execute("COMMIT;")
                    return (resp_msg, ready_event, False)

                # 3. Insert response message
                conn.execute(
                    """
                    INSERT INTO messages (
                        message_id, thread_id, conversation_id, connector_id,
                        sender, recipient, message_type, reply_to, artifact_id,
                        content, metadata, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'review.response', ?, ?, ?, ?, 'COMPLETED', ?)
                    """,
                    (
                        resp_id,
                        t_id,
                        conv_id,
                        conn_id,
                        snd,
                        rcp,
                        req_id,
                        art_id,
                        content,
                        meta_json,
                        now,
                    ),
                )

                # 4. Insert matching RESPONSE_READY event
                ready_payload_dict = {
                    "request_id": req_id,
                    "response_id": resp_id,
                    "conversation_id": conv_id,
                    "connector_id": conn_id,
                    "verdict": verdict,
                    "artifact_id": art_id,
                }
                ready_payload_json = json.dumps(ready_payload_dict, sort_keys=True)

                cursor = conn.execute(
                    """
                    INSERT INTO events (thread_id, message_id, connector_id, event_type, payload, created_at)
                    VALUES (?, ?, ?, 'RESPONSE_READY', ?, ?)
                    """,
                    (t_id, resp_id, conn_id, ready_payload_json, now),
                )
                event_id = cursor.lastrowid

                conn.execute(
                    "UPDATE threads SET updated_at = ? WHERE thread_id = ?",
                    (now, t_id),
                )

                conn.execute("COMMIT;")

                resp_msg = Message(
                    message_id=resp_id,
                    thread_id=t_id,
                    conversation_id=conv_id,
                    connector_id=conn_id,
                    sender=snd,
                    recipient=rcp,
                    message_type="review.response",
                    reply_to=req_id,
                    artifact_id=art_id,
                    content=content,
                    metadata=meta,
                    status="COMPLETED",
                    created_at=now,
                )

                ready_event = Event(
                    event_id=event_id,
                    thread_id=t_id,
                    message_id=resp_id,
                    connector_id=conn_id,
                    event_type="RESPONSE_READY",
                    payload=ready_payload_dict,
                    created_at=now,
                )

                return (resp_msg, ready_event, True)
            except sqlite3.IntegrityError:
                # Concurrent race condition caught by UNIQUE INDEX on reply_to
                conn.execute("ROLLBACK;")
                # Re-fetch the winning response in a clean transaction
                with self._connect() as refetch_conn:
                    existing_resp = refetch_conn.execute(
                        "SELECT * FROM messages WHERE reply_to = ? AND message_type = 'review.response'",
                        (req_id,),
                    ).fetchone()
                    if existing_resp:
                        ev_row = refetch_conn.execute(
                            "SELECT * FROM events WHERE message_id = ? AND event_type = 'RESPONSE_READY'",
                            (existing_resp["message_id"],),
                        ).fetchone()
                        try:
                            ex_meta = json.loads(existing_resp["metadata"])
                        except Exception:
                            ex_meta = {}
                        try:
                            ev_payload = json.loads(ev_row["payload"]) if ev_row else {}
                        except Exception:
                            ev_payload = {}
                        return (
                            Message(
                                message_id=existing_resp["message_id"],
                                thread_id=existing_resp["thread_id"],
                                conversation_id=existing_resp["conversation_id"],
                                connector_id=existing_resp["connector_id"],
                                sender=existing_resp["sender"],
                                recipient=existing_resp["recipient"],
                                message_type=existing_resp["message_type"],
                                reply_to=existing_resp["reply_to"],
                                artifact_id=existing_resp["artifact_id"],
                                content=existing_resp["content"],
                                metadata=ex_meta,
                                status=existing_resp["status"],
                                created_at=existing_resp["created_at"],
                            ),
                            Event(
                                event_id=ev_row["event_id"] if ev_row else 0,
                                thread_id=existing_resp["thread_id"],
                                message_id=existing_resp["message_id"],
                                connector_id=existing_resp["connector_id"],
                                event_type="RESPONSE_READY",
                                payload=ev_payload,
                                created_at=ev_row["created_at"] if ev_row else existing_resp["created_at"],
                            ),
                            False,
                        )
                raise
            except BaseException:
                conn.execute("ROLLBACK;")
                raise

    # -------------------------------------------------------------------------
    # Event Query Operations (for M1 tests and future M2 consumers)
    # -------------------------------------------------------------------------

    def get_events(
        self,
        thread_id: str | None = None,
        connector_id: str | None = None,
        after_id: int = 0,
        limit: int = 100,
    ) -> list[Event]:
        query = "SELECT * FROM events WHERE event_id > ?"
        params: list[Any] = [after_id]

        if thread_id:
            query += " AND thread_id = ?"
            params.append(thread_id.strip())

        if connector_id:
            query += " AND connector_id = ?"
            params.append(connector_id.strip())

        query += " ORDER BY event_id ASC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            results: list[Event] = []
            for row in rows:
                try:
                    payload = json.loads(row["payload"])
                except Exception:
                    payload = {}
                results.append(
                    Event(
                        event_id=row["event_id"],
                        thread_id=row["thread_id"],
                        message_id=row["message_id"],
                        connector_id=row["connector_id"],
                        event_type=row["event_type"],
                        payload=payload,
                        created_at=row["created_at"],
                    )
                )
            return results
