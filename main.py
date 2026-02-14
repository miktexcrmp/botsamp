import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile
from openai import AsyncOpenAI

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8383278594:AAG-AXod5yB7OKzYQpJBdCzo-csvTH12gA0"
OPENAI_API_KEY = "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"

# Пути к файлам (настрой под свою ОС)
# Если Linux, то просто "./compiler/pawncc"
COMPILER_PATH = r"compiler\pawncc.exe" 
INCLUDE_PATH = r"includes"
TEMP_FOLDER = "temp"

# Настройка клиента AI
# Если используешь OpenRouter, раскомментируй строку base_url
client = AsyncOpenAI(
    api_key=OPENAI_API_KEY,
    # base_url="https://openrouter.ai/api/v1" 
)

# Включаем логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- МАШИНА СОСТОЯНИЙ (FSM) ---
class ModWork(StatesGroup):
    waiting_for_file = State()       # Ждем файл .pwn
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

    # 4. Отправка результатов
    if os.path.exists(amx_path):
        # Успех
        input_pwn = FSInputFile(file_path, filename=f"FIXED_{original_name}")
        input_amx = FSInputFile(amx_path, filename=f"FIXED_{original_name.replace('.pwn', '.amx')}")

        await message.answer_document(input_pwn, caption="Исходный код (исправленный)")
        await message.answer_document(input_amx, caption="Скомпилированный мод (.amx)")
        await message.answer("Готово. Ошибок не обнаружено.")
    else:
        # Провал
        # Если лог слишком длинный, режем его
        if len(output_log) > 3500:
            output_log = output_log[:3500] + "\n... (лог обрезан)"
            
        await message.answer(f"Компиляция не удалась. Ошибки:\n{output_log}")
        input_pwn = FSInputFile(file_path, filename=f"FAILED_{original_name}")
        await message.answer_document(input_pwn, caption="Попытка исправления (код с ошибками)")

    # Сбрасываем состояние
    await state.clear()

# Запуск
async def main():
    if not os.path.exists(TEMP_FOLDER):
        os.makedirs(TEMP_FOLDER)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
      
