import logging
import requests
import json
import os
import random
import re
import hashlib
from datetime import datetime, timedelta
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Путь к файлам с данными
JOKES_FILE = 'jokes.json'
USER_DATA_FILE = 'user_data.json'

# Класс для управления анекдотами
class JokeManager:
    def __init__(self):
        # Загружаем анекдоты и данные пользователей
        self.jokes = self.load_data(JOKES_FILE)
        self.user_data = self.load_data(USER_DATA_FILE)
        self.sources = [
            'https://www.anekdot.ru/last/anekdot/',
            'https://www.anekdot.ru/random/anekdot/',
            'https://www.anekdot.ru/last/top25/',
            'https://www.anekdot.ru/today/anekdot/',
            'https://www.ba-bamail.com/jokes/search.aspx?search=&categoryId=0',  # Пример другого источника
            # Добавьте другие источники здесь
        ]

    def load_data(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        else:
            return {}

    def save_data(self, data, filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def fetch_new_jokes(self):
        new_jokes = []
        for url in self.sources:
            for page in range(1, 6):  # Получаем первые 5 страниц каждого источника
                full_url = f"{url}?page={page}"
                try:
                    response = requests.get(full_url)
                    if response.status_code == 200:
                        content = response.text
                        # Используем регулярное выражение для поиска анекдотов
                        jokes = self.extract_jokes(content)
                        # Очищаем анекдоты от HTML-тегов
                        jokes = [re.sub('<.*?>', '', joke).strip() for joke in jokes]
                        for joke in jokes:
                            joke_id = self.generate_joke_id(joke)
                            if joke_id not in self.jokes:
                                self.jokes[joke_id] = {'text': joke, 'rating': 0}
                                new_jokes.append(joke)
                    else:
                        logger.error(f'Ошибка при запросе к {full_url}: {response.status_code}')
                except Exception as e:
                    logger.error(f'Ошибка при получении анекдотов: {e}')
        # Сохраняем обновленные анекдоты
        self.save_data(self.jokes, JOKES_FILE)
        return new_jokes

    def extract_jokes(self, content):
        # Здесь вы должны написать код для извлечения анекдотов из HTML-кода страницы
        # Это может быть различным для каждого источника
        jokes = re.findall(r'<div class="text">(.*?)</div>', content, re.DOTALL)
        return jokes

    def generate_joke_id(self, joke_text):
        # Генерируем уникальный идентификатор для анекдота
        return hashlib.md5(joke_text.encode('utf-8')).hexdigest()

    def get_new_joke_for_user(self, user_id):
        user_id_str = str(user_id)
        user_seen_jokes = self.user_data.get(user_id_str, {}).get('jokes_seen', [])
        # Получаем список анекдотов, которые пользователь еще не видел
        unseen_jokes = [(joke_id, joke) for joke_id, joke in self.jokes.items()
                        if joke_id not in user_seen_jokes]
        if unseen_jokes:
            joke_id, joke = random.choice(unseen_jokes)
            return joke_id, joke
        else:
            # Если все анекдоты уже просмотрены, обновляем список
            self.fetch_new_jokes()
            # Проверяем снова после обновления
            unseen_jokes = [(joke_id, joke) for joke_id, joke in self.jokes.items()
                            if joke_id not in user_seen_jokes]
            if unseen_jokes:
                joke_id, joke = random.choice(unseen_jokes)
                return joke_id, joke
            else:
                return None, None  # Если совсем нет новых анекдотов

    def get_best_joke_for_user(self, user_id):
        user_id_str = str(user_id)
        user_seen_jokes = self.user_data.get(user_id_str, {}).get('jokes_seen', [])
        # Сортируем анекдоты по рейтингу
        sorted_jokes = sorted(self.jokes.items(), key=lambda x: x[1]['rating'], reverse=True)
        # Фильтруем анекдоты, которые пользователь еще не видел
        unseen_jokes = [(joke_id, joke) for joke_id, joke in sorted_jokes
                        if joke_id not in user_seen_jokes]
        if unseen_jokes:
            joke_id, joke = unseen_jokes[0]
            return joke_id, joke
        else:
            # Если все анекдоты уже просмотрены, обновляем список
            self.fetch_new_jokes()
            # Проверяем снова после обновления
            unseen_jokes = [(joke_id, joke) for joke_id, joke in self.jokes.items()
                            if joke_id not in user_seen_jokes]
            if unseen_jokes:
                joke_id, joke = unseen_jokes[0]
                return joke_id, joke
            else:
                return None, None  # Если совсем нет новых анекдотов

    def record_joke_sent(self, user_id, joke_id):
        user_id_str = str(user_id)
        if user_id_str not in self.user_data:
            # Инициализируем данные пользователя
            self.user_data[user_id_str] = {
                'jokes_seen': [],
                'ad_offset': random.randint(0, 4),
                'last_interaction': datetime.now().isoformat()
            }
        if joke_id not in self.user_data[user_id_str]['jokes_seen']:
            self.user_data[user_id_str]['jokes_seen'].append(joke_id)
            self.save_data(self.user_data, USER_DATA_FILE)

    def update_joke_rating(self, joke_id, increment):
        if joke_id in self.jokes:
            self.jokes[joke_id]['rating'] += increment
            self.save_data(self.jokes, JOKES_FILE)

    def record_user_interaction(self, user_id):
        user_id_str = str(user_id)
        if user_id_str not in self.user_data:
            # Инициализируем данные пользователя
            self.user_data[user_id_str] = {
                'jokes_seen': [],
                'ad_offset': random.randint(0, 4),
                'last_interaction': datetime.now().isoformat()
            }
        else:
            # Обновляем время последнего взаимодействия
            self.user_data[user_id_str]['last_interaction'] = datetime.now().isoformat()
        self.save_data(self.user_data, USER_DATA_FILE)

# Инициализируем менеджер анекдотов
joke_manager = JokeManager()

# Планировщик для ежедневного обновления анекдотов
async def daily_jokes_update(context: ContextTypes.DEFAULT_TYPE):
    joke_manager.fetch_new_jokes()
    logger.info("База данных анекдотов обновлена.")

# Функция для отправки первого напоминания
async def send_first_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.chat_id
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="Эй, чего скучаешь?"
        )
        # Планируем второе напоминание через 49.5 часов
        context.job_queue.run_once(
            send_second_reminder,
            when=timedelta(hours=49.5),
            chat_id=user_id,
            name=str(user_id) + '_second_reminder'
        )
    except Exception as e:
        logger.error(f'Ошибка при отправке первого напоминания пользователю {user_id}: {e}')

# Функция для отправки второго напоминания
async def send_second_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.chat_id
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="Я соскучился 🥺"
        )
    except Exception as e:
        logger.error(f'Ошибка при отправке второго напоминания пользователю {user_id}: {e}')

# Функция для планирования напоминания
def schedule_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    # Отменяем существующие напоминания
    current_jobs = context.job_queue.get_jobs_by_name(str(user_id) + '_first_reminder')
    for job in current_jobs:
        job.schedule_removal()
    current_jobs = context.job_queue.get_jobs_by_name(str(user_id) + '_second_reminder')
    for job in current_jobs:
        job.schedule_removal()
    # Планируем новое напоминание через 47 часов
    context.job_queue.run_once(
        send_first_reminder,
        when=timedelta(hours=47),
        chat_id=user_id,
        name=str(user_id) + '_first_reminder'
    )

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    joke_manager.record_user_interaction(user.id)
    schedule_reminder(context, user.id)
    keyboard = [
        [KeyboardButton('Новый анекдот'), KeyboardButton('Лучший анекдот')]
    ]
    greeting = f"Привет, {user.first_name}! 😊\n\nЯ бот, который рассказывает анекдоты. Хочешь посмеяться или узнать лучший анекдот? Выбери опцию ниже:"
    await update.message.reply_text(
        greeting,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

# Обработчик команды /newjoke
async def new_joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    joke_manager.record_user_interaction(user_id)
    schedule_reminder(context, user_id)
    joke_id, joke = joke_manager.get_new_joke_for_user(user_id)
    if joke:
        joke_text = joke['text']
        joke_manager.record_joke_sent(user_id, joke_id)
        await send_joke(update, joke_text, joke_id)
    else:
        await update.message.reply_text("Извините, анекдоты временно недоступны. Попробуйте позже.")

# Обработчик команды /bestjoke
async def best_joke_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    joke_manager.record_user_interaction(user_id)
    schedule_reminder(context, user_id)
    joke_id, joke = joke_manager.get_best_joke_for_user(user_id)
    if joke:
        joke_text = joke['text']
        joke_manager.record_joke_sent(user_id, joke_id)
        await send_joke(update, joke_text, joke_id)
    else:
        await update.message.reply_text("Извините, анекдоты временно недоступны. Попробуйте позже.")

# Функция для отправки анекдота
async def send_joke(update: Update, joke_text: str, joke_id: str):
    user_id = update.effective_user.id
    # Получаем данные пользователя
    user_data = joke_manager.user_data.get(str(user_id), {})
    jokes_sent = len(user_data.get('jokes_seen', []))
    ad_offset = user_data.get('ad_offset', 0)
    if (jokes_sent + ad_offset) % 5 == 0:
        # Добавляем рекламу в каждый пятый анекдот
        joke_text_with_ad = f"{joke_text}\n\nПодписывайтесь на наш канал @your_channel"
    else:
        joke_text_with_ad = joke_text
    # Создаем инлайн-кнопки для голосования
    keyboard = [
        [
            InlineKeyboardButton("😂", callback_data=f'like_{joke_id}'),
            InlineKeyboardButton("😒", callback_data=f'dislike_{joke_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(joke_text_with_ad, reply_markup=reply_markup)

# Обработчик выбора пользователя
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    joke_manager.record_user_interaction(user_id)
    schedule_reminder(context, user_id)
    text = update.message.text.strip()
    if text == 'Новый анекдот':
        joke_id, joke = joke_manager.get_new_joke_for_user(user_id)
    elif text == 'Лучший анекдот':
        joke_id, joke = joke_manager.get_best_joke_for_user(user_id)
    else:
        await update.message.reply_text("Пожалуйста, выберите один из вариантов.")
        return
    if joke:
        joke_text = joke['text']
        joke_manager.record_joke_sent(user_id, joke_id)
        await send_joke(update, joke_text, joke_id)
    else:
        await update.message.reply_text("Извините, анекдоты временно недоступны. Попробуйте позже.")

# Обработчик голосования
async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    joke_manager.record_user_interaction(user_id)
    schedule_reminder(context, user_id)
    if data.startswith('like_'):
        joke_id = data.split('_')[1]
        joke_manager.update_joke_rating(joke_id, 1)
        await query.answer("Спасибо за ваш лайк! 👍")
    elif data.startswith('dislike_'):
        joke_id = data.split('_')[1]
        joke_manager.update_joke_rating(joke_id, -1)
        await query.answer("Спасибо за ваш отзыв! 🤔")
    else:
        await query.answer()

# Обработчик неизвестных команд
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Извините, я не понимаю эту команду. Пожалуйста, используйте меню или команды /newjoke и /bestjoke.")

# Основная функция
def main():
    # Инициализируем бота
    TOKEN = '7676676474:AAHXb74U1IIkOZYskLJkNAYn-StIo1H_u7M'  # Замените 'ВАШ_ТОКЕН' на токен вашего бота
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable not set.")
        return
    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', start))  # Команда /help будет вызывать старт
    application.add_handler(CommandHandler('newjoke', new_joke_command))
    application.add_handler(CommandHandler('bestjoke', best_joke_command))

    # Обработчик выбора пользователя
    choice_filter = filters.Regex('^(Новый анекдот|Лучший анекдот)$')
    application.add_handler(MessageHandler(choice_filter, handle_choice))

    # Обработчик инлайн-кнопок
    application.add_handler(CallbackQueryHandler(vote_callback))

    # Обработчик неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Обработчик неизвестных сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_command))

    # Устанавливаем команды бота
    commands = [
        BotCommand('start', 'Начать взаимодействие с ботом'),
        BotCommand('help', 'Получить помощь'),
        BotCommand('newjoke', 'Получить новый анекдот'),
        BotCommand('bestjoke', 'Получить лучший анекдот'),
    ]
    application.bot.set_my_commands(commands)

    # Планируем ежедневное обновление анекдотов
    application.job_queue.run_repeating(
        daily_jokes_update,
        interval=timedelta(hours=24),
        first=timedelta(seconds=0)
    )

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
