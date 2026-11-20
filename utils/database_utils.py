import os
import json
import sqlite3
import logging
import threading
from datetime import datetime, timezone

from utils.utils import get_chatbot_data_dir

_pg_pool = None
_oracle_pool = None
_local = threading.local()

def get_sqlite_path():
    """
    Returns the path to the SQLite database, ensuring the directory exists.
    """
    db_dir = os.path.join(get_chatbot_data_dir(), "conversations_history")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "history.db")

def get_sqlite_conn():
    """
    Returns a thread-local SQLite connection enabling WAL mode and busy timeout
    to allow concurrent reads and writes across threads without transaction collisions.
    """
    conn = getattr(_local, "sqlite_conn", None)
    if conn is None:
        sqlite_path = get_sqlite_path()
        conn = sqlite3.connect(sqlite_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        _local.sqlite_conn = conn
    return conn

def _get_normalized_pg_uri():
    """
    Fetches the PostgreSQL connection string and normalizes it for psycopg3.
    """
    uri = os.getenv("POSTGRESQL_DATABASE_CONNECTION_STRING")
    if not uri:
        raise ValueError("POSTGRESQL_DATABASE_CONNECTION_STRING is not set.")

    if uri.startswith("postgresql+psycopg2://") or uri.startswith("postgresql+psycopg://"):
        uri = uri.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
    return uri

def get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        from psycopg_pool import ConnectionPool

        uri = _get_normalized_pg_uri()

        try:
            from psycopg.conninfo import make_conninfo
            make_conninfo(uri)
        except Exception as e:
            raise ValueError(f"Invalid PostgreSQL connection string syntax: {e}") from e

        _pg_pool = ConnectionPool(conninfo=uri)
    return _pg_pool

def get_oracle_pool():
    global _oracle_pool
    if _oracle_pool is None:
        import oracledb

        dsn = os.getenv("ORACLE_DATABASE_DSN")
        user = os.getenv("ORACLE_DATABASE_USERNAME")
        password = os.getenv("ORACLE_DATABASE_PASSWORD")
        if not all([dsn, user, password]):
            raise ValueError(
                "Oracle connection parameters (ORACLE_DATABASE_DSN, ORACLE_DATABASE_USERNAME, ORACLE_DATABASE_PASSWORD) are not fully set."
            )

        # Return CLOB/NCLOB as str (and BLOB as bytes) so callers can treat
        # Oracle text columns like SQLite/Postgres TEXT without LOB handling.
        oracledb.defaults.fetch_lobs = False
        _oracle_pool = oracledb.create_pool(user=user, password=password, dsn=dsn, min=2, max=10, increment=1, ping_interval=0)
    return _oracle_pool

class UniformCheckpointer:
    @staticmethod
    def get_saver():
        provider = os.getenv("CHATBOT_DATABASE_PROVIDER", "SQLite").upper()

        if provider == "SQLITE":
            from langgraph.checkpoint.sqlite import SqliteSaver

            conn = get_sqlite_conn()
            saver = SqliteSaver(conn)
            saver.setup()
            return saver

        elif provider == "POSTGRESQL":
            from langgraph.checkpoint.postgres import PostgresSaver
            import psycopg

            uri = _get_normalized_pg_uri()

            try:
                with psycopg.connect(uri, autocommit=True) as conn:
                    PostgresSaver(conn).setup()
            except Exception as e:
                logging.warning(f"Warning initializing tables in PostgresSaver: {e}")

            pool = get_pg_pool()
            return PostgresSaver(pool)

        elif provider == "ORACLE":
            from langgraph_oracledb.checkpoint.oracle import OracleSaver

            pool = get_oracle_pool()
            saver = OracleSaver(pool)
            try:
                saver.setup()
            except Exception as e:
                logging.warning(f"Warning initializing tables in OracleSaver: {e}")

            return saver
        else:
            raise ValueError(f"Chat history provider not supported: {provider}")

class UserSkills:
    """
    Storage for personal skills and per-user skill activation preferences.

    Personal skills are created/uploaded by a user and only visible to that
    user; they live in the same database as the conversation history.
    System skills (the on-disk skills/ folder) are visible to everyone.
    Activation is per (user, agent, skill) via user_skill_prefs — the same
    skill can be active in one agent's settings and inactive in another's.
    """

    @staticmethod
    def _get_connection():
        return HistoryMetadata._get_connection()

    @staticmethod
    def _execute(sql, params=(), fetch=None):
        """
        Run a statement written with placeholders, adapting
        the params to the active provider. fetch: None | 'one' | 'all'.
        Returns fetched rows (or rowcount for writes).
        """
        conn_obj, provider = UserSkills._get_connection()
        if not conn_obj:
            return None

        if provider == "SQLITE":
            cursor = conn_obj.execute(sql, params)
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            else:
                result = cursor.rowcount
            conn_obj.commit()
            return result

        elif provider == "POSTGRESQL":
            pg_sql = sql.replace("?", "%s")
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_sql, params)
                    if fetch == "one":
                        result = cur.fetchone()
                    elif fetch == "all":
                        result = cur.fetchall()
                    else:
                        result = cur.rowcount
                conn.commit()
                return result

        elif provider == "ORACLE":
            oracle_sql = sql
            index = 1
            while "?" in oracle_sql:
                oracle_sql = oracle_sql.replace("?", f":{index}", 1)
                index += 1
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(oracle_sql, list(params))
                    if fetch == "one":
                        result = cur.fetchone()
                    elif fetch == "all":
                        result = cur.fetchall()
                    else:
                        result = cur.rowcount
                conn.commit()
                return result

        return None

    @staticmethod
    def init_db():
        conn_obj, provider = UserSkills._get_connection()
        if not conn_obj:
            return

        if provider == "SQLITE":
            conn_obj.execute("""
                CREATE TABLE IF NOT EXISTS user_skills (
                    user_id TEXT,
                    skill_name TEXT,
                    content TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, skill_name)
                )
            """)
            conn_obj.execute("""
                CREATE TABLE IF NOT EXISTS user_skill_prefs (
                    user_id TEXT,
                    agent_id TEXT,
                    skill_name TEXT,
                    active INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, agent_id, skill_name)
                )
            """)
            conn_obj.commit()

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_skills (
                            user_id TEXT,
                            skill_name TEXT,
                            content TEXT,
                            active INTEGER DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, skill_name)
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_skill_prefs (
                            user_id TEXT,
                            agent_id TEXT,
                            skill_name TEXT,
                            active INTEGER DEFAULT 1,
                            PRIMARY KEY (user_id, agent_id, skill_name)
                        )
                    """)
                conn.commit()

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    for ddl in (
                        """
                        CREATE TABLE user_skills (
                            user_id VARCHAR2(255),
                            skill_name VARCHAR2(255),
                            content CLOB,
                            active NUMBER(1) DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, skill_name)
                        )
                        """,
                        """
                        CREATE TABLE user_skill_prefs (
                            user_id VARCHAR2(255),
                            agent_id VARCHAR2(255),
                            skill_name VARCHAR2(255),
                            active NUMBER(1) DEFAULT 1,
                            PRIMARY KEY (user_id, agent_id, skill_name)
                        )
                        """,
                    ):
                        try:
                            cur.execute(ddl)
                        except Exception as e:
                            if "ORA-00955" not in str(e):
                                raise
                conn.commit()

    # -- Personal skills ------------------------------------------------

    @staticmethod
    def list_personal(user_id):
        rows = UserSkills._execute(
            """
            SELECT skill_name, content, active, created_at, updated_at
            FROM user_skills WHERE user_id = ? ORDER BY skill_name
            """,
            (user_id,),
            fetch="all",
        ) or []
        return [
            {
                "skill_name": row[0],
                "content": row[1],
                "active": bool(row[2]),
                "created_at": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]

    @staticmethod
    def get_personal(user_id, skill_name):
        row = UserSkills._execute(
            "SELECT content, active FROM user_skills WHERE user_id = ? AND skill_name = ?",
            (user_id, skill_name),
            fetch="one",
        )
        if not row:
            return None
        return {"content": row[0], "active": bool(row[1])}

    @staticmethod
    def create_personal(user_id, skill_name, content):
        """Create a personal skill. Returns False if it already exists."""
        if UserSkills.get_personal(user_id, skill_name) is not None:
            return False
        UserSkills._execute(
            "INSERT INTO user_skills (user_id, skill_name, content, active) VALUES (?, ?, ?, 1)",
            (user_id, skill_name, content),
        )
        return True

    @staticmethod
    def update_personal(user_id, skill_name, content):
        """Update a personal skill's content. Returns False if it does not exist."""
        count = UserSkills._execute(
            """
            UPDATE user_skills SET content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND skill_name = ?
            """,
            (content, user_id, skill_name),
        )
        return bool(count)

    @staticmethod
    def delete_personal(user_id, skill_name):
        count = UserSkills._execute(
            "DELETE FROM user_skills WHERE user_id = ? AND skill_name = ?",
            (user_id, skill_name),
        )
        if count:
            UserSkills._execute(
                "DELETE FROM user_skill_prefs WHERE user_id = ? AND skill_name = ?",
                (user_id, skill_name),
            )
        return bool(count)

    # -- Skill activation preferences (per user, per agent) --------------

    @staticmethod
    def get_prefs(user_id, agent_id):
        """Return {skill_name: active} the user has toggled for this agent.

        Skills without a row default to active. Covers both system and
        personal skills.
        """
        rows = UserSkills._execute(
            "SELECT skill_name, active FROM user_skill_prefs WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
            fetch="all",
        ) or []
        return {row[0]: bool(row[1]) for row in rows}

    @staticmethod
    def set_active(user_id, agent_id, skill_name, active):
        value = 1 if active else 0
        count = UserSkills._execute(
            "UPDATE user_skill_prefs SET active = ? WHERE user_id = ? AND agent_id = ? AND skill_name = ?",
            (value, user_id, agent_id, skill_name),
        )
        if not count:
            UserSkills._execute(
                "INSERT INTO user_skill_prefs (user_id, agent_id, skill_name, active) VALUES (?, ?, ?, ?)",
                (user_id, agent_id, skill_name, value),
            )

    @staticmethod
    def clear_agent_prefs(user_id, agent_id):
        """Drop this user's skill toggles for one agent.

        A skill with no row is active, which is the default. Agent-managed
        skills ignore these rows, so clearing them does not change those.
        """
        UserSkills._execute(
            "DELETE FROM user_skill_prefs WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
        )

class UserUiPreferences:
    """
    UI settings that used to live only in the browser.

    One row per user for the profile (scope "user"): what agents should
    know about them, the input method, and the number format.
    One row per user per agent (scope "agent:" plus the agent id) for that
    agent's instructions and LLM / AI SDK options.
    """

    PROFILE_SCOPE = "user"
    _ready = False
    _init_lock = threading.Lock()

    @staticmethod
    def ensure():
        """Create the table once. Later calls skip the lock."""
        if UserUiPreferences._ready:
            return
        with UserUiPreferences._init_lock:
            if UserUiPreferences._ready:
                return
            UserUiPreferences.init_db()
            UserUiPreferences._ready = True

    @staticmethod
    def init_db():
        conn_obj, provider = UserSkills._get_connection()
        if not conn_obj:
            return

        if provider == "SQLITE":
            conn_obj.execute("""
                CREATE TABLE IF NOT EXISTS user_ui_prefs (
                    user_id TEXT,
                    scope TEXT,
                    prefs_json TEXT,
                    PRIMARY KEY (user_id, scope)
                )
            """)
            conn_obj.commit()
        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS user_ui_prefs (
                            user_id TEXT,
                            scope TEXT,
                            prefs_json TEXT,
                            PRIMARY KEY (user_id, scope)
                        )
                    """)
                conn.commit()
        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    try:
                        cur.execute("""
                            CREATE TABLE user_ui_prefs (
                                user_id VARCHAR2(255),
                                scope VARCHAR2(255),
                                prefs_json CLOB,
                                PRIMARY KEY (user_id, scope)
                            )
                        """)
                    except Exception as e:
                        if "ORA-00955" not in str(e):
                            raise
                conn.commit()

    @staticmethod
    def get(user_id, scope):
        UserUiPreferences.ensure()
        row = UserSkills._execute(
            "SELECT prefs_json FROM user_ui_prefs WHERE user_id = ? AND scope = ?",
            (user_id, scope),
            fetch="one",
        )
        if not row or row[0] in (None, ""):
            return {}
        raw = row[0]
        if not isinstance(raw, str):
            raw = str(raw)
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            logging.error(f"Invalid stored prefs_json for user {user_id} scope {scope}")
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def merge(user_id, scope, patch):
        """Replace the named keys on this row and leave the others in place."""
        UserUiPreferences.ensure()
        current = UserUiPreferences.get(user_id, scope)
        for key, value in patch.items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        payload = json.dumps(current)
        exists = UserSkills._execute(
            "SELECT 1 FROM user_ui_prefs WHERE user_id = ? AND scope = ?",
            (user_id, scope),
            fetch="one",
        )
        if exists:
            UserSkills._execute(
                "UPDATE user_ui_prefs SET prefs_json = ? WHERE user_id = ? AND scope = ?",
                (payload, user_id, scope),
            )
        else:
            UserSkills._execute(
                "INSERT INTO user_ui_prefs (user_id, scope, prefs_json) VALUES (?, ?, ?)",
                (user_id, scope, payload),
            )
        return current


def _is_unique_violation(exc):
    """True when an insert collided with a row that already exists."""
    name = type(exc).__name__
    if name in ("IntegrityError", "UniqueViolation"):
        return True
    text = str(exc)
    return "ORA-00001" in text or "UNIQUE constraint failed" in text or "duplicate key" in text.lower()

class UserMemories:
    """
    Durable chatbot memories in the same database as conversation history.

    One row in ``memories`` is one fact. A name is unique for one user,
    across types and agents. ``user`` and ``user-metadata`` are scoped to
    one user on one agent (``agent_id``; the general chat is ``global``).
    ``metadata`` is one fact per user and name, readable and writable from
    every agent of that user. The row keeps the agent that first saved it.
    ``position`` keeps the order of the user-memory index. Each linked
    fact can point at several views, databases, or tags. Those pointers
    are rows in ``memory_links``.
    """

    _SELECT = """
        SELECT user_id, agent_id, memory_type, name, description, body,
               owner, modified, position
        FROM memories
    """

    _LINK_SELECT = """
        SELECT user_id, agent_id, memory_type, name, link_kind, link_name
        FROM memory_links
    """

    @staticmethod
    def _execute(sql, params=(), fetch=None):
        return UserSkills._execute(sql, params, fetch)

    @staticmethod
    def _apply(work):
        """Run ``work(execute)`` in one transaction. ``execute`` matches ``_execute``."""
        conn_obj, provider = UserSkills._get_connection()
        if not conn_obj:
            return None

        if provider == "SQLITE":
            def execute(sql, params=(), fetch=None):
                cursor = conn_obj.execute(sql, params)
                if fetch == "one":
                    return cursor.fetchone()
                if fetch == "all":
                    return cursor.fetchall()
                return cursor.rowcount

            try:
                result = work(execute)
                conn_obj.commit()
                return result
            except Exception:
                conn_obj.rollback()
                raise

        if provider == "POSTGRESQL":
            with conn_obj as conn:
                try:
                    with conn.cursor() as cur:
                        def execute(sql, params=(), fetch=None):
                            cur.execute(sql.replace("?", "%s"), params)
                            if fetch == "one":
                                return cur.fetchone()
                            if fetch == "all":
                                return cur.fetchall()
                            return cur.rowcount

                        result = work(execute)
                    conn.commit()
                    return result
                except Exception:
                    conn.rollback()
                    raise

        if provider == "ORACLE":
            def adapt(sql):
                oracle_sql = sql
                index = 1
                while "?" in oracle_sql:
                    oracle_sql = oracle_sql.replace("?", f":{index}", 1)
                    index += 1
                return oracle_sql

            with conn_obj as conn:
                try:
                    with conn.cursor() as cur:
                        def execute(sql, params=(), fetch=None):
                            cur.execute(adapt(sql), list(params))
                            if fetch == "one":
                                return cur.fetchone()
                            if fetch == "all":
                                return cur.fetchall()
                            return cur.rowcount

                        result = work(execute)
                    conn.commit()
                    return result
                except Exception:
                    conn.rollback()
                    raise

        return None

    @staticmethod
    def _as_records(rows, links_by_key):
        records = []
        for row in rows or []:
            key = (row[0], row[1], row[2], row[3])
            records.append({
                "user_id": row[0],
                "agent_id": row[1],
                "memory_type": row[2],
                "name": row[3],
                "description": row[4],
                "body": row[5] or "",
                "owner": row[6],
                "modified": "" if row[7] is None else str(row[7]),
                "position": int(row[8] or 0),
                "links": links_by_key.get(key, []),
            })
        return records

    @staticmethod
    def _group_links(rows):
        grouped = {}
        seen = {}
        for row in rows or []:
            if not row[4] or not row[5]:
                continue
            key = (row[0], row[1], row[2], row[3])
            marker = (row[4], str(row[5]).casefold())
            bag = seen.setdefault(key, set())
            if marker in bag:
                continue
            bag.add(marker)
            grouped.setdefault(key, []).append({"kind": row[4], "name": row[5]})
        return grouped

    @staticmethod
    def _attach(rows, link_rows):
        return UserMemories._as_records(rows, UserMemories._group_links(link_rows))

    @staticmethod
    def _replace_links(execute, user_id, agent_id, memory_type, name, links):
        execute(
            "DELETE FROM memory_links WHERE user_id = ? AND agent_id = ? AND memory_type = ? AND name = ?",
            (user_id, agent_id, memory_type, name),
        )
        for position, link in enumerate(links or [], start=1):
            execute(
                """
                INSERT INTO memory_links (
                    user_id, agent_id, memory_type, name, link_kind, link_name, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, agent_id, memory_type, name, link["kind"], link["name"], position),
            )

    @staticmethod
    def init_db():
        conn_obj, provider = UserSkills._get_connection()
        if not conn_obj:
            return

        if provider == "SQLITE":
            UserMemories._init_sqlite(conn_obj)
        elif provider == "POSTGRESQL":
            UserMemories._init_postgresql(conn_obj)
        elif provider == "ORACLE":
            UserMemories._init_oracle(conn_obj)

    @staticmethod
    def _create_unique_name_index(execute, sql=None, savepoint=None):
        """One memory name per user. Existing duplicate names are left in place.

        A failed index must not abort the rest of init. PostgreSQL aborts the
        transaction on that failure, so the index runs inside a savepoint there.
        """
        statement = sql or """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_user_name
            ON memories (user_id, name)
        """
        if savepoint:
            execute(f"SAVEPOINT {savepoint}")
        try:
            execute(statement)
        except Exception as exc:
            if savepoint:
                execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            text = str(exc)
            if "ORA-00955" in text or "ORA-01408" in text:
                return
            if (
                "UNIQUE constraint failed" in text
                or "duplicate key" in text.lower()
                or "ORA-01452" in text
            ):
                logging.warning(
                    "Could not add the unique memory-name index because some names are already reused. "
                    "A write that reuses a name is still refused."
                )
                return
            raise
        if savepoint:
            execute(f"RELEASE SAVEPOINT {savepoint}")

    @staticmethod
    def _init_sqlite(conn_obj):
        conn_obj.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT 'global',
                memory_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                body TEXT NOT NULL,
                owner TEXT NOT NULL,
                modified TEXT NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_id, memory_type, name)
            )
        """)
        UserMemories._create_unique_name_index(conn_obj.execute)
        conn_obj.execute("""
            CREATE TABLE IF NOT EXISTS memory_links (
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL DEFAULT 'global',
                memory_type TEXT NOT NULL,
                name TEXT NOT NULL,
                link_kind TEXT NOT NULL,
                link_name TEXT NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_id, memory_type, name, link_kind, link_name)
            )
        """)
        conn_obj.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_links
            ON memory_links (memory_type, link_kind, link_name)
        """)
        conn_obj.execute("""
            CREATE TABLE IF NOT EXISTS user_memory_prefs (
                user_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                active INTEGER NOT NULL,
                PRIMARY KEY (user_id, agent_id)
            )
        """)
        conn_obj.commit()

    @staticmethod
    def _init_postgresql(conn_obj):
        with conn_obj as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        user_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL DEFAULT 'global',
                        memory_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        body TEXT NOT NULL,
                        owner TEXT NOT NULL,
                        modified TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        PRIMARY KEY (user_id, agent_id, memory_type, name)
                    )
                """)
                UserMemories._create_unique_name_index(cur.execute, savepoint="memories_name_index")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memory_links (
                        user_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL DEFAULT 'global',
                        memory_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        link_kind TEXT NOT NULL,
                        link_name TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        PRIMARY KEY (user_id, agent_id, memory_type, name, link_kind, link_name)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_memory_links
                    ON memory_links (memory_type, link_kind, link_name)
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_memory_prefs (
                        user_id TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        active INTEGER NOT NULL,
                        PRIMARY KEY (user_id, agent_id)
                    )
                """)
            conn.commit()

    @staticmethod
    def _oracle_ignoring_exists(cur, ddl):
        try:
            cur.execute(ddl)
        except Exception as e:
            message = str(e)
            if "ORA-00955" not in message and "ORA-01408" not in message:
                raise

    @staticmethod
    def _init_oracle(conn_obj):
        with conn_obj as conn:
            with conn.cursor() as cur:
                UserMemories._oracle_ignoring_exists(cur, """
                    CREATE TABLE memories (
                        user_id VARCHAR2(255) NOT NULL,
                        agent_id VARCHAR2(255) DEFAULT 'global' NOT NULL,
                        memory_type VARCHAR2(32) NOT NULL,
                        name VARCHAR2(64) NOT NULL,
                        description CLOB NOT NULL,
                        body CLOB NOT NULL,
                        owner VARCHAR2(255) NOT NULL,
                        modified VARCHAR2(40) NOT NULL,
                        position NUMBER NOT NULL,
                        PRIMARY KEY (user_id, agent_id, memory_type, name)
                    )
                """)
                UserMemories._create_unique_name_index(
                    cur.execute,
                    """
                    CREATE UNIQUE INDEX idx_memories_user_name
                    ON memories (user_id, name)
                    """,
                )
                UserMemories._oracle_ignoring_exists(cur, """
                    CREATE TABLE memory_links (
                        user_id VARCHAR2(255) NOT NULL,
                        agent_id VARCHAR2(255) DEFAULT 'global' NOT NULL,
                        memory_type VARCHAR2(32) NOT NULL,
                        name VARCHAR2(64) NOT NULL,
                        link_kind VARCHAR2(32) NOT NULL,
                        link_name VARCHAR2(1024) NOT NULL,
                        position NUMBER NOT NULL,
                        PRIMARY KEY (user_id, agent_id, memory_type, name, link_kind, link_name)
                    )
                """)
                UserMemories._oracle_ignoring_exists(cur, """
                    CREATE INDEX idx_memory_links
                    ON memory_links (memory_type, link_kind, link_name)
                """)
                UserMemories._oracle_ignoring_exists(cur, """
                    CREATE TABLE user_memory_prefs (
                        user_id VARCHAR2(255) NOT NULL,
                        agent_id VARCHAR2(255) NOT NULL,
                        active NUMBER(1) DEFAULT 1 NOT NULL,
                        PRIMARY KEY (user_id, agent_id)
                    )
                """)
            conn.commit()

    @staticmethod
    def list_for_user(user_id, agent_id, memory_type):
        rows = UserMemories._execute(
            UserMemories._SELECT + " WHERE user_id = ? AND agent_id = ? AND memory_type = ? ORDER BY position, name",
            (user_id, agent_id, memory_type),
            fetch="all",
        )
        link_rows = UserMemories._execute(
            UserMemories._LINK_SELECT + " WHERE user_id = ? AND agent_id = ? AND memory_type = ? ORDER BY position, link_kind, link_name",
            (user_id, agent_id, memory_type),
            fetch="all",
        )
        return UserMemories._attach(rows, link_rows)

    @staticmethod
    def list_type_for_user(user_id, memory_type):
        """Every memory of one type for this user, on every agent."""
        rows = UserMemories._execute(
            UserMemories._SELECT + " WHERE user_id = ? AND memory_type = ? ORDER BY agent_id, position, name",
            (user_id, memory_type),
            fetch="all",
        )
        link_rows = UserMemories._execute(
            UserMemories._LINK_SELECT + " WHERE user_id = ? AND memory_type = ? ORDER BY agent_id, position, link_kind, link_name",
            (user_id, memory_type),
            fetch="all",
        )
        return UserMemories._attach(rows, link_rows)

    @staticmethod
    def list_metadata_for_link(link_kind, link_name):
        rows = UserMemories._execute(
            """
            SELECT m.user_id, m.agent_id, m.memory_type, m.name, m.description, m.body,
                   m.owner, m.modified, m.position
            FROM memories m
            JOIN memory_links l
              ON l.user_id = m.user_id
             AND l.agent_id = m.agent_id
             AND l.memory_type = m.memory_type
             AND l.name = m.name
            WHERE m.memory_type = 'metadata'
              AND l.link_kind = ?
              AND LOWER(l.link_name) = LOWER(?)
            ORDER BY m.modified DESC, m.owner, m.name
            """,
            (link_kind, link_name),
            fetch="all",
        )
        unique = []
        seen = set()
        for row in rows or []:
            # One metadata fact per user and name, even if an older copy
            # still sits on another agent. modified DESC keeps the newest.
            key = (row[0], row[3])
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        if not unique:
            return []
        link_rows = UserMemories._execute(
            """
            SELECT l.user_id, l.agent_id, l.memory_type, l.name, l.link_kind, l.link_name
            FROM memory_links l
            JOIN memory_links matched
              ON matched.user_id = l.user_id
             AND matched.agent_id = l.agent_id
             AND matched.memory_type = l.memory_type
             AND matched.name = l.name
            WHERE l.memory_type = 'metadata'
              AND matched.link_kind = ?
              AND LOWER(matched.link_name) = LOWER(?)
            ORDER BY l.position, l.link_kind, l.link_name
            """,
            (link_kind, link_name),
            fetch="all",
        )
        return UserMemories._attach(unique, link_rows)

    @staticmethod
    def list_metadata_links():
        """Every metadata link, as (kind, name) pairs.

        Two copies of the same user's memory are counted once.
        """
        rows = UserMemories._execute(
            """
            SELECT user_id, name, link_kind, link_name FROM memory_links
            WHERE memory_type = 'metadata'
              AND link_kind IS NOT NULL
              AND link_name IS NOT NULL
            """,
            fetch="all",
        ) or []
        seen = set()
        pairs = []
        for row in rows:
            if not row[2] or not row[3]:
                continue
            marker = (row[0], row[1], row[2], str(row[3]).casefold())
            if marker in seen:
                continue
            seen.add(marker)
            pairs.append((row[2], row[3]))
        return pairs

    @staticmethod
    def next_position(user_id, agent_id, memory_type):
        row = UserMemories._execute(
            "SELECT MAX(position) FROM memories WHERE user_id = ? AND agent_id = ? AND memory_type = ?",
            (user_id, agent_id, memory_type),
            fetch="one",
        )
        if not row or row[0] is None:
            return 1
        return int(row[0]) + 1

    @staticmethod
    def insert(user_id, agent_id, memory_type, name, description, body, links, owner, modified, position):
        """Insert one memory and its links. Returns False when that fact already exists."""
        def work(execute):
            execute(
                """
                INSERT INTO memories (
                    user_id, agent_id, memory_type, name, description, body,
                    owner, modified, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, agent_id, memory_type, name, description, body, owner, modified, position),
            )
            UserMemories._replace_links(execute, user_id, agent_id, memory_type, name, links)

        try:
            UserMemories._apply(work)
            return True
        except Exception as exc:
            if _is_unique_violation(exc):
                return False
            raise

    @staticmethod
    def update(user_id, agent_id, memory_type, name, description, body, links, owner, modified):
        """Replace the text and links of an existing memory. Position stays put."""
        def work(execute):
            count = execute(
                """
                UPDATE memories
                SET description = ?, body = ?, owner = ?, modified = ?
                WHERE user_id = ? AND agent_id = ? AND memory_type = ? AND name = ?
                """,
                (description, body, owner, modified, user_id, agent_id, memory_type, name),
            )
            if not count:
                return 0
            UserMemories._replace_links(execute, user_id, agent_id, memory_type, name, links)
            return count

        return bool(UserMemories._apply(work))

    @staticmethod
    def delete(user_id, agent_id, memory_type, name):
        def work(execute):
            execute(
                "DELETE FROM memory_links WHERE user_id = ? AND agent_id = ? AND memory_type = ? AND name = ?",
                (user_id, agent_id, memory_type, name),
            )
            return execute(
                "DELETE FROM memories WHERE user_id = ? AND agent_id = ? AND memory_type = ? AND name = ?",
                (user_id, agent_id, memory_type, name),
            )

        return bool(UserMemories._apply(work))

    @staticmethod
    def is_enabled(user_id, agent_id):
        """True when this user wants memory formation on for this agent.

        A missing row means on, which is how every agent behaved before the
        switch existed.
        """
        row = UserMemories._execute(
            "SELECT active FROM user_memory_prefs WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
            fetch="one",
        )
        if not row or row[0] is None:
            return True
        return bool(row[0])

    @staticmethod
    def set_enabled(user_id, agent_id, enabled):
        value = 1 if enabled else 0
        count = UserMemories._execute(
            "UPDATE user_memory_prefs SET active = ? WHERE user_id = ? AND agent_id = ?",
            (value, user_id, agent_id),
        )
        if not count:
            try:
                UserMemories._execute(
                    "INSERT INTO user_memory_prefs (user_id, agent_id, active) VALUES (?, ?, ?)",
                    (user_id, agent_id, value),
                )
            except Exception as exc:
                if not _is_unique_violation(exc):
                    raise
                UserMemories._execute(
                    "UPDATE user_memory_prefs SET active = ? WHERE user_id = ? AND agent_id = ?",
                    (value, user_id, agent_id),
                )

class HistoryMetadata:
    @staticmethod
    def _get_connection():
        provider = os.getenv("CHATBOT_DATABASE_PROVIDER", "SQLite").upper()
        if provider == "SQLITE":
            return get_sqlite_conn(), "SQLITE"

        elif provider == "POSTGRESQL":
            pool = get_pg_pool()
            return pool.connection(), "POSTGRESQL"

        elif provider == "ORACLE":
            pool = get_oracle_pool()
            return pool.acquire(), "ORACLE"

        else:
            raise ValueError(f"Chat history provider not supported: {provider}")

    @staticmethod
    def init_db():
        conn_obj, provider = HistoryMetadata._get_connection()
        if not conn_obj:
            return

        if provider == "SQLITE":
            conn_obj.execute("""
                CREATE TABLE IF NOT EXISTS chat_metadata (
                    thread_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    agent_id TEXT,
                    title TEXT,
                    is_pinned INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn_obj.commit()

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chat_metadata (
                            thread_id TEXT PRIMARY KEY,
                            user_id TEXT,
                            agent_id TEXT,
                            title TEXT,
                            is_pinned INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                conn.commit()

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    try:
                        cur.execute("""
                            CREATE TABLE chat_metadata (
                                thread_id VARCHAR2(255) PRIMARY KEY,
                                user_id VARCHAR2(255),
                                agent_id VARCHAR2(255),
                                title VARCHAR2(1000),
                                is_pinned NUMBER(1) DEFAULT 0,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                    except Exception as e:
                        # Filter out the specific Oracle error for "name is already used by an existing object"
                        # Any other exception (like privilege issues) will be raised properly
                        if "ORA-00955" not in str(e):
                            raise
                conn.commit()

    @staticmethod
    def save_new_chat(thread_id, user_id, agent_id, first_query):
        title = (first_query[:30] + "...") if len(first_query) > 30 else first_query

        conn_obj, provider = HistoryMetadata._get_connection()

        if provider == "SQLITE":
            conn_obj.execute(
                """
                INSERT INTO chat_metadata (thread_id, user_id, agent_id, title, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(thread_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
                (thread_id, user_id, agent_id, title),
            )
            conn_obj.commit()

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO chat_metadata (thread_id, user_id, agent_id, title, updated_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (thread_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    """,
                        (thread_id, user_id, agent_id, title),
                    )
                conn.commit()

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        MERGE INTO chat_metadata dest
                        USING (SELECT :1 as thread_id, :2 as user_id, :3 as agent_id, :4 as title FROM dual) src
                        ON (dest.thread_id = src.thread_id)
                        WHEN MATCHED THEN
                            UPDATE SET updated_at = CURRENT_TIMESTAMP
                        WHEN NOT MATCHED THEN
                            INSERT (thread_id, user_id, agent_id, title, updated_at)
                            VALUES (src.thread_id, src.user_id, src.agent_id, src.title, CURRENT_TIMESTAMP)
                    """,
                        [thread_id, user_id, agent_id, title],
                    )
                conn.commit()

    @staticmethod
    def get_user_chats(user_id, limit=20, offset=0, search_query=None):
        conn_obj, provider = HistoryMetadata._get_connection()
        chats = []

        if provider == "SQLITE":
            sql = """
                SELECT thread_id, agent_id, title, is_pinned, created_at, updated_at
                FROM chat_metadata
                WHERE user_id = ?
            """
            params = [user_id]

            if search_query:
                sql += " AND title LIKE ? "
                params.append(f"%{search_query}%")

            sql += " ORDER BY is_pinned DESC, updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = conn_obj.execute(sql, tuple(params))
            for row in cursor.fetchall():
                chats.append(
                    {
                        "thread_id": row[0],
                        "agent_id": row[1],
                        "title": row[2],
                        "is_pinned": bool(row[3]),
                        "created_at": row[4],
                        "updated_at": row[5],
                    }
                )

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    sql = """
                        SELECT thread_id, agent_id, title, is_pinned, created_at, updated_at
                        FROM chat_metadata 
                        WHERE user_id = %s 
                    """
                    params = [user_id]

                    if search_query:
                        sql += " AND title ILIKE %s "
                        params.append(f"%{search_query}%")

                    sql += " ORDER BY is_pinned DESC, updated_at DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])

                    cur.execute(sql, tuple(params))
                    for row in cur.fetchall():
                        chats.append(
                            {
                                "thread_id": row[0],
                                "agent_id": row[1],
                                "title": row[2],
                                "is_pinned": bool(row[3]),
                                "created_at": row[4],
                                "updated_at": row[5],
                            }
                        )

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    sql = """
                        SELECT thread_id, agent_id, title, is_pinned, created_at, updated_at
                        FROM chat_metadata
                        WHERE user_id = :1
                    """
                    params = [user_id]
                    param_index = 2

                    if search_query:
                        sql += f" AND UPPER(title) LIKE UPPER(:{param_index}) "
                        params.append(f"%{search_query}%")
                        param_index += 1

                    sql += f" ORDER BY is_pinned DESC, updated_at DESC OFFSET :{param_index} ROWS FETCH NEXT :{param_index + 1} ROWS ONLY"
                    params.extend([offset, limit])

                    cur.execute(sql, params)
                    for row in cur.fetchall():
                        chats.append(
                            {
                                "thread_id": row[0],
                                "agent_id": row[1],
                                "title": row[2],
                                "is_pinned": bool(row[3]),
                                "created_at": row[4],
                                "updated_at": row[5],
                            }
                        )

        return chats

    @staticmethod
    def chat_exists(thread_id):
        """Checks whether a chat metadata row exists for the given thread_id."""
        conn_obj, provider = HistoryMetadata._get_connection()
        if not conn_obj:
            return False

        exists = False

        if provider == "SQLITE":
            cursor = conn_obj.execute(
                "SELECT 1 FROM chat_metadata WHERE thread_id = ?",
                (thread_id,)
            )
            exists = cursor.fetchone() is not None

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM chat_metadata WHERE thread_id = %s",
                        (thread_id,)
                    )
                    exists = cur.fetchone() is not None

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM chat_metadata WHERE thread_id = :1",
                        [thread_id]
                    )
                    exists = cur.fetchone() is not None

        return exists

    @staticmethod
    def verify_ownership(thread_id, user_id):
        """
        Checks if a specific thread_id belongs to a user_id directly in the DB.
        Returns True if it exists and matches, False otherwise.
        """
        conn_obj, provider = HistoryMetadata._get_connection()
        if not conn_obj:
            return False

        is_owner = False

        if provider == "SQLITE":
            cursor = conn_obj.execute(
                "SELECT 1 FROM chat_metadata WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id)
            )
            is_owner = cursor.fetchone() is not None

        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM chat_metadata WHERE thread_id = %s AND user_id = %s",
                        (thread_id, user_id)
                    )
                    is_owner = cur.fetchone() is not None

        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM chat_metadata WHERE thread_id = :1 AND user_id = :2",
                        [thread_id, user_id]
                    )
                    is_owner = cur.fetchone() is not None

        return is_owner

    @staticmethod
    def rename_chat(thread_id, new_title):
        conn_obj, provider = HistoryMetadata._get_connection()
        if provider == "SQLITE":
            conn_obj.execute(
                "UPDATE chat_metadata SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE thread_id = ?",
                (new_title, thread_id),
            )
            conn_obj.commit()
        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE chat_metadata SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE thread_id = %s",
                        (new_title, thread_id),
                    )
                conn.commit()
        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE chat_metadata SET title = :1, updated_at = CURRENT_TIMESTAMP WHERE thread_id = :2",
                        [new_title, thread_id],
                    )
                conn.commit()

    @staticmethod
    def pin_chat(thread_id, is_pinned):
        conn_obj, provider = HistoryMetadata._get_connection()
        pin_val = 1 if is_pinned else 0

        if provider == "SQLITE":
            conn_obj.execute("UPDATE chat_metadata SET is_pinned = ? WHERE thread_id = ?", (pin_val, thread_id))
            conn_obj.commit()
        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE chat_metadata SET is_pinned = %s WHERE thread_id = %s", (pin_val, thread_id))
                conn.commit()
        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE chat_metadata SET is_pinned = :1 WHERE thread_id = :2", [pin_val, thread_id])
                conn.commit()

    @staticmethod
    def delete_chat(thread_id):
        conn_obj, provider = HistoryMetadata._get_connection()
        if not conn_obj:
            return

        if provider == "SQLITE":
            conn_obj.execute("DELETE FROM chat_metadata WHERE thread_id = ?", (thread_id,))
            conn_obj.commit()
        elif provider == "POSTGRESQL":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_metadata WHERE thread_id = %s", (thread_id,))
                conn.commit()
        elif provider == "ORACLE":
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_metadata WHERE thread_id = :1", [thread_id])
                conn.commit()

        # Delegate the cleanup of LangGraph internal tables to the native saver
        try:
            saver = UniformCheckpointer.get_saver()
            saver.delete_thread(thread_id)
        except Exception as e:
            logging.error(f"Error cleaning up LangGraph history for thread {thread_id}: {e}")



class DeepQueryReports:
    """
    Persistence for DeepQuery analyses and the reports generated from them.

    An analysis (deepquery_analyses) is one execution of the DeepQuery data
    extraction phase and stores the raw deepquery_metadata. A report
    (deepquery_reports) is one HTML rendering of an analysis in a given
    language; several reports (variants) can share the same analysis.
    Timestamps are stored as UTC ISO-8601 strings so every provider behaves
    the same way. Rows are scoped per user and agent.
    """

    ACTIVE_STATUSES = ("PENDING", "PROCESSING")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    @staticmethod
    def _get_connection():
        return HistoryMetadata._get_connection()

    @staticmethod
    def _execute(sql, params=(), fetch=None):
        """
        Run a statement written with '?' placeholders, adapting it to the
        active provider. fetch: None | 'one' | 'all'.
        Returns fetched rows (or rowcount for writes).
        """
        conn_obj, provider = DeepQueryReports._get_connection()
        if not conn_obj:
            return None

        if provider == "SQLITE":
            cursor = conn_obj.execute(sql, params)
            if fetch == "one":
                result = cursor.fetchone()
            elif fetch == "all":
                result = cursor.fetchall()
            else:
                result = cursor.rowcount
            conn_obj.commit()
            return result

        elif provider == "POSTGRESQL":
            pg_sql = sql.replace("?", "%s")
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(pg_sql, params)
                    if fetch == "one":
                        result = cur.fetchone()
                    elif fetch == "all":
                        result = cur.fetchall()
                    else:
                        result = cur.rowcount
                conn.commit()
                return result

        elif provider == "ORACLE":
            oracle_sql = sql
            index = 1
            while "?" in oracle_sql:
                oracle_sql = oracle_sql.replace("?", f":{index}", 1)
                index += 1
            with conn_obj as conn:
                with conn.cursor() as cur:
                    cur.execute(oracle_sql, list(params))
                    if fetch == "one":
                        result = cur.fetchone()
                    elif fetch == "all":
                        result = cur.fetchall()
                    else:
                        result = cur.rowcount
                conn.commit()
                return result

        return None

    @staticmethod
    def init_db():
        conn_obj, provider = DeepQueryReports._get_connection()
        if not conn_obj:
            return

        if provider in ("SQLITE", "POSTGRESQL"):
            statements = [
                """
                CREATE TABLE IF NOT EXISTS deepquery_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    agent_id TEXT,
                    thread_id TEXT,
                    question TEXT,
                    title TEXT,
                    metadata_json TEXT,
                    status TEXT,
                    error TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS deepquery_reports (
                    report_id TEXT PRIMARY KEY,
                    analysis_id TEXT,
                    user_id TEXT,
                    agent_id TEXT,
                    language TEXT,
                    status TEXT,
                    stage TEXT,
                    title TEXT,
                    html TEXT,
                    error TEXT,
                    created_at TEXT,
                    started_at TEXT,
                    completed_at TEXT
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_dqa_user_created ON deepquery_analyses (user_id, created_at)",
                "CREATE INDEX IF NOT EXISTS idx_dqr_user_created ON deepquery_reports (user_id, created_at)",
                "CREATE INDEX IF NOT EXISTS idx_dqr_analysis ON deepquery_reports (analysis_id)",
            ]
            if provider == "SQLITE":
                for ddl in statements:
                    conn_obj.execute(ddl)
                conn_obj.commit()
            else:
                with conn_obj as conn:
                    with conn.cursor() as cur:
                        for ddl in statements:
                            cur.execute(ddl)
                    conn.commit()

        elif provider == "ORACLE":
            statements = [
                """
                CREATE TABLE deepquery_analyses (
                    analysis_id VARCHAR2(64) PRIMARY KEY,
                    user_id VARCHAR2(255),
                    agent_id VARCHAR2(255),
                    thread_id VARCHAR2(255),
                    question CLOB,
                    title VARCHAR2(1000),
                    metadata_json CLOB,
                    status VARCHAR2(20),
                    error CLOB,
                    created_at VARCHAR2(40),
                    updated_at VARCHAR2(40)
                )
                """,
                """
                CREATE TABLE deepquery_reports (
                    report_id VARCHAR2(64) PRIMARY KEY,
                    analysis_id VARCHAR2(64),
                    user_id VARCHAR2(255),
                    agent_id VARCHAR2(255),
                    language VARCHAR2(100),
                    status VARCHAR2(20),
                    stage VARCHAR2(30),
                    title VARCHAR2(1000),
                    html CLOB,
                    error CLOB,
                    created_at VARCHAR2(40),
                    started_at VARCHAR2(40),
                    completed_at VARCHAR2(40)
                )
                """,
                "CREATE INDEX idx_dqa_user_created ON deepquery_analyses (user_id, created_at)",
                "CREATE INDEX idx_dqr_user_created ON deepquery_reports (user_id, created_at)",
                "CREATE INDEX idx_dqr_analysis ON deepquery_reports (analysis_id)",
            ]
            with conn_obj as conn:
                with conn.cursor() as cur:
                    for ddl in statements:
                        try:
                            cur.execute(ddl)
                        except Exception as e:
                            # ORA-00955: name is already used by an existing object
                            if "ORA-00955" not in str(e):
                                raise
                conn.commit()

    # -- Creation ---------------------------------------------------------

    @staticmethod
    def create_analysis(analysis_id, user_id, agent_id, thread_id, question, title=None):
        now = DeepQueryReports._now()
        DeepQueryReports._execute(
            """
            INSERT INTO deepquery_analyses
                (analysis_id, user_id, agent_id, thread_id, question, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
            """,
            (analysis_id, user_id, agent_id, thread_id, question, title, now, now),
        )

    @staticmethod
    def create_report(report_id, analysis_id, user_id, agent_id, language, title=None):
        DeepQueryReports._execute(
            """
            INSERT INTO deepquery_reports
                (report_id, analysis_id, user_id, agent_id, language, status, stage, title, created_at)
            VALUES (?, ?, ?, ?, ?, 'PENDING', 'queued', ?, ?)
            """,
            (report_id, analysis_id, user_id, agent_id, language, title, DeepQueryReports._now()),
        )

    # -- Updates ----------------------------------------------------------

    @staticmethod
    def update_status(report_id, status, stage=None, error=None, title=None, only_if_status=None):
        """
        Update the status of a report. Sets started_at when moving to
        PROCESSING (first time) and completed_at on terminal states.
        If only_if_status (tuple/list) is given the update only applies when
        the current status is one of them, which makes state transitions
        race-safe (e.g. a finished worker cannot overwrite a cancellation).
        Returns the number of rows changed.
        """
        now = DeepQueryReports._now()
        sets = ["status = ?"]
        params = [status]
        if stage is not None:
            sets.append("stage = ?")
            params.append(stage)
        if error is not None:
            sets.append("error = ?")
            params.append(error)
        if title:
            sets.append("title = ?")
            params.append(title)
        if status == "PROCESSING":
            sets.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        elif status in ("COMPLETED", "FAILED", "CANCELLED"):
            sets.append("completed_at = ?")
            params.append(now)

        sql = f"UPDATE deepquery_reports SET {', '.join(sets)} WHERE report_id = ?"
        params.append(report_id)
        if only_if_status:
            sql += f" AND status IN ({', '.join('?' for _ in only_if_status)})"
            params.extend(only_if_status)
        return DeepQueryReports._execute(sql, tuple(params)) or 0

    @staticmethod
    def reset_report(report_id, user_id, only_if_status=("FAILED", "CANCELLED")):
        """
        Put a finished report back in the queue (PENDING) so it can be run again in place.
        Returns the number of rows changed (0 if the report is not in one of only_if_status).
        """
        sql = (
            "UPDATE deepquery_reports SET status = 'PENDING', stage = 'queued', error = NULL, "
            "started_at = NULL, completed_at = NULL, html = NULL "
            "WHERE report_id = ? AND user_id = ?"
        )
        params = [report_id, user_id]
        if only_if_status:
            sql += f" AND status IN ({', '.join('?' for _ in only_if_status)})"
            params.extend(only_if_status)
        return DeepQueryReports._execute(sql, tuple(params)) or 0

    @staticmethod
    def update_analysis_status(analysis_id, status, error=None):
        DeepQueryReports._execute(
            "UPDATE deepquery_analyses SET status = ?, error = ?, updated_at = ? WHERE analysis_id = ?",
            (status, error, DeepQueryReports._now(), analysis_id),
        )

    @staticmethod
    def set_analysis_metadata(analysis_id, metadata, title=None):
        payload = metadata if isinstance(metadata, str) else json.dumps(metadata, default=str)
        DeepQueryReports._execute(
            """
            UPDATE deepquery_analyses
            SET metadata_json = ?, title = COALESCE(?, title), status = 'COMPLETED', error = NULL, updated_at = ?
            WHERE analysis_id = ?
            """,
            (payload, title, DeepQueryReports._now(), analysis_id),
        )

    @staticmethod
    def set_report_html(report_id, html, title=None):
        """
        Store the generated HTML and mark the report COMPLETED, unless it
        was cancelled/failed meanwhile. Returns True if the report was updated.
        """
        count = DeepQueryReports._execute(
            """
            UPDATE deepquery_reports
            SET html = ?, title = COALESCE(?, title), status = 'COMPLETED', stage = 'done',
                error = NULL, completed_at = ?
            WHERE report_id = ? AND status IN ('PENDING', 'PROCESSING')
            """,
            (html, title or None, DeepQueryReports._now(), report_id),
        )
        return bool(count)

    # -- Reads ------------------------------------------------------------

    _REPORT_COLUMNS = (
        "r.report_id, r.analysis_id, r.title, a.title, a.question, r.language, r.status, r.stage, "
        "r.error, r.created_at, r.started_at, r.completed_at, r.user_id, r.agent_id"
    )

    @staticmethod
    def _row_to_report(row):
        question = row[4] or ""
        return {
            "report_id": row[0],
            "analysis_id": row[1],
            "title": row[2] or row[3] or "",
            "question": question[:500],
            "language": row[5],
            "status": row[6],
            "stage": row[7],
            "error": row[8],
            "created_at": row[9],
            "started_at": row[10],
            "completed_at": row[11],
            "user_id": row[12],
            "agent_id": row[13],
        }

    @staticmethod
    def list_reports(user_id, agent_id=None):
        """List a user's reports (newest first) without html or metadata."""
        sql = (
            f"SELECT {DeepQueryReports._REPORT_COLUMNS} FROM deepquery_reports r "
            "LEFT JOIN deepquery_analyses a ON a.analysis_id = r.analysis_id "
            "WHERE r.user_id = ?"
        )
        params = [user_id]
        if agent_id:
            sql += " AND r.agent_id = ?"
            params.append(agent_id)
        sql += " ORDER BY r.created_at DESC"
        rows = DeepQueryReports._execute(sql, tuple(params), fetch="all") or []
        return [DeepQueryReports._row_to_report(row) for row in rows]

    @staticmethod
    def count_reports(user_id):
        """Total number of reports (any status, any agent) a user has."""
        row = DeepQueryReports._execute(
            "SELECT COUNT(*) FROM deepquery_reports WHERE user_id = ?", (user_id,), fetch="one"
        )
        return int(row[0]) if row else 0

    @staticmethod
    def get_report(report_id, user_id=None):
        """Return report information (no html) or None. Enforces ownership if user_id is given."""
        sql = (
            f"SELECT {DeepQueryReports._REPORT_COLUMNS} FROM deepquery_reports r "
            "LEFT JOIN deepquery_analyses a ON a.analysis_id = r.analysis_id "
            "WHERE r.report_id = ?"
        )
        params = [report_id]
        if user_id is not None:
            sql += " AND r.user_id = ?"
            params.append(user_id)
        row = DeepQueryReports._execute(sql, tuple(params), fetch="one")
        return DeepQueryReports._row_to_report(row) if row else None

    @staticmethod
    def get_report_html(report_id, user_id):
        row = DeepQueryReports._execute(
            """
            SELECT r.html, r.title, a.title, r.status
            FROM deepquery_reports r
            LEFT JOIN deepquery_analyses a ON a.analysis_id = r.analysis_id
            WHERE r.report_id = ? AND r.user_id = ?
            """,
            (report_id, user_id),
            fetch="one",
        )
        if not row:
            return None
        return {"html": row[0], "title": row[1] or row[2] or "", "status": row[3]}

    @staticmethod
    def get_analysis(analysis_id, user_id=None):
        """Return {question, title, metadata (dict|None), user_id, agent_id, thread_id, status} or None."""
        sql = (
            "SELECT question, title, metadata_json, user_id, agent_id, thread_id, status "
            "FROM deepquery_analyses WHERE analysis_id = ?"
        )
        params = [analysis_id]
        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)
        row = DeepQueryReports._execute(sql, tuple(params), fetch="one")
        if not row:
            return None
        metadata = None
        if row[2]:
            try:
                metadata = json.loads(row[2])
            except (TypeError, ValueError):
                logging.error(f"Invalid stored deepquery_metadata for analysis {analysis_id}")
        return {
            "question": row[0],
            "title": row[1],
            "metadata": metadata,
            "user_id": row[3],
            "agent_id": row[4],
            "thread_id": row[5],
            "status": row[6],
        }

    @staticmethod
    def get_analysis_report_statuses(analysis_id):
        """Return [(report_id, status)] for every report sharing an analysis."""
        rows = DeepQueryReports._execute(
            "SELECT report_id, status FROM deepquery_reports WHERE analysis_id = ?",
            (analysis_id,),
            fetch="all",
        ) or []
        return [(row[0], row[1]) for row in rows]

    # -- Deletion ---------------------------------------------------------

    @staticmethod
    def _delete_orphan_analyses(user_id, analysis_id=None):
        sql = (
            "DELETE FROM deepquery_analyses WHERE user_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM deepquery_reports r WHERE r.analysis_id = deepquery_analyses.analysis_id)"
        )
        params = [user_id]
        if analysis_id:
            sql += " AND analysis_id = ?"
            params.append(analysis_id)
        DeepQueryReports._execute(sql, tuple(params))

    @staticmethod
    def delete_report(report_id, user_id):
        """Delete a report (and its analysis if no other report uses it). Returns True if deleted."""
        row = DeepQueryReports._execute(
            "SELECT analysis_id FROM deepquery_reports WHERE report_id = ? AND user_id = ?",
            (report_id, user_id),
            fetch="one",
        )
        if not row:
            return False
        count = DeepQueryReports._execute(
            "DELETE FROM deepquery_reports WHERE report_id = ? AND user_id = ?",
            (report_id, user_id),
        )
        DeepQueryReports._delete_orphan_analyses(user_id, row[0])
        return bool(count)

    @staticmethod
    def delete_all(user_id, agent_id=None):
        """Delete all reports of a user (optionally for one agent). Returns the deleted count."""
        sql = "DELETE FROM deepquery_reports WHERE user_id = ?"
        params = [user_id]
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        count = DeepQueryReports._execute(sql, tuple(params)) or 0
        DeepQueryReports._delete_orphan_analyses(user_id)
        return count

    # -- Recovery ---------------------------------------------------------

    @staticmethod
    def fail_stale_jobs(reason="Interrupted by restart"):
        """Mark jobs left PENDING/PROCESSING by a previous process as FAILED. Returns the count."""
        now = DeepQueryReports._now()
        count = DeepQueryReports._execute(
            """
            UPDATE deepquery_reports
            SET status = 'FAILED', stage = 'done', error = ?, completed_at = ?
            WHERE status IN ('PENDING', 'PROCESSING')
            """,
            (reason, now),
        ) or 0
        DeepQueryReports._execute(
            """
            UPDATE deepquery_analyses
            SET status = 'FAILED', error = ?, updated_at = ?
            WHERE status IN ('PENDING', 'PROCESSING')
            """,
            (reason, now),
        )
        if count:
            logging.warning(f"Marked {count} interrupted DeepQuery report job(s) as FAILED")
        return count
