import sqlite3

DB_PATH = 'users.db'


def init_db():
    """Создание таблиц пользователей и квиз-ответов"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        scores INTEGER,
        username TEXT,
        first_name TEXT
    )
    ''')
    
    # Таблица для правильных ответов квизов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quiz_answers(
        poll_id TEXT,
        user_id INTEGER,
        correct INTEGER,
        PRIMARY KEY(poll_id, user_id)
    )
    ''')
    
    conn.commit()
    conn.close()


def add_user_if_new(user_id: int, username: str, first_name: str):
    """Добавляет пользователя в базу, если его там ещё нет"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (user_id, scores, username, first_name) VALUES (?, ?, ?, ?)",
            (user_id, 0, username, first_name)  # <--- передаем все 4 значения
        )
        conn.commit()
    conn.close()


def add_point(user_id: int):
    """Добавляет 1 очко пользователю"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET scores = scores + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_user_scores(user_id: int) -> int:
    """Возвращает количество очков пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT scores FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def save_correct_answer(poll_id: str, user_id: int):
    """Сохраняет факт правильного ответа пользователя в квизе"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO quiz_answers (poll_id, user_id, correct) VALUES (?, ?, ?)",
        (poll_id, user_id, 1)
    )
    conn.commit()
    conn.close()

def get_top_users(limit: int = 7):
    """Возвращает список топ-пользователей: (username, first_name, scores)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, first_name, scores
        FROM users
        ORDER BY scores DESC, id ASC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_user_rank(user_id: int):
    """Возвращает кортеж (place, scores) для конкретного пользователя."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.scores,
               RANK() OVER (ORDER BY u.scores DESC, u.id ASC) AS rnk
        FROM users u
    """)
    data = cursor.fetchall()
    conn.close()
    for uid, scores, rank in data:
        if uid == user_id:
            return rank, scores
    return None, 0
