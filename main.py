import asyncio
import os
import logging
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from openai import AsyncOpenAI

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8383278594:AAG-AXod5yB7OKzYQpJBdCzo-csvTH12gA0"
OPENAI_API_KEY = "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"

# Пути для Linux (Koyeb)
COMPILER_PATH = "./compiler/pawncc" 
INCLUDE_PATH = "./includes"
TEMP_FOLDER = "temp"

# --- ВЕБ-СЕРВЕР ДЛЯ ПОДДЕРЖКИ ЖИЗНИ ---
app = Flask(__name__)
@app.route('/')
def health(): return "AI_PAWN_READY", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Исправленная инициализация клиента (без лишних аргументов)
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class ModWork(StatesGroup):
    waiting_for_file = State()
    waiting_for_instruction = State()

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Я ИИ-разработчик SAMP.\nПришли файл .pwn или .txt с кодом.")
    await state.set_state(ModWork.waiting_for_file)

@dp.message(StateFilter(ModWork.waiting_for_file), F.document)
async def process_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name
    if not (file_name.endswith('.pwn') or file_name.endswith('.txt')):
        return await message.answer("Ошибка: Нужен файл .pwn или .txt")

    file = await bot.get_file(message.document.file_id)
    local_path = os.path.join(TEMP_FOLDER, f"{message.from_user.id}_{file_name}")
    
    if not os.path.exists(TEMP_FOLDER): os.makedirs(TEMP_FOLDER)
    await bot.download_file(file.file_path, local_path)
    await state.update_data(file_path=local_path, original_name=file_name)
    
    await message.answer("Файл получен. Что в нем изменить или добавить?")
    await state.set_state(ModWork.waiting_for_instruction)

@dp.message(StateFilter(ModWork.waiting_for_instruction), F.text)
async def process_instruction(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_path = data['file_path']
    original_name = data['original_name']
    instruction = message.text
    status_msg = await message.answer("🤖 ИИ анализирует код...")

    try:
        with open(file_path, 'r', encoding='cp1251', errors='ignore') as f:
            code = f.read()

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты мастер Pawn SAMP. Верни ТОЛЬКО код без markdown."},
                {"role": "user", "content": f"Задача: {instruction}\n\nКод:\n{code[:30000]}"}
            ]
        )
        
        new_code = response.choices[0].message.content.replace("```pawn", "").replace("```", "")
        with open(file_path, 'w', encoding='cp1251') as f:
            f.write(new_code)

        await status_msg.edit_text("✅ Код обновлен. Компилирую...")

        amx_path = file_path.replace(".pwn", ".amx").replace(".txt", ".amx")
        os.system(f"chmod +x {COMPILER_PATH}")
        
        process = await asyncio.create_subprocess_exec(
            COMPILER_PATH, file_path, f"-o{amx_path}", f"-i{INCLUDE_PATH}", "-;+", "-(+",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if os.path.exists(amx_path):
            await message.answer_document(FSInputFile(file_path, filename=f"FIXED_{original_name}"))
            await message.answer_document(FSInputFile(amx_path, filename=f"FIXED_{original_name.replace('.pwn', '.amx')}"))
        else:
            log = (stdout + stderr).decode('cp1251', errors='ignore')
            await message.answer(f"Ошибка компиляции:\n{log[:1000]}")

    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    await state.clear()

async def main():
    Thread(target=run_web, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    waiting_for_instruction = State() # Ждем описание задачи

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет. Я бот-разработчик SAMP.\n"
        "Отправь мне файл мода (.pwn) или текстовый файл (.txt) с кодом."
    )
    await state.set_state(ModWork.waiting_for_file)

@dp.message(StateFilter(ModWork.waiting_for_file), F.document)
async def process_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name
    if not (file_name.endswith('.pwn') or file_name.endswith('.txt')):
        await message.answer("Ошибка: Мне нужен файл .pwn или .txt")
        return

    file_id = message.document.file_id
    file = await bot.get_file(file_id)
    
    # Формируем путь: temp/user_id_filename
    local_path = os.path.join(TEMP_FOLDER, f"{message.from_user.id}_{file_name}")
    
    await bot.download_file(file.file_path, local_path)
    
    # Сохраняем путь к файлу в память состояния
    await state.update_data(file_path=local_path, original_name=file_name)
    
    await message.answer(
        "Файл получен. Теперь напиши текстом, что нужно сделать.\n"
        "Пример: 'Исправь ошибку в команде /makeleader' или 'Добавь систему голода'."
    )
    await state.set_state(ModWork.waiting_for_instruction)

@dp.message(StateFilter(ModWork.waiting_for_instruction), F.text)
async def process_instruction(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_path = data['file_path']
    original_name = data['original_name']
    instruction = message.text

    status_msg = await message.answer("Анализирую код и вношу изменения... Это может занять минуту.")

    # 1. Читаем файл (в кодировке Windows-1251, стандарт для SAMP)
    try:
        with open(file_path, 'r', encoding='cp1251', errors='ignore') as f:
            code = f.read()
    except Exception as e:
        await status_msg.edit_text(f"Ошибка чтения файла: {e}")
        return

    # Проверка длины (GPT имеет лимит)
    # Если код огромный, лучше обрезать или использовать специальную логику (RAG)
    # Здесь мы берем первые 30000 символов и последние 5000 для контекста, если файл огромный
    if len(code) > 100000:
        code_context = code[:20000] + "\n...[код пропущен]...\n" + code[-5000:]
        await message.answer("Предупреждение: Файл слишком большой. Я прочитаю только начало и конец для контекста.")
    else:
        code_context = code

    # 2. Запрос к AI
    try:
        response = await client.chat.completions.create(
            model="gpt-4-turbo", # Или gpt-4o
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "Ты профессиональный Pawn скриптер (SAMP). "
                        "Твоя задача: изменить присланный код согласно инструкции. "
                        "ВЕРНИ ТОЛЬКО ПОЛНЫЙ ИСПРАВЛЕННЫЙ КОД БЕЗ MARKDOWN РАЗМЕТКИ (```). "
                        "Не пиши объяснений, только готовый код для компиляции. "
                        "Сохраняй кодировку cp1251 совместимость."
                    )
                },
                {
                    "role": "user", 
                    "content": f"Инструкция: {instruction}\n\nКод мода:\n{code_context}"
                }
            ],
            max_tokens=4096 
        )
        
        new_code = response.choices[0].message.content
        # Убираем возможные маркеры markdown, если AI их добавил
        new_code = new_code.replace("```pawn", "").replace("```", "")

        # Перезаписываем файл
        with open(file_path, 'w', encoding='cp1251') as f:
            f.write(new_code)

    except Exception as e:
        await status_msg.edit_text(f"Ошибка AI: {e}")
        return

    await status_msg.edit_text("Код обновлен. Начинаю компиляцию...")

    # 3. Компиляция
    # Генерируем имя для .amx
    amx_path = file_path.replace(".pwn", ".amx").replace(".txt", ".amx")
    
    # Аргументы: путь к pwn, путь вывода amx, папка инклудов
    # Флаги: -;+ (требовать ;), -(+ (требовать скобки), -d3 (отладка)
    args = [
        COMPILER_PATH,
        file_path,
        f"-o{amx_path}",
        f"-i{INCLUDE_PATH}",
        "-;+",
        "-(+"
    ]

    # Запускаем процесс асинхронно
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    output_log = stdout.decode('cp1251', errors='ignore') + stderr.decode('cp1251', errors='ignore')

import asyncio
import os
import logging
import time
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from openai import AsyncOpenAI

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8383278594:AAG-AXod5yB7OKzYQpJBdCzo-csvTH12gA0"
OPENAI_API_KEY = "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"

# Пути для Linux (Koyeb)
COMPILER_PATH = "./compiler/pawncc" 
INCLUDE_PATH = "./includes"
TEMP_FOLDER = "temp"

# --- FLASK ДЛЯ KOYEB (ЧТОБЫ НЕ ПАДАЛ) ---
app = Flask(__name__)
@app.route('/')
def health(): return "AI_PAWN_DEV_ACTIVE", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Настройка ИИ
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class ModWork(StatesGroup):
    waiting_for_file = State()
    waiting_for_instruction = State()

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Привет! Я ИИ-разработчик SAMP.\nПришли файл .pwn или .txt с кодом.")
    await state.set_state(ModWork.waiting_for_file)

@dp.message(StateFilter(ModWork.waiting_for_file), F.document)
async def process_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name
    if not (file_name.endswith('.pwn') or file_name.endswith('.txt')):
        return await message.answer("Ошибка: Нужен файл .pwn или .txt")

    file = await bot.get_file(message.document.file_id)
    local_path = os.path.join(TEMP_FOLDER, f"{message.from_user.id}_{file_name}")
    
    await bot.download_file(file.file_path, local_path)
    await state.update_data(file_path=local_path, original_name=file_name)
    
    await message.answer("Файл получен. Теперь напиши, что нужно исправить или добавить.")
    await state.set_state(ModWork.waiting_for_instruction)

@dp.message(StateFilter(ModWork.waiting_for_instruction), F.text)
async def process_instruction(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_path = data['file_path']
    original_name = data['original_name']
    instruction = message.text

    status_msg = await message.answer("🤖 ИИ анализирует и правит код...")

    try:
        with open(file_path, 'r', encoding='cp1251', errors='ignore') as f:
            code = f.read()

        # Ограничение контекста для стабильности
        code_context = code[:35000] if len(code) > 35000 else code

        response = await client.chat.completions.create(
            model="gpt-4o-mini", # Можно сменить на gpt-4o
            messages=[
                {"role": "system", "content": "Ты мастер Pawn SAMP. Верни ТОЛЬКО исправленный код. Без markdown (```)."},
                {"role": "user", "content": f"Инструкция: {instruction}\n\nКод:\n{code_context}"}
            ]
        )
        
        new_code = response.choices[0].message.content.replace("```pawn", "").replace("```", "")

        with open(file_path, 'w', encoding='cp1251') as f:
            f.write(new_code)

        await status_msg.edit_text("✅ Код обновлен. Компилирую...")

        amx_path = file_path.replace(".pwn", ".amx").replace(".txt", ".amx")
        
        # Даем права компилятору
        os.system(f"chmod +x {COMPILER_PATH}")
        
        process = await asyncio.create_subprocess_exec(
            COMPILER_PATH, file_path, f"-o{amx_path}", f"-i{INCLUDE_PATH}", "-;+", "-(+",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        output_log = (stdout + stderr).decode('cp1251', errors='ignore')

        if os.path.exists(amx_path):
            await message.answer_document(FSInputFile(file_path, filename=f"FIXED_{original_name}"), caption="Исправленный код")
            await message.answer_document(FSInputFile(amx_path, filename=f"FIXED_{original_name.replace('.pwn', '.amx')}"), caption="Скомпилированный .AMX")
        else:
            await message.answer_document(FSInputFile(file_path), caption=f"Ошибка компиляции:\n{output_log[:1000]}")

    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    
    await state.clear()

# --- ЗАПУСК ---
async def main():
    if not os.path.exists(TEMP_FOLDER): os.makedirs(TEMP_FOLDER)
    if not os.path.exists("compiler"): os.makedirs("compiler")
    if not os.path.exists("includes"): os.makedirs("includes")
    
    # Запуск Flask в отдельном потоке
    Thread(target=run_web, daemon=True).start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
