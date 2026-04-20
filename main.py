import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from config import BOT_TOKEN, ADMIN_IDS, BISTRO_NAME, BISTRO_PHONE, BISTRO_ADDRESS, MIN_ORDER_SUM, DELIVERY_TIME
from menu import MENU

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def is_working_time():
    """Проверяет, работает ли бистро в текущее время"""
    utc_now = datetime.now(timezone.utc)
    msk_time = utc_now + timedelta (hours=3)
    closing_time = msk_time.replace(hour=21, minute=00, second=0, microsecond=0)
    return msk_time < closing_time

def get_working_hours():
    """Возвращает строку с часами работы"""
    return "🕐 08:00 - 21:30"

def get_status_emoji():
    """Возвращает статус работы"""
    return "🟢 ОТКРЫТО" if is_working_time() else "🔴 ЗАКРЫТО"

def get_closing_message():
    """Возвращает сообщение о закрытии"""
    return (
        "⏰ **ВНИМАНИЕ!**\n\n"
        "Заказы принимаются только **до 21:30** по московскому времени.\n"
        "🍽 Завтра ждём вас снова!"
    )

async def check_order_time(update: Update, _: ContextTypes.DEFAULT_TYPE):
    """Проверяет время и отправляет сообщение о закрытии"""
    if not is_working_time():
        await update.message.reply_text(
            get_closing_message(),
            parse_mode='Markdown'
        )
        return False
    return True
# ==================== СОСТОЯНИЯ ====================
(
    CHOOSING_TYPE,
    TYPING_NAME,
    TYPING_PHONE,
    TYPING_ADDRESS,
    CONFIRMING_ORDER,
    ASK_DELIVERY_ZONE
) = range(6)


# ==================== ХРАНИЛИЩЕ ДАННЫХ ====================
class DataStore:
    def __init__(self):
        self.carts = {}
        self.order_counter = 1

    def add_to_cart(self, user_id, item_name, price, quantity=1):
        if user_id not in self.carts:
            self.carts[user_id] = []

        for item in self.carts[user_id]:
            if item['name'] == item_name:
                item['quantity'] += quantity
                break
        else:
            self.carts[user_id].append({
                'name': item_name,
                'price': price,
                'quantity': quantity
            })

    def remove_from_cart(self, user_id, item_name):
        if user_id in self.carts:
            self.carts[user_id] = [
                item for item in self.carts[user_id]
                if item['name'] != item_name
            ]

    def clear_cart(self, user_id):
        if user_id in self.carts:
            del self.carts[user_id]

    def get_cart_total(self, user_id):
        if user_id not in self.carts:
            return 0
        return sum(
            item['price'] * item['quantity']
            for item in self.carts[user_id]
        )

    def get_cart_count(self, user_id):
        if user_id not in self.carts:
            return 0
        return sum(item['quantity'] for item in self.carts[user_id])

    def create_order(self, user_id, order_type, name, phone, address=None):
        if user_id not in self.carts or not self.carts[user_id]:
            return None

        order = {
            'id': self.order_counter,
            'user_id': user_id,
            'items': self.carts[user_id].copy(),
            'total': self.get_cart_total(user_id),
            'type': order_type,
            'name': name,
            'phone': phone,
            'address': address if order_type == 'delivery' else None,
            'created_at': datetime.now().isoformat()
        }

        self.order_counter += 1
        self.clear_cart(user_id)
        return order


store = DataStore()


# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard(user_id=None):
    cart_count = store.get_cart_count(user_id) if user_id else 0
    return ReplyKeyboardMarkup([
        ["📋 Меню", f"🛒 Корзина ({cart_count})"],
        ["🚀 Оформить заказ", "📞 Контакты"],
        ["ℹ️ Помощь"]
    ], resize_keyboard=True)


def get_menu_keyboard():
    keyboard = [[cat] for cat in MENU.keys()]
    keyboard.append(["🛒 Корзина", "🔙 Назад"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_category_keyboard(category):
    keyboard = [
        [f"➕ {item['name']} - {item['price']}₽"]
        for item in MENU[category]["items"]
    ]
    keyboard.append(["🛒 Корзина", "🔙 Назад"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_cart_keyboard():
    return ReplyKeyboardMarkup([
        ["➖ Удалить"],
        ["🗑️ Очистить корзину", "🚀 Оформить"],
        ["📋 Меню", "🔙 Назад"]
    ], resize_keyboard=True)


def get_order_type_keyboard():
    return ReplyKeyboardMarkup([
        ["🚗 Доставка", "🏃 Самовывоз"],
        ["🔙 Отмена"]
    ], resize_keyboard=True)


# ==================== ПРОВЕРКА ВРЕМЕНИ ====================

async def check_order_time(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if not is_working_time():
        await update.message.reply_text(
            "⏰ **ВНИМАНИЕ!**\n\n"
            "Заказы принимаются только **до 21:30** по московскому времени.\n"
            "🍽 Завтра ждём вас снова!",
            parse_mode='Markdown'
        )
        return False
    return True


# ==================== ОСНОВНЫЕ ФУНКЦИИ ====================
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    delivery_info = """
🚗 **ИНФОРМАЦИЯ О ДОСТАВКЕ**

🏠 **ЖК Одинцово-1**
• Доставка: 100 ₽

🏘️ **Старый город**
• Доставка: 300 ₽

📍 **Самовывоз**
• Каштановая улица, 11
• Бесплатно

⏱️ **Время доставки:** 60 минут
💵 **Минимальный заказ:** 500 ₽
"""

    await update.message.reply_text(
        f"🍝 **Добро пожаловать в бистро '{BISTRO_NAME}'!**\n\n"
        f"Привет, {user.first_name}!\n"
        f"{delivery_info}\n"
        f"Используйте кнопки ниже для заказа ⬇️",
        reply_markup=get_main_keyboard(user.id),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def show_menu(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍽 **Выберите категорию:**",
        reply_markup=get_menu_keyboard(),
        parse_mode='Markdown'
    )


async def show_category(update: Update, _: ContextTypes.DEFAULT_TYPE):
    category = update.message.text
    if category not in MENU:
        return

    items = MENU[category]["items"]
    photos = MENU[category].get("photos", [])

    menu_text = f"**{category}:**\n\n"
    for item in items:
        menu_text += f"• *{item['name']}* - {item['price']}₽\n"
        if item['desc']:
            menu_text += f"  _{item['desc']}_\n\n"
        else:
            menu_text += "\n"

    try:
        if photos:
            await update.message.reply_photo(
                photo=photos[0],
                caption=menu_text,
                reply_markup=get_category_keyboard(category),
                parse_mode='Markdown'
            )

            if len(photos) > 1:
                for i, photo_url in enumerate(photos[1:], 2):
                    await update.message.reply_photo(
                        photo=photo_url,
                        caption=f"📸 Фото {i}/{len(photos)}"
                    )
        else:
            await update.message.reply_text(
                menu_text,
                reply_markup=get_category_keyboard(category),
                parse_mode='Markdown'
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке категории {category}: {e}")
        await update.message.reply_text(
            menu_text,
            reply_markup=get_category_keyboard(category),
            parse_mode='Markdown'
        )


async def add_to_cart(update: Update, _: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text.startswith("➕ "):
        try:
            parts = text[2:].split(" - ")
            item_name = parts[0].strip()
            price = int(parts[1].replace("₽", "").strip())

            store.add_to_cart(user_id, item_name, price)

            await update.message.reply_text(
                f"✅ *{item_name}* добавлен в корзину!",
                reply_markup=get_main_keyboard(user_id),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Ошибка добавления в корзину: {e}")


async def remove_from_cart_handler(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in store.carts or not store.carts[user_id]:
        await update.message.reply_text(
            "🛒 Корзина пуста!",
            reply_markup=get_main_keyboard(user_id)
        )
        return

    keyboard = [
        [f"➖ Удалить {item['name']}"]
        for item in store.carts[user_id]
    ]
    keyboard.append(["🔙 Назад"])

    await update.message.reply_text(
        "🗑️ **Выберите товар для удаления:**",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )

async def remove_item_from_cart(update: Update, _: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text.startswith("➖ Удалить "):
        item_name = text.replace("➖ Удалить ", "").strip()
        store.remove_from_cart(user_id, item_name)

        await update.message.reply_text(
            f"❌ *{item_name}* удален из корзины!",
            reply_markup=get_cart_keyboard(),
            parse_mode='Markdown'
        )

async def clear_cart_handler(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    store.clear_cart(user_id)

    await update.message.reply_text(
        "🗑️ **Корзина очищена!**",
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )

async def show_cart(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart_total = store.get_cart_total(user_id)

    if cart_total == 0:
        await update.message.reply_text(
            "🛒 **Ваша корзина пуста**\n\nВыберите товары из меню 📋",
            reply_markup=get_main_keyboard(user_id),
            parse_mode='Markdown'
        )
        return

    text = "🛒 **Ваша корзина:**\n\n"
    for item in store.carts.get(user_id, []):
        item_total = item['price'] * item['quantity']
        text += f"• *{item['name']}*\n"
        text += f"  {item['price']}₽ × {item['quantity']} = {item_total}₽\n\n"

    text += f"💰 **Итого: {cart_total}₽**\n\n"

    if cart_total < MIN_ORDER_SUM:
        text += f"⚠️ Минимальная сумма заказа: {MIN_ORDER_SUM}₽"

    await update.message.reply_text(
        text,
        reply_markup=get_cart_keyboard(),
        parse_mode='Markdown'
    )

async def start_order(update: Update, _: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cart_total = store.get_cart_total(user_id)

    if not await check_order_time(update, _):
        return ConversationHandler.END

    if cart_total == 0:
        await update.message.reply_text(
            "🛒 Корзина пуста!",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    if cart_total < MIN_ORDER_SUM:
        await update.message.reply_text(
            f"⚠️ Минимальная сумма заказа: {MIN_ORDER_SUM}₽",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🚀 **Оформление заказа**\n\nВыберите способ получения:",
        reply_markup=get_order_type_keyboard(),
        parse_mode='Markdown'
    )
    return CHOOSING_TYPE

async def choose_order_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🔙 Отмена":
        await update.message.reply_text(
            "❌ Заказ отменён",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    context.user_data['order_type'] = 'delivery' if text == "🚗 Доставка" else 'pickup'

    if context.user_data['order_type'] == 'delivery':
        delivery_keyboard = ReplyKeyboardMarkup([
            ["✅ Да, в ЖК Одинцово-1", "❌ Нет, в старом городе"],
            ["🔙 Отмена"]
        ], resize_keyboard=True)

        await update.message.reply_text(
            "🚗 **Доставка**\n\nВы находитесь в **ЖК Одинцово-1**?",
            reply_markup=delivery_keyboard,
            parse_mode='Markdown'
        )
        return ASK_DELIVERY_ZONE
    else:
        await update.message.reply_text(
            "📝 **Введите ваше имя:**",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        return TYPING_NAME


async def ask_delivery_zone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "🔙 Отмена":
        await update.message.reply_text(
            "❌ Заказ отменён",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    if text == "✅ Да, в ЖК Одинцово-1":
        context.user_data['delivery_zone'] = 'jk'
        delivery_price = 100
    else:
        context.user_data['delivery_zone'] = 'old'
        delivery_price = 300

    context.user_data['delivery_price'] = delivery_price

    await update.message.reply_text(
        f"🚗 Стоимость доставки: **{delivery_price}₽**\n\n"
        f"📝 **Введите ваше имя:**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    return TYPING_NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text

    await update.message.reply_text(
        "📱 **Введите ваш телефон:**",
        parse_mode='Markdown'
    )
    return TYPING_PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not any(c.isdigit() for c in phone):
        await update.message.reply_text(
            "❌ Некорректный номер\nВведите ещё раз:"
        )
        return TYPING_PHONE

    context.user_data['phone'] = phone

    if context.user_data['order_type'] == 'delivery':
        await update.message.reply_text(
            "📍 **Введите адрес доставки:**\nУлица, дом, квартира",
            parse_mode='Markdown'
        )
        return TYPING_ADDRESS
    else:
        return await confirm_order(update, context)


async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['address'] = update.message.text
    return await confirm_order(update, context)


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = context.user_data

    cart_total = store.get_cart_total(user_id)
    delivery_price = user_data.get('delivery_price', 0)
    total_with_delivery = cart_total + delivery_price

    order_text = f"✅ **Подтвердите заказ:**\n\n"
    order_text += f"**Способ:** {'🚗 Доставка' if user_data['order_type'] == 'delivery' else '🏃 Самовывоз'}\n"

    if user_data['order_type'] == 'delivery':
        zone = user_data.get('delivery_zone')
        if zone == 'jk':
            order_text += f"**Зона:** ЖК Одинцово-1 (доставка 100₽)\n"
        else:
            order_text += f"**Зона:** Старый город (доставка 300₽)\n"
        order_text += f"**Адрес:** {user_data.get('address', 'Не указан')}\n"
    else:
        order_text += f"**Адрес самовывоза:** {BISTRO_ADDRESS}\n"

    order_text += f"**Имя:** {user_data['name']}\n"
    order_text += f"**Телефон:** {user_data['phone']}\n\n"

    order_text += "**Состав заказа:**\n"
    for item in store.carts.get(user_id, []):
        order_text += f"• {item['name']} × {item['quantity']}\n"

    order_text += f"\n💰 **Сумма заказа: {cart_total}₽**\n"

    if delivery_price > 0:
        order_text += f"🚗 **Доставка: +{delivery_price}₽**\n"

    order_text += f"💵 **ИТОГО: {total_with_delivery}₽**\n\n"

    if user_data['order_type'] == 'delivery':
        order_text += f"⏱️ **Время доставки:** ~{DELIVERY_TIME} мин\n\n"

    order_text += "Всё верно?"

    keyboard = [["✅ Да, всё верно", "❌ Нет, изменить"]]

    await update.message.reply_text(
        order_text,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode='Markdown'
    )
    return CONFIRMING_ORDER


async def complete_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_data = context.user_data

    if update.message.text == "❌ Нет, изменить":
        await update.message.reply_text(
            "Начнём заново...",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    order = store.create_order(
        user_id=user_id,
        order_type=user_data['order_type'],
        name=user_data['name'],
        phone=user_data['phone'],
        address=user_data.get('address')
    )

    if not order:
        await update.message.reply_text(
            "❌ Ошибка создания заказа",
            reply_markup=get_main_keyboard(user_id)
        )
        return ConversationHandler.END

    order['delivery_zone'] = user_data.get('delivery_zone')
    order['delivery_price'] = user_data.get('delivery_price', 0)
    order['total_with_delivery'] = order['total'] + order['delivery_price']

    await send_order_notification(order)

    delivery_text = ""
    if order['type'] == 'delivery':
        if order['delivery_zone'] == 'jk':
            delivery_text = "🚗 Доставка в ЖК Одинцово-1: +100₽"
        else:
            delivery_text = "🚗 Доставка в старый город: +300₽"

    await update.message.reply_text(
        f"🎉 **Заказ #{order['id']} принят!**\n\n"
        f"Спасибо, {user_data['name']}!\n\n"
        f"{'🚗 Заказ будет доставлен' if order['type'] == 'delivery' else '🏃 Заберите заказ по адресу:'}\n"
        f"{'⏱️ Время: ~60 мин' if order['type'] == 'delivery' else BISTRO_ADDRESS}\n\n"
        f"💰 Сумма заказа: {order['total']}₽\n"
        f"{delivery_text}\n"
        f"💵 **ИТОГО: {order['total_with_delivery']}₽**\n\n"
        f"📱 Наш телефон: {BISTRO_PHONE}\n\n"
        f"Ожидайте звонка для подтверждения!",
        reply_markup=get_main_keyboard(user_id),
        parse_mode='Markdown'
    )

    context.user_data.clear()
    return ConversationHandler.END


async def send_order_notification(order):
    delivery_text = ""
    if order['type'] == 'delivery':
        if order.get('delivery_zone') == 'jk':
            delivery_text = "🏠 ЖК Одинцово-1 (доставка 100₽)"
        else:
            delivery_text = "🏘️ Старый город (доставка 300₽)"

    admin_message = f"""
🚨 **НОВЫЙ ЗАКАЗ #{order['id']}**

👤 **Клиент:** {order['name']}
📱 **Телефон:** {order['phone']}
{'📍 **Адрес доставки:**' if order['type'] == 'delivery' else '🏃 **Самовывоз:**'}
{order['address'] if order['type'] == 'delivery' else BISTRO_ADDRESS}

{'🚗 **Зона доставки:** ' + delivery_text if order['type'] == 'delivery' else ''}

📦 **Состав заказа:**
"""

    for item in order['items']:
        admin_message += f"• {item['name']} × {item['quantity']} = {item['price'] * item['quantity']}₽\n"

    admin_message += f"\n💰 **Сумма заказа: {order['total']}₽**"

    if order.get('delivery_price'):
        admin_message += f"\n🚗 **Доставка: +{order['delivery_price']}₽**"
        admin_message += f"\n💵 **ИТОГО: {order['total'] + order['delivery_price']}₽**"
    else:
        admin_message += f"\n💵 **ИТОГО: {order['total']}₽**"

    admin_message += f"\n🕐 **Время заказа:** {datetime.now().strftime('%H:%M %d.%m.%Y')}"

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    for admin_id in ADMIN_IDS:
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📋 Меню":
        await show_menu(update, context)

    elif text == "🛒 Корзина" or text.startswith("🛒 Корзина ("):
        await show_cart(update, context)

    elif text == "📞 Контакты":
        time_status = "🟢 ОТКРЫТО" if is_working_time() else "🔴 ЗАКРЫТО"
        await update.message.reply_text(
            f"**{BISTRO_NAME}**\n\n"
            f"📍 {BISTRO_ADDRESS}\n"
            f"📱 {BISTRO_PHONE}\n"
            f"🕐 08:00 - 21:30\n"
            f"{time_status}",
            parse_mode='Markdown'
        )

    elif text == "ℹ️ Помощь":
        await update.message.reply_text(
            "ℹ️ **Помощь**\n\n"
            "1. '📋 Меню' - посмотреть блюда\n"
            "2. '➕' - добавить в корзину\n"
            "3. '🛒 Корзина' - проверить заказ\n"
            "4. '🚀 Оформить' - завершить заказ",
            parse_mode='Markdown'
        )

    elif text in MENU:
        await show_category(update, context)

    elif text == "🔙 Назад":
        await update.message.reply_text(
            "Главное меню",
            reply_markup=get_main_keyboard(user_id)
        )

    elif text.startswith("➕ "):
        await add_to_cart(update, context)

    elif text == "🚀 Оформить заказ":
        return await start_order(update, context)

    elif text == "➖ Удалить":
        await remove_from_cart_handler(update, context)

    elif text.startswith("➖ Удалить "):
        await remove_item_from_cart(update, context)

    elif text == "🗑️ Очистить корзину":
        await clear_cart_handler(update, context)

    else:
        await update.message.reply_text(
            "Используйте кнопки ⬇️",
            reply_markup=get_main_keyboard(user_id)
        )

    return None


# ==================== ЗАПУСК БОТА ====================
def main():
    print("=" * 50)
    print(f"🍝 БОТ '{BISTRO_NAME}' ЗАПУСКАЕТСЯ...")
    print(f"👑 Админы: {ADMIN_IDS}")
    print("=" * 50)

    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .concurrent_updates(50) \
        .build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(🚀 Оформить заказ)$"), start_order),
            CommandHandler("order", start_order)
        ],
        states={
            CHOOSING_TYPE: [
                MessageHandler(
                    filters.Regex("^(🚗 Доставка|🏃 Самовывоз|🔙 Отмена)$"),
                    choose_order_type
                )
            ],
            ASK_DELIVERY_ZONE: [
                MessageHandler(
                    filters.Regex("^(✅ Да, в ЖК Одинцово-1|❌ Нет, в старом городе|🔙 Отмена)$"),
                    ask_delivery_zone
                )
            ],
            TYPING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
            ],
            TYPING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)
            ],
            TYPING_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)
            ],
            CONFIRMING_ORDER: [
                MessageHandler(
                    filters.Regex("^(✅ Да, всё верно|❌ Нет, изменить)$"),
                    complete_order
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", start),
            MessageHandler(filters.Regex("^🔙"), start)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_menu))
    app.add_handler(CommandHandler("cart", show_cart))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот готов к работе!")
    app.run_polling()


if __name__ == "__main__":
    main()
