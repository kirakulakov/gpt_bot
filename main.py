import asyncio
import logging
import random
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import g4f
import telebot
from g4f import Model, Messages
from g4f.Provider import ChatBase as provider
from g4f.models import gpt_4
from telebot import types
message_id_to_count_regenerate = {}

db_path = 'bot_messages.db'
conn = sqlite3.connect(db_path)

cursor = conn.cursor()

# Создаём таблицу для хранения ID сообщений
cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages_from_user (
        message_id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        text TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages_from_bot_v2 (
        message_id INTEGER PRIMARY KEY,
        text TEXT,
        question_from_user TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_TOKEN = '6368893890:AAFxIMeQ_o3ovj-z-WtviJDJWYB5aAOPEpE'

bot = telebot.TeleBot(API_TOKEN)

GPT_MODELS = [
                 g4f.models.gpt_35_turbo_16k,
                 g4f.models.default,
                 g4f.models.gpt_35_long,
                 g4f.models.gpt_35_turbo,
                 g4f.models.gpt_35_turbo_16k_0613
             ] * 2


def get_message_declension(count):
    if 10 <= count % 100 <= 20:
        return 'сообщений'
    else:
        last_digit = count % 10
        if last_digit == 1:
            return 'сообщение'
        elif 2 <= last_digit <= 4:
            return 'сообщения'
        else:
            return 'сообщений'


@bot.message_handler(commands=['history'])
def handle_history(message):
    user_id = message.from_user.id  # ID пользователя, отправившего команду

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT text FROM messages_from_user WHERE user_id = ? ORDER BY date DESC LIMIT 20', (user_id,))
        messages = cursor.fetchall()

    if messages:
        response = "\n\n" + "\n".join("- " + msg[0] for msg in messages)
    else:
        response = "История сообщений пуста."

    bot.send_message(message.chat.id, response, parse_mode='HTML')


@bot.message_handler(commands=['count'])
def count_messages(message):
    user_id = message.from_user.id  # ID пользователя, отправившего команду

    # Подключаемся к базе данных и выполняем запрос подсчета
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM messages_from_user WHERE user_id = ?', (user_id,))
        count = cursor.fetchone()[0]  # Получаем количество сообщений

    message_word = get_message_declension(count)

    # Отправляем пользователю количество его сообщений с правильным склонением
    bot.send_message(message.chat.id, f"Ты отправил(а) мне {count} {message_word}.")


@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Получение имени пользователя
    first_name = message.from_user.first_name
    logger.info(f"Received /start command from [ID: {message.from_user.id}], [first_name: {first_name}]")

    if first_name:
        greeting = f"Привет, <b>{first_name}</b>! Рад с тобой познакомиться!\nЯ твой умный <b>AI-помощник</b>. Можешь задавать мне любые вопросы!"
    else:
        greeting = f"Привет! Рад с тобой познакомиться!\nЯ твой умный <b>AI-помощник</b>. Можешь задавать мне любые вопросы!"

    bot.send_message(message.chat.id, greeting, parse_mode='HTML')


@bot.message_handler(commands=['help'])
def send_help(message):
    # Получение имени пользователя
    first_name = message.from_user.first_name
    logger.info(f"Received /help command from [ID: {message.from_user.id}], [first_name: {first_name}]")

    help_message = (
        f"Я бот-помощник, созданный благодаря последним достижениям <b>OpenAI</b>.\n"
        f"Моя задача — помогать тебе, отвечая на любые вопросы, которые могут у тебя возникнуть.\n\n\n"
        f"<i>from</i> @kirakulakov"
    )

    # Отправляем сообщение
    bot.send_message(chat_id=message.chat.id, text=help_message, parse_mode='HTML')


def contains_no_chinese_or_japanese_characters(text):
    pattern = r'^[^\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]*$'
    return re.match(pattern, text) is not None

_providers = [
        g4f.Provider.GPTalk,
        g4f.Provider.RetryProvider,
        g4f.Provider.ChatBase,
        g4f.Provider.GptForLove,
        g4f.Provider.Hashnode,
        g4f.Provider.BaseProvider

    ]
async def ask_gpt_do(p: str, model: Model) -> str | None:
    _content = 'ОБЯЗАТЕЛЬНО: ответ генерируй на русском языке и собери максимально достоверную, подробную и правдивую информацию! В своем ответе в большей части опирайся на научно-известные факты и проверенные данные!\n' + p + '\n ОБЯЗАТЕЛЬНО: ответ генерируй на русском языке и собери максимально достоверную, подробную и правдивую информацию! В своем ответе в большей части опирайся на научно-известные факты и проверенные данные!'
    # _content = 'Ответ сгенерируй максимально кратко, быстро и понятно, вопрос --> ' + p
    # _content = 'Для генерации ответа найди золотую середину между краткостью, быстротой, и развернутостью ответа, итак вопрос звучит так: --> ' + p
    max_attempts = 15
    attempt = 0

    while attempt < max_attempts:
        try:
            response = await g4f.ChatCompletion.create_async(
                model=model,
                messages=[{"role": "user", "content": _content}]
            )
            if response:
                if isinstance(response, str):
                    if contains_no_chinese_or_japanese_characters(response):
                        if response != "I'm sorry, but I can only provide information and answer questions related to Chatbase." and response != ["I'm sorry, but I can only provide information and answer questions related to Chatbase."]:
                            return response
            else:
                attempt += 1
                # await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Ошибка при запросе к GPT: {e}")
            attempt += 1
            # await asyncio.sleep(0.2)

    return None  # возвращаем None, если не удалось получить адекватный ответ


async def ask_gpt_first_completed(message):
    if isinstance(message, str):
        tasks = [asyncio.create_task(ask_gpt_do(p=message, model=model)) for model in GPT_MODELS]
    else:
        tasks = [asyncio.create_task(ask_gpt_do(p=message.text, model=model)) for model in GPT_MODELS]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    for task in pending:
        task.cancel()

    # Возвращаем результат первой выполненной задачи
    if done:
        return done.pop().result()
    return None


def _answer_prepare(message) -> int:
    logger.info(f"Get message from: [ID {message.from_user.id}] [NAME: {message.from_user.first_name}] [MESSAGE: {message.text}]")

    # Отправка сообщения и сохранение его message_id
    processing_message = bot.send_message(message.chat.id,
                                          '<i>Уже обрабатываю твое сообщение 🔮\n\nОбычно мне необходимо всего несколько секунд, но в некоторых случаях чуть больше 💫</i>',
                                          parse_mode='HTML')

    message_id_to_delete = processing_message.message_id

    bot.send_chat_action(message.chat.id, 'typing')
    return message_id_to_delete


def save_to_db(message):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages_from_user (message_id, user_id, text, chat_id) VALUES (?, ?, ?, ?)
        ''', (message.id, message.from_user.id, message.text, message.chat.id))
        conn.commit()

def save_to_db_from_bot(message, question_from_user):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages_from_bot_v2 (message_id, text, question_from_user) VALUES (?, ?, ?)
        ''', (message.id, message.text, question_from_user.text))
        conn.commit()



@bot.message_handler(func=lambda message: True)
def answer(message):
    btn_retry = str('\U0001F504')
    inline_markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(btn_retry, callback_data=btn_retry),
    ]
    inline_markup.add(*buttons)

    mess_from_user = message

    with ThreadPoolExecutor() as executor:
        save_to_db_future = executor.submit(save_to_db, message)
        answer_prepare_future = executor.submit(_answer_prepare, message)
        ask_gpt_first_completed_future = executor.submit(asyncio.run, ask_gpt_first_completed(message=message))

        save_to_db_future.result()
        message_id_to_delete = answer_prepare_future.result()
        res = ask_gpt_first_completed_future.result()

    # message_id_to_delete = _answer_prepare(message=message)
    # res = asyncio.run(ask_gpt_first_completed(message=message))

    with ThreadPoolExecutor() as executor:
        delete_message_future = executor.submit(bot.delete_message, chat_id=message.chat.id,
                                                message_id=message_id_to_delete)
        if res:
            reply_result_future = executor.submit(bot.reply_to, message, res, reply_markup=inline_markup, parse_mode='Markdown')
        else:
            reply_result_future = executor.submit(bot.reply_to, message,
                                                  "Извини, возникла ошибка при обработке твоего запроса. Попробуй еще раз позже.", reply_markup=inline_markup)

        delete_message_future.result()
        message_from_bot = reply_result_future.result()

    if res:
        with ThreadPoolExecutor() as executor:
            save_to_db_future = executor.submit(save_to_db_from_bot, message_from_bot, mess_from_user)
            save_to_db_future.result()

    # Удаление предыдущего сообщения
    # bot.delete_message(chat_id=message.chat.id, message_id=message_id_to_delete)

    # Отправка ответа
    # if res:
    #     bot.reply_to(message, res)
    # else:
    #     bot.reply_to(message, "Извини, возникла ошибка при обработке твоего запроса. Попробуй еще раз позже.")

    logger.info(f"Send response to: [ID {message.from_user.id}] MES: [{res}]")


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):

    btn_retry = str('\U0001F504')
    inline_markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(btn_retry, callback_data=btn_retry),
    ]
    inline_markup.add(*buttons)

    chat_id = call.message.chat.id
    message_id = call.message.message_id

    if not message_id in message_id_to_count_regenerate:
        message_id_to_count_regenerate[message_id] = 1
    else:
        message_id_to_count_regenerate[message_id] += 1

    if call.data == '\U0001F504':
        bot.answer_callback_query(call.id, f"Вы выбрали: Перегенерировать ответ")

        user_id = call.from_user.id

        # with sqlite3.connect(db_path) as conn:
        #     cursor = conn.cursor()
        #     cursor.execute('SELECT chat_id FROM messages_from_user WHERE user_id = ? ORDER BY date DESC LIMIT 1',
        #                    (user_id,))
        #     c = cursor.fetchall()
        #     print(c)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT question_from_user FROM messages_from_bot_v2 WHERE message_id = ? ORDER BY date DESC LIMIT 1',
                           (message_id,))
            message_from_bot = cursor.fetchall()

        message = message_from_bot[0][0]


        with ThreadPoolExecutor() as executor:
            prepare = executor.submit(bot.send_chat_action, chat_id, 'typing')
            ask_gpt_first_completed_future = executor.submit(asyncio.run, ask_gpt_first_completed(message=message))

            res = ask_gpt_first_completed_future.result()
            prepare.result()

        edited_text = res + f'\n\n\n<b>[REGENERATED v.{message_id_to_count_regenerate[message_id]}]</b>'
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=edited_text, reply_markup=inline_markup, parse_mode='HTML')
        logger.info(f"Regenerate done [ID: {user_id}], [RESULT: {res[0:50]} ...]")


# Запуск бота
bot.polling(long_polling_timeout=9999)
