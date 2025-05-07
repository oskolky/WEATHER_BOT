import sqlite3
from datetime import datetime
from typing import Optional

DB_NAME = "history.db"

def init_db():
    conn = sqlite3.connect('weather.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_input TEXT NOT NULL,
            city TEXT NOT NULL,
            advice TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def save_history(
        user_id: str,
        user_input: str,
        city: str,
        advice: str
):
    conn = sqlite3.connect('weather.db')
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO history (user_id, user_input, city, advice)
        VALUES (?, ?, ?, ?)
    ''', (user_id, user_input, city, advice))

    conn.commit()
    conn.close()

def get_history(limit: int = 50):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, user_input, city, advice, timestamp 
        FROM history ORDER BY timestamp DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "user_id": row[0],
            "user_input": row[1],
            "city": row[2],
            "advice": row[3]
        }
        for row in rows
    ]


def get_last_city(user_id: str) -> Optional[str]:
    print(f"⚡ Поиск последнего города для user_id: {user_id}")

    try:
        conn = sqlite3.connect('weather.db')
        cursor = conn.cursor()

        # Явно указываем нужные столбцы
        query = """
        SELECT city, timestamp 
        FROM history 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 1
        """

        print(f"🛠 Выполняем запрос: {query} с user_id={user_id}")
        cursor.execute(query, (user_id,))

        result = cursor.fetchone()

        if result:
            city, timestamp = result
            print(f"✅ Найден город: {city} (записан в {timestamp})")
            return city
        else:
            print("⚠️ Записей для этого пользователя не найдено")
            return None

    except sqlite3.Error as e:
        print(f"🔥 Ошибка SQLite: {e}")
        return None
    finally:
        if conn:
            conn.close()
            print("🔌 Соединение с БД закрыто")