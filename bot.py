import os
import random
import telebot
import threading
from banners import *
from dotenv import load_dotenv
from questions import questions

from telebot.types import (
    PollAnswer, ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove,
    Poll

)

from config import (
    auto_delete, delete_user_command,
    with_quiz_winners, auto_delete_replies
) 

from db import (
    init_db, add_user_if_new, add_point,
    save_answer, get_user_stats, 
    get_all_user_stats, reset_user_stats
)

load_dotenv()

token = os.getenv("BOT_TOKEN")

if not token:
    raise ValueError("❌ Токен не найден! Проверь .env файл и имя переменной BOT_TOKEN")

bot = telebot.TeleBot(token)

# ---------------------------
# Хранение ответов по poll_id
# ---------------------------

correct_answers_dict = {}  # poll_id -> correct_index
wrong_answers = {}  # poll_id: [ошибшиеся пользователи]
poll_results = {} # Сохраняем ответы пользователей

@bot.message_handler(commands=['start'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=15)
def start_command(message):
    text = (
        f"Привет, {message.from_user.first_name}! 🤗\n\n"
        f"{commands}\n"
    )
    return bot.send_message(chat_id=message.chat.id, text=text)



@bot.message_handler(commands=['my_score'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=15)
def my_score_command(message):
    user_id = message.from_user.id
    all_stats = get_all_user_stats()
    user_stat = next((stat for stat in all_stats if stat[0] == user_id), None)

    if not user_stat:
        return bot.send_message(message.chat.id, "Вы ещё не участвовали в квизах 😅")

    uid, uname, fname, scores, total_games, correct, wrong, ratio = user_stat
    name = f"@{uname}" if uname else fname

    stats_text = (
        f"🏆 Очки: {scores}\n"
        f"🎮 Всего игр: {total_games}\n"
        f"✅ Правильных: {correct}\n"
        f"❌ Неправильных: {wrong}\n"
        f"📊 % П/Н: {ratio}%"
    )

    # Добавляем отступы для выравнивания внутри бокса
    formatted_stats = "\n".join("┃ " + line for line in stats_text.split("\n")) + "\n"

    try:
        # Вставляем статистику между частями баннера с помощью конкатенации
        banner_with_stats = personal_stats_1 + formatted_stats + personal_stats_2
    except NameError as e:
        # Fallback если баннер не определен (например, если personal_stats_1/_2 отсутствуют)
        print(f"Ошибка в баннере: {e}. Проверьте banners.py на наличие personal_stats_1 и personal_stats_2.")
        banner_with_stats = stats_text  # Отправляем статистику без баннера

    return bot.send_message(message.chat.id, banner_with_stats)



@bot.message_handler(commands=['rs'])
@delete_user_command(bot, delay=5)
@auto_delete_replies(bot, delay=15)  # все сообщения внутри будут удалены
def reset_stats_command(message):
    chat_id = message.chat.id

    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Да"), KeyboardButton("Нет"))

    bot.send_message(
        chat_id,
        "⚠ Вы уверены, что хотите обнулить вашу статистику?",
        reply_markup=markup
    )

    bot.register_next_step_handler(message, process_reset_confirmation)


@auto_delete_replies(bot, delay=15)
def process_reset_confirmation(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    answer = message.text.strip().lower()

    if answer == "да":
        reset_user_stats(user_id)
        bot.send_message(chat_id, "✅ Ваша статистика была обнулена!", reply_markup=ReplyKeyboardRemove())
    else:
        bot.send_message(chat_id, "❌ Обнуление статистики отменено.", reply_markup=ReplyKeyboardRemove())



@bot.message_handler(commands=['quiz'])
@delete_user_command(bot, delay=5)
def create_quiz(message):
    if not questions:
        bot.send_message(message.chat.id, "Вопросы недоступны 😱.")
        return

    # Выбираем случайный вопрос
    q_text, correct_answer = random.choice(list(questions.items()))
    other_answers = [a for _, a in questions.items() if a != correct_answer]

    num_options = 4
    num_wrong = min(num_options - 1, len(other_answers))
    wrong_answers = random.sample(other_answers, k=num_wrong)

    options = wrong_answers + [correct_answer]
    random.shuffle(options)
    correct_index = options.index(correct_answer)

    # Отправляем квиз
    poll_message = bot.send_poll(
        chat_id=message.chat.id,
        question=q_text,
        options=options,
        type='quiz',
        correct_option_id=correct_index,
        is_anonymous=False,
        explanation=f"Правильный ответ: {correct_answer}"
    )

    # Сохраняем правильный ответ по poll_id
    correct_answers_dict[poll_message.poll.id] = correct_index

    # Таймер на удаление квиза через 20 секунд
    threading.Timer(
    20.0,
    delete_quiz,
    args=(message.chat.id, poll_message.message_id, poll_message.poll.id)).start()

# ---------------------------
# Обработчик ответа пользователя на опрос
# ---------------------------

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer: PollAnswer):
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    username = poll_answer.user.username
    first_name = poll_answer.user.first_name
    option_id = poll_answer.option_ids[0] if poll_answer.option_ids else None

    if option_id is None:
        return  # Игнорируем, если нет выбора

    # Добавляем пользователя, если новый
    add_user_if_new(user_id, username, first_name)

    # Проверяем правильность
    correct_index = correct_answers_dict.get(poll_id)
    if correct_index is not None:
        correct = 1 if option_id == correct_index else 0
        # Сохраняем в БД
        save_answer(poll_id, user_id, correct)
        # Сохраняем в poll_results для handle_closed_poll
        if poll_id not in poll_results:
            poll_results[poll_id] = []
        poll_results[poll_id].append((user_id, username, first_name, correct))


@with_quiz_winners
@auto_delete(bot, delay=15)
def delete_quiz(chat_id: int, message_id: int, poll_id: str, winners_text: str = None):
    try:
        bot.stop_poll(chat_id, message_id)
        bot.delete_message(chat_id, message_id)

        if winners_text:
            text = f"{winners}\n🎉 Победители: {winners_text}!\n\nДля продолжения игры используйте : /quiz"
            return bot.send_message(chat_id, text)
        else:
            text = f"<pre>{fail_answer}</pre>\nНикто не ответил правильно 😅.\n\nДля продолжения игры используйте : /quiz"
            return bot.send_message(chat_id, text, parse_mode='HTML')

    except Exception as e:
        print("Ошибка при удалении квиза:", e)


# ---------------------------
# Обработчик выбора ответа в квизе
# ---------------------------

@auto_delete(bot, delay=10)
@bot.poll_handler(func=lambda p: p.is_closed)
def handle_closed_poll(poll: Poll):
    results = poll_results.get(poll.id, [])
    correct_index = correct_answers_dict.get(poll.id)

    for user_id, username, first_name, correct in results:
        name = f"@{username}" if username else first_name
        if correct:
            add_point(user_id)
            # Убрана отправка личного сообщения для избежания дублирования; итог только в чате
        else:
            pass  # Пустой блок для неправильных ответов


# ---------------------------
# Функция вывода топ игроков
# ---------------------------

@bot.message_handler(commands=['top'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=10)
def show_top(message):
    user_id = message.from_user.id
    headers = ['№', 'Имя', 'Очки', 'Игр', 'П/Н%']

    # Удаляем командное сообщение
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass

    # Получаем список всех пользователей с рейтингом
    all_users = get_user_stats()

    table_data = []
    user_row = None

    for rank, uid, username, first_name, scores, total_games, correct, wrong, percent in all_users:
        display_name = f"@{username}" if username else first_name or "—"
        row = [str(rank), display_name, str(scores), str(total_games), f"{percent}%"]

        # Добавляем топ-7
        if rank <= 7:
            table_data.append(row)

        # Если пользователь вне топа
        if uid == user_id and rank > 7:
            user_row = row

    # Добавляем пользователя вне топа с разделителем
    if user_row:
        table_data.append(['—'] * len(headers))
        table_data.append(user_row)

    # Вычисляем динамическую ширину колонок
    col_widths = [
        max(len(str(headers[i])), max(len(str(row[i])) for row in table_data))
        for i in range(len(headers))
    ]

    def format_row(row):
        # Выравнивание по левому краю с разделителем |
        return "|" + "|".join(f" {str(row[i]):<{col_widths[i]}} " for i in range(len(row))) + "|"

    # Разделительная линия для всей таблицы
    sep_line = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    lines = [sep_line, format_row(headers), sep_line] + \
            [format_row(row) for row in table_data] + [sep_line]

    # Отправка сообщения с тегом <pre> для фиксированного шрифта
    return bot.send_message(
        message.chat.id,
        f"<pre>{chr(10).join(lines)}</pre>",
        parse_mode='HTML'
    )


# ---------------------------
# Запуск бота
# ---------------------------

if __name__ == '__main__':
    init_db()  # создаём таблицу при старте
    print("Бот успешно запущен и работает!")
    bot.polling()