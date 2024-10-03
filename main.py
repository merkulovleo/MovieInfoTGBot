import logging
import requests
import os.path
import os

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext 

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
KINPOISK_API_KEY = os.getenv("KINPOISK_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Scopes для работы с Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Храним название фильма для добавления в таблицу
current_movie_info = {}

# Функция для получения информации о фильме из Кинопоиска
def fetch_movie_info(title):
    logger.info(f"Запрашиваем информацию о фильме: {title}")
    url = f"https://api.kinopoisk.dev/v1.3/movie?token={KINPOISK_API_KEY}&field=name&search={title}&limit=1"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        logger.info(f"Ответ от API Кинопоиска: {data}")
        if data['docs']:
            movie = data['docs'][0]
            movie_title = movie['name']
            movie_year = movie['year']
            genres = ", ".join([genre['name'] for genre in movie['genres']])
            description = movie.get('description', 'Описание отсутствует.')
            poster_url = movie['poster']['url'] if movie['poster'] else None
            return movie_title, movie_year, genres, description, poster_url
        else:
            return None
    else:
        logger.error(f"Ошибка API Кинопоиска: {response.status_code}")
        return None

# Обработчик команды /start
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Привет! Нажмите на кнопку ниже, чтобы начать поиск фильма.", 
                                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Найти фильм", callback_data="search_film")]]))

# Обработчик команды для начала поиска фильма
async def search_film(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Введите название фильма:")

# Обработчик текстового сообщения - получения названия фильма
async def receive_movie_title(update: Update, context: CallbackContext) -> None:
    title = update.message.text
    logger.info(f"Получено название фильма: {title}")
    
    # Запрашиваем информацию о фильме
    movie_info = fetch_movie_info(title)
    
    if movie_info:
        movie_title, movie_year, movie_genres, movie_description, poster_url = movie_info
        global current_movie_info
        current_movie_info = {
            "title": movie_title,
            "year": movie_year,
            "genres": movie_genres
        }
        
        # Создаем текст сообщения с постером и описанием
        message = f"<b>Название:</b> {movie_title}\n<b>Год:</b> {movie_year}\n<b>Жанры:</b> {movie_genres}\n<b>Описание:</b> {movie_description}"

        # Отправляем постер и текст в одном сообщении
        if poster_url:
            await update.message.reply_photo(photo=poster_url, caption=message, parse_mode="HTML")
        else:
            await update.message.reply_text(message, parse_mode="HTML")

        # Создаем кнопки для выбора действий
        keyboard = [
            [InlineKeyboardButton("Найти другой фильм", callback_data="search_another")],
            [InlineKeyboardButton("Добавить в Google Таблицу", callback_data="add_to_sheet")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Что вы хотите сделать дальше?", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Фильм не найден. Попробуйте ввести другое название.")

# Обработчик выбора действия с кнопок
async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "search_another":
        await query.message.reply_text("Введите название другого фильма.")
    elif query.data == "add_to_sheet":
        await add_movie_to_sheet(query.message, context)

# Функция для добавления фильма в Google Таблицу
async def add_movie_to_sheet(message, context: CallbackContext) -> None:
    logger.info(f"Добавляем фильм в Google Таблицу: {current_movie_info}")
    try:
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        service = build('sheets', 'v4', credentials=creds)

        # Добавляем данные в Google Таблицу
        sheet = service.spreadsheets()
        values = [[current_movie_info["title"], current_movie_info["year"], current_movie_info["genres"]]]
        body = {
            'values': values
        }
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range="Sheet1!A:C",
            valueInputOption="RAW",
            body=body
        ).execute()

        await message.reply_text(f"Фильм '{current_movie_info['title']}' успешно добавлен в Google Таблицу!")
    except Exception as e:
        logger.error(f"Ошибка при добавлении данных в таблицу: {e}")
        await message.reply_text(f"Ошибка при добавлении данных в таблицу.")

# Основная функция запуска бота
def main() -> None:
    # Создаем приложение Telegram Bot
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_movie_title))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()