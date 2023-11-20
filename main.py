import logging
import time

import g4f
import telebot

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_TOKEN = '6368893890:AAFxIMeQ_o3ovj-z-WtviJDJWYB5aAOPEpE'

bot = telebot.TeleBot(API_TOKEN)


# '/start' и '/help'
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    # Получение имени пользователя
    first_name = message.from_user.first_name
    logger.info(f"Received /start or /help command from [ID: {message.from_user.id}], [first_name: {first_name}]")

    if first_name:
        greeting = f"Привет, <b>{first_name}</b>! Рад с тобой познакомиться! Я твой умный <b>AI</b>-помощник. Можешь задавать мне любые вопросы!"
    else:
        greeting = f"Привет! Рад с тобой познакомиться! Я твой умный <b>AI</b>-помощник. Можешь задавать мне любые вопросы!"

    bot.send_message(message.chat.id, greeting, parse_mode='HTML')


def ask_gpt(p: str) -> str | None:
    p = p + '\n ОБЯЗАТЕЛЬНО: ответ генерируй на русском языке!'
    max_attempts = 15
    attempt = 0
    while attempt < max_attempts:
        try:
            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_35_turbo_16k,
                messages=[{"role": "user", "content": p}],
            )  # Alternative model setting

            if isinstance(response, str):
                return response
        except Exception as e:
            logger.error(f"Ошибка при запросе к GPT: {e}")
            attempt += 1
            time.sleep(0.3)

    return None  # возвращаем None, если не удалось получить адекватный ответ


@bot.message_handler(func=lambda message: True)
def echo_all(message):
    logger.info(f"Get message from: [ID {message.from_user.id}] [MESSAGE: {message.text}]")

    # Отправка сообщения и сохранение его message_id
    processing_message = bot.send_message(message.chat.id,
                                          '<i>Уже обрабатываю твое сообщение 🔮\n\nОбычно мне необходимо всего несколько секунд, но в некоторых случаях чуть больше 💫</i>',
                                          parse_mode='HTML')

    # message_id_to_delete = processing_message.message_id

    bot.send_chat_action(message.chat.id, 'typing')

    res = ask_gpt(message.text)

    # Удаление предыдущего сообщения
    # bot.delete_message(chat_id=message.chat.id, message_id=message_id_to_delete)

    # Отправка ответа
    if res:
        bot.reply_to(message, res)
    else:
        bot.reply_to(message, "Извини, возникла ошибка при обработке твоего запроса. Попробуй еще раз позже.")

    logger.info(f"Send response to: [ID {message.from_user.id}] MES: [{res}]")


# Запуск бота
bot.polling(skip_pending=True)
