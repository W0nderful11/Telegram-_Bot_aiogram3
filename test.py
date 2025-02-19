import logging
import random
import wikipedia
import ollama
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardRemove
from pymongo import MongoClient
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()
#BOT_TOKEN = os.getenv("BOT_TOKEN")
#MONGO_URL = os.getenv("MONGO_URL")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключение к MongoDB
client = MongoClient(MONGO_URL)
db = client["bot_database"]
users_collection = db["users"]

# Устанавливаем язык Wikipedia
wikipedia.set_lang("ru")

# Состояния
class MailingState(StatesGroup):
    waiting_for_message = State()

class WikiState(StatesGroup):
    waiting_for_query = State()

# Главное меню
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/game"), KeyboardButton(text="/wiki")],
        [KeyboardButton(text="/mailing"), KeyboardButton(text="/show_all")]
    ],
    resize_keyboard=True
)

# Приветственное сообщение с командами
WELCOME_MESSAGE = """
Привет! Я бот, который может:
🪨✂️📜 Играть в камень-ножницы-бумагу — /game
📖🔍 Искать информацию в Википедии — /wiki
📩📢 Отправлять рассылку — /mailing
👥📜 Показать всех пользователей — /show_all

Просто выбери команду из меню или напиши мне что-нибудь! 😊
"""

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id})

    await message.answer(WELCOME_MESSAGE, reply_markup=menu_keyboard)

# Инлайн-клавиатура для игры
game_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Камень", callback_data="rock"),
     InlineKeyboardButton(text="Ножницы", callback_data="scissors"),
     InlineKeyboardButton(text="Бумага", callback_data="paper")],
    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
])

@dp.message(Command("game"))
async def cmd_game(message: types.Message):
    await message.answer("Выберите вариант:", reply_markup=game_keyboard)

@dp.callback_query(F.data.in_(["rock", "scissors", "paper"]))
async def process_game_choice(callback: types.CallbackQuery):
    user_choice = callback.data
    bot_choice = random.choice(["rock", "scissors", "paper"])

    choices = {"rock": "Камень", "scissors": "Ножницы", "paper": "Бумага"}
    user_text = choices[user_choice]
    bot_text = choices[bot_choice]

    result = determine_winner(user_choice, bot_choice)
    await callback.message.edit_text(f"Вы выбрали: {user_text}\nБот выбрал: {bot_text}\nРезультат: {result}",
                                     reply_markup=game_keyboard)

def determine_winner(user_choice, bot_choice):
    if user_choice == bot_choice:
        return "Ничья!"
    elif (user_choice == "rock" and bot_choice == "scissors") or \
            (user_choice == "scissors" and bot_choice == "paper") or \
            (user_choice == "paper" and bot_choice == "rock"):
        return "Вы победили!"
    return "Бот победил!"

@dp.message(Command("wiki"))
async def cmd_wiki(message: types.Message, state: FSMContext):
    await message.answer("Введите запрос для поиска в Википедии:")
    await state.set_state(WikiState.waiting_for_query)

@dp.message(StateFilter(WikiState.waiting_for_query))
async def process_wiki_query(message: types.Message, state: FSMContext):
    query = message.text + "?"  # Добавляем "?" в конец запроса
    search_result = search_wikipedia(query)
    await message.answer(search_result)
    await state.clear()  # Сбрасываем состояние

@dp.message(Command("mailing"))
async def cmd_mailing(message: types.Message, state: FSMContext):
    await message.answer("Введите сообщение для рассылки:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(MailingState.waiting_for_message)

@dp.message(StateFilter(MailingState.waiting_for_message))
async def process_mailing_message(message: types.Message, state: FSMContext):
    mailing_text = message.text
    users = users_collection.find({}, {"user_id": 1})

    for user in users:
        try:
            await bot.send_message(chat_id=user["user_id"], text=mailing_text)
        except Exception as e:
            logging.error(f"Ошибка отправки пользователю {user['user_id']}: {e}")

    await message.answer("Рассылка отправлена всем пользователям.", reply_markup=menu_keyboard)
    await state.clear()

@dp.message(Command("show_all"))
async def show_all_users(message: types.Message):
    users = list(users_collection.find({}, {"user_id": 1}))
    if not users:
        await message.answer("Нет зарегистрированных пользователей.")
        return

    user_ids = [str(user["user_id"]) for user in users]
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]

    for chunk in chunks:
        await message.answer("Список ID пользователей:\n" + "\n".join(chunk))

@dp.callback_query(F.data == "back_to_menu")
async def callback_back(callback: types.CallbackQuery):
    await cmd_start(callback.message)  # Возвращаем пользователя в главное меню
    await callback.answer()

def search_wikipedia(query: str):
    try:
        page = wikipedia.page(query)
        summary = wikipedia.summary(query, sentences=5)
        return f"📚 Результат поиска:\n\n{summary}\n\n🔗 Источник: {page.url}"
    except wikipedia.exceptions.PageError:
        return "❌ По вашему запросу ничего не найдено."
    except wikipedia.exceptions.DisambiguationError as e:
        options = "\n".join(e.options[:5])
        return f"🔍 Уточните запрос. Возможные варианты:\n\n{options}"
    except Exception as e:
        return f"⚠️ Произошла ошибка при поиске: {str(e)}"

@dp.message(F.text & ~F.text.startswith("/"))
async def process_message(message: types.Message, state: FSMContext):
    if await state.get_state() == MailingState.waiting_for_message:
        return

    # Обработка игровых предложений
    text = message.text.lower()
    game_triggers = ["игра", "поиграть", "сыграем", "game", "играть"]
    if any(trigger in text for trigger in game_triggers):
        await message.answer("🎮 Давайте сыграем! Используйте команду /game", reply_markup=menu_keyboard)
        return

    # Обработка запросов к Ollama
    try:
        # Добавляем контекст для модели
        context = [
            {"role": "system", "content": "Ты — помощник Stratton — это твое имя и ты компания для помощи."},
            {"role": "user", "content": message.text}
        ]
        response = ollama.chat(model="llama3.2", messages=context)
        answer = response.get('message', {}).get('content', '').strip()
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Ошибка Ollama: {e}")
        await message.answer("Извините, не удалось обработать ваш запрос.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())