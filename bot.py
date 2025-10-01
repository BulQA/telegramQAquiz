import telebot
import threading
import random
from telebot.types import PollAnswer, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from config import token, auto_delete, delete_user_command, with_quiz_winners
from questions import questions
from db import (
    init_db, add_user_if_new, add_point,
    save_answer, get_user_stats, 
    get_all_user_stats, reset_user_stats
)

bot = telebot.TeleBot(token)

# ---------------------------
# Хранение правильных ответов по poll_id
# ---------------------------

correct_answers_dict = {}  # poll_id -> correct_index


@bot.message_handler(commands=['start'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=15)
def start_command(message):
    return bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"Привет, {message.from_user.first_name}! 🤗\n\n"
            "Для продолжения используйте: /fun"

        )
    )


@bot.message_handler(commands=['fun'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=10)
def fun_command(message):
    return bot.send_message(
        chat_id=message.chat.id,
        text=(
            f"Чтобы начать игру используйте команду: /quiz\n\n"
             "Для просмотра очков: /my_score"
        )
    )


@bot.message_handler(commands=['my_score'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=15)
def my_score_command(message):
    user_id = message.from_user.id
    all_stats = get_all_user_stats()
    user_stat = next((stat for stat in all_stats if stat[0] == user_id), None)

    if not user_stat:
        return bot.send_message(message.chat.id, "Вы ещё не участвовали в квизах 😅")
    else:
        uid, uname, fname, scores, total_games, correct, wrong, ratio = user_stat
        name = f"@{uname}" if uname else fname
        msg_text = (f"🏆 Очки: {scores}\n"
                    f"🎮 Всего игр: {total_games}\n"
                    f"✅ Правильных: {correct}\n"
                    f"❌ Неправильных: {wrong}\n"
                    f"📊 % П/Н: {ratio}%")
        return bot.send_message(message.chat.id, msg_text)


@bot.message_handler(commands=['rs'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=5)
def reset_stats_command(message):
    chat_id = message.chat.id

    # создаем клавиатуру "Да / Нет"
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Да"), KeyboardButton("Нет"))

    bot.send_message(
        chat_id,
        "⚠ Вы уверены, что хотите обнулить вашу статистику?",
        reply_markup=markup
    )

    # переводим в режим ожидания ответа
    bot.register_next_step_handler(message, process_reset_confirmation)


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

    # Таймер на удаление квиза через 15 секунд
    threading.Timer(
    20.0,
    delete_quiz,
    args=(message.chat.id, poll_message.message_id, poll_message.poll.id)).start()


@with_quiz_winners
@auto_delete(bot, delay=15)
def delete_quiz(chat_id: int, message_id: int, poll_id: str, winners_text: str = None):
    try:
        bot.stop_poll(chat_id, message_id)
        bot.delete_message(chat_id, message_id)

        if winners_text:
            text = (f"🎉 Победители: {winners_text}!\n\n"
                    "Для продолжения игры используйте : /quiz"
                    )
        else:
            text = ("Никто не ответил правильно 😅.\n\n"
                    "Для продолжения игры используйте : /quiz"
                    )
        return bot.send_message(chat_id, text)

    except Exception as e:
        print("Ошибка при удалении квиза:", e)


# ---------------------------
# Обработчик выбора ответа в квизе
# ---------------------------

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer: PollAnswer):
    user_id = poll_answer.user.id
    username = poll_answer.user.username
    first_name = poll_answer.user.first_name

    # Добавляем пользователя в базу при первом ответе
    add_user_if_new(user_id=user_id, username=username, first_name=first_name)

    selected_option = poll_answer.option_ids[0]
    correct_index = correct_answers_dict.get(poll_answer.poll_id)
    correct = 1 if selected_option == correct_index else 0

    # Сохраняем ответ в таблицу quiz_answers (и правильный, и неправильный)
    save_answer(poll_answer.poll_id, user_id, correct)

    # Начисляем очки только за правильный ответ
    if correct:
        add_point(user_id)


# ---------------------------
# Функция вывода топ игроков
# ---------------------------

@bot.message_handler(commands=['top'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=10)
def show_top(message):
    user_id = message.from_user.id
    headers = ['Место', 'Юз', 'Очки', 'Игры', '% П/Н']

    all_users = get_user_stats()

    table_data = []
    user_row = None

    for rank, username, first_name, scores, total_games, correct, wrong, percent in all_users:
        display_name = f"@{username}" if username else first_name or "—"
        row = [rank, display_name, scores, total_games, f"{percent}%"]

        if rank <= 7:
            table_data.append(row)

        if rank > 7 and (username == message.from_user.username or user_id == message.from_user.id):
            user_row = row

    # автоширина колонок
    col_widths = [
        max(len(str(x)) for x in [header] + [row[i] for row in table_data] + ([user_row[i]] if user_row else [])) + 2
        for i, header in enumerate(headers)
    ]

    def format_row(row):
        return "|" + "|".join(f"{str(row[i]):^{col_widths[i]}}" for i in range(len(row))) + "|"

    sep_line = "+" + "+".join("-" * w for w in col_widths) + "+"
    lines = [format_row(headers), sep_line] + [format_row(row) for row in table_data]

    if user_row:
        lines.append(sep_line)
        lines.append(format_row(user_row))

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
