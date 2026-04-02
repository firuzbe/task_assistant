import sqlite3
from datetime import datetime
from config import DB_FILE

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()


def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bot_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        role TEXT DEFAULT 'user',
        authorized INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_text TEXT NOT NULL,
        deadline TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        created_by INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS task_assignees (
        task_id INTEGER NOT NULL,
        employee_id INTEGER NOT NULL
    )
    """)

    conn.commit()


# --- USERS ---
def get_bot_user(telegram_id: int):
    cursor.execute("SELECT * FROM bot_users WHERE telegram_id=?", (telegram_id,))
    return cursor.fetchone()


def create_bot_user(telegram_id: int):
    cursor.execute("INSERT OR IGNORE INTO bot_users (telegram_id) VALUES (?)", (telegram_id,))
    conn.commit()


def set_authorized(telegram_id: int, authorized: bool):
    cursor.execute(
        "UPDATE bot_users SET authorized=? WHERE telegram_id=?",
        (1 if authorized else 0, telegram_id)
    )
    conn.commit()


def is_authorized(telegram_id: int) -> bool:
    user = get_bot_user(telegram_id)
    return user and user["authorized"] == 1


def get_role(telegram_id: int) -> str:
    user = get_bot_user(telegram_id)
    if not user:
        return "user"
    return user["role"]


def ensure_admin(telegram_id: int):
    cursor.execute("SELECT * FROM bot_users WHERE telegram_id=?", (telegram_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute(
            "UPDATE bot_users SET role='admin', authorized=1 WHERE telegram_id=?",
            (telegram_id,)
        )
    else:
        cursor.execute(
            "INSERT INTO bot_users (telegram_id, role, authorized) VALUES (?, 'admin', 1)",
            (telegram_id,)
        )

    conn.commit()


# --- EMPLOYEES ---
def add_employee(full_name: str, email: str):
    last_name = full_name.split()[0].strip().lower()

    cursor.execute(
        "INSERT INTO employees (full_name, last_name, email) VALUES (?, ?, ?)",
        (full_name, last_name, email)
    )
    conn.commit()


def delete_employee(email: str):
    cursor.execute("DELETE FROM employees WHERE email=?", (email,))
    conn.commit()


def list_employees():
    cursor.execute("SELECT * FROM employees ORDER BY full_name")
    return cursor.fetchall()


def get_employee_by_email(email: str):
    cursor.execute("SELECT * FROM employees WHERE email=?", (email,))
    return cursor.fetchone()


def find_employee_by_lastname(last_name: str):
    cursor.execute("SELECT * FROM employees WHERE lower(last_name)=?", (last_name.lower(),))
    return cursor.fetchone()


# --- TASKS ---
def count_active_tasks() -> int:
    cursor.execute("SELECT COUNT(*) AS c FROM tasks WHERE status='active'")
    return cursor.fetchone()["c"]


def create_task(task_text: str, deadline: str, created_by: int) -> int:
    created_at = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO tasks (task_text, deadline, status, created_at, created_by)
        VALUES (?, ?, 'active', ?, ?)
    """, (task_text, deadline, created_at, created_by))
    conn.commit()
    return cursor.lastrowid


def assign_task(task_id: int, employee_ids: list[int]):
    for emp_id in employee_ids:
        cursor.execute(
            "INSERT INTO task_assignees (task_id, employee_id) VALUES (?, ?)",
            (task_id, emp_id)
        )
    conn.commit()


def cancel_task(task_id: int):
    cursor.execute("UPDATE tasks SET status='cancelled' WHERE id=?", (task_id,))
    conn.commit()


def get_active_tasks():
    cursor.execute("SELECT * FROM tasks WHERE status='active' ORDER BY id DESC")
    return cursor.fetchall()


def get_history_tasks(limit: int = 30):
    cursor.execute("""
        SELECT * FROM tasks
        WHERE status!='active'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()


def get_task(task_id: int):
    cursor.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    return cursor.fetchone()


def get_task_emails(task_id: int) -> list[str]:
    cursor.execute("""
        SELECT e.email
        FROM task_assignees ta
        JOIN employees e ON e.id = ta.employee_id
        WHERE ta.task_id=?
    """, (task_id,))
    rows = cursor.fetchall()
    return [r["email"] for r in rows]