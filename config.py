import sqlite3
import threading
from db import DB_PATH
from functools import wraps
from telebot.apihelper import ApiTelegramException

def safe_delete(bot, chat_id, message_id):
    """Удаляет сообщение с безопасной обработкой исключений"""
    try:
        bot.delete_message(chat_id, message_id)
    except ApiTelegramException:
        pass  # Игнорируем, если сообщение уже удалено или нет прав


def auto_delete(bot, delay: int = 15):
    """Декоратор, удаляющий сообщение(я) от бота через delay секунд"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            def schedule_delete(msg):
                if msg:
                    safe_delete(bot, msg.chat.id, msg.message_id)

            if isinstance(result, (list, tuple)):
                for msg in result:
                    threading.Timer(delay, schedule_delete, args=(msg,)).start()
            elif result is not None:
                threading.Timer(delay, schedule_delete, args=(result,)).start()

            return result
        return wrapper
    return decorator


def delete_user_command(bot, delay: int = 5):
    """Декоратор для удаления исходного сообщения пользователя через delay секунд"""
    def decorator(func):
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            threading.Timer(delay, safe_delete, args=(bot, message.chat.id, message.message_id)).start()
            return func(message, *args, **kwargs)
        return wrapper
    return decorator


def auto_delete_replies(bot, delay: int = 10):
    """Декоратор для удаления всех сообщений бота, отправленных внутри функции"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sent_messages = []

            original_send_message = bot.send_message

            def wrapped_send_message(*s_args, **s_kwargs):
                msg = original_send_message(*s_args, **s_kwargs)
                sent_messages.append(msg)
                return msg

            bot.send_message = wrapped_send_message
            try:
                result = func(*args, **kwargs)
            finally:
                bot.send_message = original_send_message

            for msg in sent_messages:
                threading.Timer(delay, safe_delete, args=(bot, msg.chat.id, msg.message_id)).start()

            return result
        return wrapper
    return decorator


def with_quiz_winners(func):
    """Декоратор для получения победителей квиза из базы данных"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        poll_id = kwargs.get('poll_id') or (args[2] if len(args) > 2 else None)
        chat_id = kwargs.get('chat_id') or (args[0] if len(args) > 0 else None)
        winners_text = None

        if poll_id and chat_id:
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT u.username, u.first_name
                    FROM users u
                    JOIN quiz_answers qa ON u.user_id = qa.user_id
                    WHERE qa.poll_id = ? AND qa.correct = 1
                """, (poll_id,))
                winners = cursor.fetchall()
                conn.close()

                if winners:
                    names = [f"@{uname}" if uname else fname for uname, fname in winners]
                    winners_text = ", ".join(names)
            except Exception as e:
                print("Ошибка при получении победителей:", e)
                winners_text = None

        kwargs['winners_text'] = winners_text
        return func(*args, **kwargs)

    return wrapper
