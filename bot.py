import telebot
import threading
import random
from telebot.types import PollAnswer
from config import token, auto_delete, delete_user_command, with_quiz_winners
from questions import questions  # словарь вопросов
from db import init_db, add_user_if_new, add_point, get_user_scores, save_correct_answer, get_top_users, get_user_rank

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
@auto_delete(bot, delay=15)
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
@auto_delete(bot, delay=15)    # <-- теперь передаём bot сюда
def my_score_command(message):
    scores = get_user_scores(message.from_user.id)
    return bot.send_message(message.chat.id, f"У вас {scores} очков 🏆")


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

    # Сохраняем ответ в таблицу quiz_answers
    if correct:
        from db import save_correct_answer
        save_correct_answer(poll_answer.poll_id, user_id)
        add_point(user_id)


@bot.message_handler(commands=['top'])
@delete_user_command(bot, delay=5)
@auto_delete(bot, delay=30)
def show_top(message):
    top_users = get_top_users(7)
    user_rank, user_score = get_user_rank(message.from_user.id)

    lines = ["🏆 Топ-7 игроков:"]
    for i, (uname, fname, score) in enumerate(top_users, start=1):
        name = f"@{uname}" if uname else fname
        lines.append(f"{i}. {name} — {score}")

    # если пользователь не в топ-7, добавляем 8-ю строку с его местом
    if user_rank and user_rank > 7:
        lines.append("—" * 20)
        lines.append(f"{user_rank}. Вы — {user_score}")

    return bot.send_message(message.chat.id, "\n".join(lines))


# ---------------------------
# Запуск бота
# ---------------------------

if __name__ == '__main__':
    init_db()  # создаём таблицу при старте
    print("Бот успешно запущен и работает!")
    bot.polling()
