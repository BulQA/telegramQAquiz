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
            (user_id, 0, username, first_name)
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


def save_answer(poll_id: str, user_id: int, correct: int):
    """Сохраняет ответ пользователя (1 - правильный, 0 - неправильный)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO quiz_answers (poll_id, user_id, correct) VALUES (?, ?, ?)",
        (poll_id, user_id, correct)
    )
    conn.commit()
    conn.close()


def get_all_user_stats():
    """
    Возвращает список со статистикой всех пользователей:
    (user_id, username, first_name, очки, всего игр, правильные, неправильные, % Побед)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.username, u.first_name, u.scores,
               COUNT(a.poll_id) as total_games,
               SUM(a.correct) as correct_answers
        FROM users u
        LEFT JOIN quiz_answers a ON u.user_id = a.user_id
        GROUP BY u.user_id
        ORDER BY u.scores DESC, u.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for uid, uname, fname, scores, total_games, correct_answers in rows:
        total_games = total_games or 0
        correct_answers = correct_answers or 0
        wrong_answers = total_games - correct_answers
        if total_games > 0:
            ratio_percent = round(correct_answers / total_games * 100, 1)
        else:
            ratio_percent = 0.0

        result.append((uid, uname, fname, scores, total_games, correct_answers, wrong_answers, ratio_percent))

    return result


def get_user_stats(limit=999999):
    """
    Возвращает список всех пользователей с их очками, количеством игр
    и процентом побед.
    Формат: [(rank, user_id, username, first_name, scores, total_games, correct_answers, wrong_answers, percent_wins), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            u.user_id,
            u.username,
            u.first_name,
            u.scores,
            COUNT(qa.poll_id) AS total_games,
            SUM(CASE WHEN qa.correct = 1 THEN 1 ELSE 0 END) AS correct_answers,
            SUM(CASE WHEN qa.correct = 0 THEN 1 ELSE 0 END) AS wrong_answers,
            ROUND(
                CASE 
                    WHEN COUNT(qa.poll_id) = 0 THEN 0.0
                    ELSE SUM(CASE WHEN qa.correct = 1 THEN 1.0 ELSE 0 END) * 100.0 
                         / COUNT(qa.poll_id)
                END, 1
            ) AS percent_wins
        FROM users u
        LEFT JOIN quiz_answers qa ON u.user_id = qa.user_id
        GROUP BY u.user_id
        ORDER BY u.scores DESC, u.id ASC
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()

    result = []
    for rank, row in enumerate(rows, start=1):
        # теперь добавляем user_id в результат
        result.append((rank,) + row)  

    return result


def reset_user_stats(user_id: int):
    """Обнуляет статистику игрока (очки и ответы)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Сбрасываем очки
    cursor.execute("UPDATE users SET scores = 0 WHERE user_id = ?", (user_id,))
    # Удаляем записи об ответах
    cursor.execute("DELETE FROM quiz_answers WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()
