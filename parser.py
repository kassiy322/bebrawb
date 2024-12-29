import asyncio
import json
import logging
import os
import random
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiohttp import ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BOT_TOKEN = "7929496116:AAHQg6ZqFy-Fo7cWoYDLaVZ6oCg0gOdz318"
CHECK_INTERVAL = 3600
DATA_FILE = "tracked_items.json"
TIMEOUT = ClientTimeout(total=30)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

def get_random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }

tracked_items = {}
adding_discount = {}  # Словарь для хранения информации о добавлении скидки

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(tracked_items, f)

def extract_product_id(url):
    match = re.search(r'/catalog/(\d+)/', url)
    if match:
        return match.group(1)
    return None

async def fetch_prices(url):
    product_id = extract_product_id(url)
    if not product_id:
        return None, None

    api_url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=27&nm={product_id}"

    await asyncio.sleep(random.uniform(1, 5))

    try:
        async with ClientSession(timeout=TIMEOUT) as session:
            async with session.get(api_url, headers=get_random_headers()) as response:
                if response.status == 200:
                    data = await response.json()
                    try:
                        product_data = data['data']['products'][0]
                        current_price = product_data['salePriceU'] // 100
                        old_price = product_data.get('priceU', current_price) // 100
                        return current_price, old_price
                    except (KeyError, IndexError) as e:
                        logger.error(f"Error parsing price from API response: {str(e)}")
                else:
                    logger.error(f"API request failed with status {response.status}")
    except Exception as e:
        logger.error(f"Error fetching price: {str(e)}")
    return None, None

async def check_prices(bot: Bot):
    while True:
        try:
            for user_id, items in tracked_items.items():
                for url, data in items.items():
                    old_price = data['price']
                    current_price, original_price = await fetch_prices(url)
                    if current_price and current_price != old_price:
                        price_diff = original_price - current_price
                        percent_diff = round((price_diff / original_price) * 100, 2)
                        response_message = (f"💰 Изменение цены!\n"
                                           f"🔗 {url}\n"
                                           f"📉 Старая цена: {original_price}₽\n"
                                           f"📈 Текущая цена: {current_price}₽\n"
                                           f"💸 Снижение: {price_diff}₽ ({percent_diff}%)\n")
                        if 'discount_price' in data:
                            response_message += f"Цена с учетом личной скидки WB кошелька: {data['discount_price']}₽\n"
                        response_message += f"{'🔥 Цена снизилась!' if current_price < original_price else '⚠️ Цена выросла!'}"
                        try:
                            await bot.send_message(user_id, response_message)
                            tracked_items[user_id][url]['price'] = current_price
                            save_data()
                        except Exception as e:
                            logger.error(f"Message error {user_id}: {str(e)}")
            await asyncio.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"Check prices error: {str(e)}")
            await asyncio.sleep(60)

async def main():
    global tracked_items
    tracked_items = load_data()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Создаем клавиатуру с новой кнопкой
    start_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Отслеживать товар")],
            [KeyboardButton(text="Список отслеживаемых")],
            [KeyboardButton(text="Остановить отслеживание")],
            [KeyboardButton(text="Остановить всё отслеживание")],
            [KeyboardButton(text="Добавить скидку WB кошелька")]  # Новая кнопка
        ],
        resize_keyboard=True
    )

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        logger.info("Отправка клавиатуры пользователю")
        await message.answer(
            "🤖 Бот мониторинга цен Wildberries\n\n"
            "Выберите действие:",
            reply_markup=start_keyboard
        )

    @dp.message(lambda message: message.text == "Отслеживать товар")
    async def track_item(message: types.Message):
        await message.answer("Введите URL товара для отслеживания:")

    @dp.message(lambda message: message.text == "Список отслеживаемых")
    async def list_items(message: types.Message):
        user_id = str(message.from_user.id)
        if user_id not in tracked_items or not tracked_items[user_id]:
            await message.answer("📋 Нет отслеживаемых товаров")
            return

        items_list = []
        for url, data in tracked_items[user_id].items():
            current_price, original_price = await fetch_prices(url)
            if current_price:
                price_diff = original_price - current_price
                percent_diff = round((price_diff / original_price) * 100, 2)
                item_message = (f"💰 Изменение цены!\n"
                               f"🔗 {url}\n"
                               f"📉 Старая цена: {original_price}₽\n"
                               f"📈 Текущая цена: {current_price}₽\n"
                               f"💸 Снижение: {price_diff}₽ ({percent_diff}%)\n")
                if 'discount_price' in data:
                    item_message += f"Цена с учетом личной скидки WB кошелька: {data['discount_price']}₽\n"
                item_message += f"{'🔥 Цена снизилась!' if current_price < original_price else '⚠️ Цена выросла!'}"
                items_list.append(item_message)

        await message.answer("📋 Отслеживаемые товары:\n\n" + "\n\n".join(items_list))

    @dp.message(lambda message: message.text == "Остановить отслеживание")
    async def stop_tracking(message: types.Message):
        await message.answer("Введите URL товара, чтобы остановить отслеживание:")

    @dp.message(lambda message: "wildberries.ru" in message.text and tracked_items.get(str(message.from_user.id), {}))
    async def handle_stop_tracking_url(message: types.Message):
        user_id = str(message.from_user.id)
        if user_id in adding_discount and adding_discount[user_id]:  # Проверяем, что пользователь добавляет скидку
            url = message.text.strip()
            if user_id in tracked_items and url in tracked_items[user_id]:
                adding_discount[user_id] = url  # Сохраняем URL для следующего шага
                await message.answer("Введите цену с учетом скидки WB кошелька:")
            else:
                await message.answer(f"❌ Товар {url} не найден в списке отслеживаемых")
                adding_discount[user_id] = False  # Сбрасываем состояние
        else:
            # Если пользователь не добавляет скидку, обрабатываем как обычный URL
            url = message.text.strip()
            if user_id in tracked_items and url in tracked_items[user_id]:
                del tracked_items[user_id][url]
                save_data()
                await message.answer(f"✅ Отслеживание товара {url} остановлено")
            else:
                await message.answer(f"❌ Товар {url} не найден в списке отслеживаемых")

    @dp.message(lambda message: message.text == "Остановить всё отслеживание")
    async def stop_all_tracking(message: types.Message):
        user_id = str(message.from_user.id)
        if user_id in tracked_items and tracked_items[user_id]:
            tracked_items[user_id] = {}
            save_data()
            await message.answer("✅ Все отслеживания остановлены")
        else:
            await message.answer("❌ Нет активных отслеживаний")

    @dp.message(lambda message: message.text == "Добавить скидку WB кошелька")
    async def add_wb_discount(message: types.Message):
        user_id = str(message.from_user.id)
        adding_discount[user_id] = True  # Указываем, что пользователь добавляет скидку
        await message.answer("Введите URL товара, для которого хотите добавить скидку WB кошелька:")

    @dp.message(lambda message: message.text.isdigit() and str(message.from_user.id) in adding_discount)
    async def handle_wb_discount_price(message: types.Message):
        user_id = str(message.from_user.id)
        discount_price = int(message.text.strip())
        url = adding_discount[user_id]  # Получаем сохраненный URL
        if user_id in tracked_items and url in tracked_items[user_id]:
            tracked_items[user_id][url]['discount_price'] = discount_price
            save_data()
            await message.answer(f"✅ Цена с учетом скидки WB кошелька для товара {url} сохранена: {discount_price}₽")
        else:
            await message.answer(f"❌ Товар {url} не найден в списке отслеживаемых")
        adding_discount[user_id] = False  # Сбрасываем состояние

    @dp.message(lambda message: "wildberries.ru" in message.text and not tracked_items.get(str(message.from_user.id), {}))
    async def handle_track_url(message: types.Message):
        url = message.text.strip()
        await message.answer("⏳ Получаю цену...")
        current_price, original_price = await fetch_prices(url)
        if current_price:
            user_id = str(message.from_user.id)
            if user_id not in tracked_items:
                tracked_items[user_id] = {}
            tracked_items[user_id][url] = {'price': current_price}
            save_data()
            price_diff = original_price - current_price
            percent_diff = round((price_diff / original_price) * 100, 2)
            response_message = (f"💰 Изменение цены!\n"
                               f"🔗 {url}\n"
                               f"📉 Старая цена: {original_price}₽\n"
                               f"📈 Текущая цена: {current_price}₽\n"
                               f"💸 Снижение: {price_diff}₽ ({percent_diff}%)\n"
                               f"{'🔥 Цена снизилась!' if current_price < original_price else '⚠️ Цена выросла!'}")
            await message.answer(response_message)
        else:
            await message.answer("❌ Не удалось получить цену")

    asyncio.create_task(check_prices(bot))

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())