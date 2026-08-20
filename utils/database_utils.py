import os
import sqlite3
import logging

_pg_pool = None
_oracle_pool = None
_sqlite_conn = None

def get_sqlite_path():
    """
    Returns the path to the SQLite database, ensuring the directory exists.
    """
    data_dir = os.getenv("AI_SDK_DATA_DIR", ".")
    db_dir = os.path.join(data_dir, "conversations_history")
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "history.db")

def get_sqlite_conn():
    """
    Returns a global SQLite connection to avoid file descriptor exhaustion,
    enabling WAL mode for concurrent read/writes.
    """
    global _sqlite_conn
    if _sqlite_conn is None:
        sqlite_path = get_sqlite_path()
        _sqlite_conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        _sqlite_conn.execute("PRAGMA journal_mode=WAL;")
    return _sqlite_conn

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
        _oracle_pool = oracledb.create_pool(user=user, password=password, dsn=dsn, min=2, max=10, increment=1)
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
