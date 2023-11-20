import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import g4f
import telebot
from g4f import Model

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_TOKEN = '6368893890:AAFxIMeQ_o3ovj-z-WtviJDJWYB5aAOPEpE'

bot = telebot.TeleBot(API_TOKEN)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Получение имени пользователя
    first_name = message.from_user.first_name
    logger.info(f"Received /start command from [ID: {message.from_user.id}], [first_name: {first_name}]")

    if first_name:
        greeting = f"Привет, <b>{first_name}</b>! Рад с тобой познакомиться! Я твой умный <b>AI</b>-помощник. Можешь задавать мне любые вопросы!"
    else:
        greeting = f"Привет! Рад с тобой познакомиться! Я твой умный <b>AI</b>-помощник. Можешь задавать мне любые вопросы!"

    bot.send_message(message.chat.id, greeting, parse_mode='HTML')


@bot.message_handler(commands=['help'])
def send_help(message):
    # Получение имени пользователя
    first_name = message.from_user.first_name
    logger.info(f"Received /help command from [ID: {message.from_user.id}], [first_name: {first_name}]")

    help_message = f"Я бот-помощник, созданный благодаря достижениям <b>OpenAI</b> и основанный на прогрессивной модели <b>GPT-3.5 turbo16k</b>.\nМоя задача — помогать тебе, отвечая на любые вопросы, которые могут у тебя возникнуть.\n\nПо вопросам сотрудничества/контрибьютинга: @kirakulakov."

    bot.send_message(message.chat.id, help_message, parse_mode='HTML')

def contains_no_chinese_or_japanese_characters(text):
    pattern = r'^[^\u3000-\u303F\u3040-\u309F\u30A0-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]*$'
    return re.match(pattern, text) is not None

async def ask_gpt_do(p: str, model: Model) -> str | None:
    _content = 'ОБЯЗАТЕЛЬНО: ответ генерируй на русском языке!\n' + p + '\n ОБЯЗАТЕЛЬНО: ответ генерируй на русском языке!'
    max_attempts = 15
    attempt = 0
    while attempt < max_attempts:
        try:
            response = await g4f.ChatCompletion.create_async(
                model=model,
                messages=[{"role": "user", "content": _content}],
            )
            if response:
                if isinstance(response, str):
                    if contains_no_chinese_or_japanese_characters(response):
                        return response
            else:
                attempt += 1
                await asyncio.sleep(0.2)

        except Exception as e:
            logger.error(f"Ошибка при запросе к GPT: {e}")
            attempt += 1
            await asyncio.sleep(0.2)

    return None  # возвращаем None, если не удалось получить адекватный ответ


async def ask_gpt_first_completed(message):
    print('in ask_gpt_first_completed')

    tasks = [asyncio.create_task(ask_gpt_do(p=message.text, model=g4f.models.gpt_35_turbo_16k)) for _ in range(1)]
    tasks.extend([asyncio.create_task(ask_gpt_do(p=message.text, model=g4f.models.default)) for _ in range(1)])
    tasks.extend([asyncio.create_task(ask_gpt_do(p=message.text, model=g4f.models.gpt_35_long)) for _ in range(1)])
    tasks.extend([asyncio.create_task(ask_gpt_do(p=message.text, model=g4f.models.gpt_35_turbo)) for _ in range(1)])
    tasks.extend([asyncio.create_task(ask_gpt_do(p=message.text, model=g4f.models.gpt_35_turbo_16k_0613)) for _ in range(1)])

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    for task in pending:
        task.cancel()

    # Возвращаем результат первой выполненной задачи
    if done:
        return done.pop().result()
    return None

def _answer_prepare(message) -> int:
    print('in _answer_prepare')
    logger.info(f"Get message from: [ID {message.from_user.id}] [MESSAGE: {message.text}]")

    # Отправка сообщения и сохранение его message_id
    processing_message = bot.send_message(message.chat.id,
                                          '<i>Уже обрабатываю твое сообщение 🔮\n\nОбычно мне необходимо всего несколько секунд, но в некоторых случаях чуть больше 💫</i>',
                                          parse_mode='HTML')

    message_id_to_delete = processing_message.message_id

    bot.send_chat_action(message.chat.id, 'typing')
    print('end _answer_prepare')
    return message_id_to_delete

@bot.message_handler(func=lambda message: True)
def answer(message):
    with ThreadPoolExecutor() as executor:
        future_gpt = executor.submit(_answer_prepare, message)
        future_gpt_2 = executor.submit(asyncio.run, ask_gpt_first_completed(message=message))
        message_id_to_delete = future_gpt.result()
        res = future_gpt_2.result()

    # message_id_to_delete = _answer_prepare(message=message)
    # res = asyncio.run(ask_gpt_first_completed(message=message))

    with ThreadPoolExecutor() as executor:
        future_gpt = executor.submit(bot.delete_message, chat_id=message.chat.id, message_id=message_id_to_delete)
        if res:
            future_gpt_2 = executor.submit(bot.reply_to, message, res)
        else:
            future_gpt_2 = executor.submit(bot.reply_to, message, "Извини, возникла ошибка при обработке твоего запроса. Попробуй еще раз позже.")

        future_gpt.result()
        future_gpt_2.result()


    # Удаление предыдущего сообщения
    # bot.delete_message(chat_id=message.chat.id, message_id=message_id_to_delete)

    # Отправка ответа
    # if res:
    #     bot.reply_to(message, res)
    # else:
    #     bot.reply_to(message, "Извини, возникла ошибка при обработке твоего запроса. Попробуй еще раз позже.")

    logger.info(f"Send response to: [ID {message.from_user.id}] MES: [{res}]")


# Запуск бота
bot.polling()
