import sqlite3
import threading
from db import DB_PATH
from functools import wraps

token = '8253664996:AAFgMQXOARA3XKxSYonWKIB08Feq2DTLd1Q'

class User:
    def __init__(self, user_id: int, first_name: str, username: str, scores: int = 0):
        self.user_id = user_id
        self.first_name = first_name
        self.username = username
        self.scores = scores


def auto_delete(bot, delay: int = 15):
    """
    Декоратор, удаляющий сообщение(я), отправленное ботом через delay секунд.
    Поддерживает: Message, list[Message], tuple[Message,...], None.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            def schedule_delete(msg):
                try:
                    bot.delete_message(msg.chat.id, msg.message_id)
                except Exception:
                    pass  # чтобы не падало, если сообщение уже удалено

            if result is None:
                return result

            if isinstance(result, list) or isinstance(result, tuple):
                for msg in result:
                    if msg:
                        threading.Timer(delay, schedule_delete, args=(msg,)).start()
            else:
                threading.Timer(delay, schedule_delete, args=(result,)).start()

            return result
        return wrapper
    return decorator


def delete_user_command(bot, delay: int = 5):
    """
    Декоратор для удаления исходного сообщения (команды),
    вызвавшего обработчик, через delay секунд.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(message, *args, **kwargs):
            # ставим таймер на удаление сообщения пользователя
            threading.Timer(
                delay,
                lambda: bot.delete_message(message.chat.id, message.message_id)
            ).start()
            # продолжаем обычную работу хэндлера
            return func(message, *args, **kwargs)
        return wrapper
    return decorator


def auto_delete_replies(bot, delay: int = 10):
    """
    Декоратор для удаления всех сообщений бота,
    отправленных через bot.send_message внутри функции.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sent_messages = []

            # Подмена метода send_message на обертку
            original_send_message = bot.send_message

            def wrapped_send_message(*s_args, **s_kwargs):
                msg = original_send_message(*s_args, **s_kwargs)
                sent_messages.append(msg)
                return msg

            bot.send_message = wrapped_send_message
            try:
                result = func(*args, **kwargs)
            finally:
                # Возвращаем оригинальный метод
                bot.send_message = original_send_message

            # Планируем удаление всех сообщений
            def schedule_delete(msg):
                try:
                    bot.delete_message(msg.chat.id, msg.message_id)
                except Exception:
                    pass

            for msg in sent_messages:
                threading.Timer(delay, schedule_delete, args=(msg,)).start()

            return result
        return wrapper
    return decorator


def with_quiz_winners(func):
    """
    Декоратор для получения победителей квиза из базы данных.
    Добавляет в kwargs ключ 'winners_text', который можно использовать в функции.
    """
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
