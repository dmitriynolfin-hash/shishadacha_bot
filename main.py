

import datetime
import time
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from config import TOKEN, ADMIN_CHAT_ID
from google_sheet import save_order

# Константы
STRENGTH_OPTIONS = ["Лёгкий", "Средний"]
FLAVORS = ["Вишня", "Лимон-лайм", "Виноград со специями", "Специи", "Мастика", "Апельсин", "Кока-кола",
           "Ежевика-черника", "Сливочный пирог", "Мандарин", "Фундук, шоколад, мята", "Грейпфрут", "Ягодный сорбет",
           "Энергетик", "Черника", "Малина", "Космополитан", "Манго", "Личи", "Виноград", "Двойное яблоко", "Арбуз",
           "Персик", "Мятная жвачка", "Зеленое яблоко с мятяной", "Виноградная крем-сода", "Смородина"]
MIXES = {
    "mix1": "Микс 1 - вишня (90%) + индийские специи (10%)",
    "mix2": "Микс 2 - апельсин (40%) + кока-кола (60%)",
    "mix3": "Микс 3 - ежевика (60%) + сливочный пирог (40%)",
    "mix4": "Микс 4 - арбуз (80%) + мятная жвачка (20%)",
    "mix5": "Микс 5 - лимон-лайм (70%) + апельсин (30%)",
    "mix6": "Микс 6 - черника (50%) + малина (50%)",
    "mix7": "Микс 7 - энергетик (50%) + персик (40%) + мастика (10%)"
}
TOWERS = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]

# Товары (только кальяны)
products = [
    {"id": 1, "name": "Кальян", "price": 4000, "category": "Кальяны", "strength": "Лёгкий"},
    {"id": 2, "name": "Кальян", "price": 4500, "category": "Кальяны", "strength": "Средний"},
]

# Глобальные переменные
user_carts = {}
delivery_data = {}  # Хранит данные доставки: tower, apartment, delivery_time, phone
pending_orders = {}  # Хранит заказы, ожидающие подтверждения: {order_id: {user_id, chat_id, message_id, timestamp}}

# Словарь для сопоставления крепости с ID продукта
STRENGTH_PRODUCT_IDS = {
    'light': 1,
    'medium': 2
}


async def show_flavors_menu(update, context, query):
    """Показывает меню выбора вкусов/миксов"""
    # Получаем текущий выбор
    selected_flavors = context.user_data.get('selected_flavors', [])

    # Формируем сообщение
    message = "🍓 Выберите вкусы табака (можно несколько):\n\n"

    if selected_flavors:
        message += f"✅ Выбрано: {', '.join(selected_flavors)}\n\n"

    message += "Или выберите готовый микс:"

    # Создаем клавиатуру
    keyboard = []

    # Кнопки вкусов (в 2 колонки)
    row = []
    for i, flavor in enumerate(FLAVORS):
        # Проверяем, выбран ли уже этот вкус
        is_selected = flavor in selected_flavors
        btn_text = f"✅ {flavor}" if is_selected else flavor

        row.append(InlineKeyboardButton(btn_text, callback_data=f'flavor_{flavor}'))

        # Каждые 2 вкуса начинаем новую строку
        if (i + 1) % 2 == 0:
            keyboard.append(row)
            row = []

    # Добавляем последнюю строку, если она не пустая
    if row:
        keyboard.append(row)

    # Кнопки готовых миксов
    for mix_id, mix_name in MIXES.items():
        keyboard.append([InlineKeyboardButton(mix_name, callback_data=f'mix_{mix_id}')])

    # Кнопка подтверждения выбора
    if selected_flavors:
        keyboard.append([InlineKeyboardButton("✅ Завершить выбор вкусов", callback_data='flavors_done')])

    # Кнопка возврата
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_strength')])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_delivery_menu(update, context, query):
    """Показывает меню выбора башни и телефона с галочками для заполненных полей"""
    user_id = query.from_user.id

    # Проверяем, есть ли уже данные о доставке
    has_delivery_data = all([
        delivery_data.get(user_id, {}).get('tower'),
        delivery_data.get(user_id, {}).get('apartment'),
        delivery_data.get(user_id, {}).get('delivery_time'),
        delivery_data.get(user_id, {}).get('phone')
    ])

    message = "🏢 Для оформления заказа заполните данные доставки:\n\n"

    # Отображаем текущие данные с галочками
    delivery_info = delivery_data.get(user_id, {})
    if delivery_info.get('tower'):
        message += f"✅ Башня: {delivery_info['tower']}\n"
    else:
        message += f"❌ Башня: не выбрана\n"

    if delivery_info.get('apartment'):
        message += f"✅ Квартира: {delivery_info['apartment']}\n"
    else:
        message += f"❌ Квартира: не указана\n"

    if delivery_info.get('delivery_time'):
        message += f"✅ Время доставки: {delivery_info['delivery_time']}\n"
    else:
        message += f"❌ Время доставки: не указано\n"

    if delivery_info.get('phone'):
        message += f"✅ Телефон: {delivery_info['phone']}\n"
    else:
        message += f"❌ Телефон: не указан\n"

    message += "\nВыберите действие:"

    keyboard = []
    # Кнопки башен
    for tower in TOWERS:
        keyboard.append([InlineKeyboardButton(tower, callback_data=f'tower_{tower}')])

    # Кнопки для ввода данных с галочками
    apartment_icon = "✅ 🏠" if delivery_info.get('apartment') else "🏠"
    time_icon = "✅ ⏰" if delivery_info.get('delivery_time') else "⏰"
    phone_icon = "✅ 📱" if delivery_info.get('phone') else "📱"

    keyboard.append([
        InlineKeyboardButton(f"{apartment_icon} Ввести номер квартиры", callback_data='input_apartment'),
        InlineKeyboardButton(f"{time_icon} Ввести время доставки", callback_data='input_time')
    ])

    keyboard.append([
        InlineKeyboardButton(f"{phone_icon} Ввести номер телефона", callback_data='input_phone')
    ])

    # Кнопка подтверждения
    if has_delivery_data:
        keyboard.append([InlineKeyboardButton("✅ Перейти к оформлению", callback_data='proceed_to_checkout')])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_cart')])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str = "Выберите действие:"):
    """Показывает главное меню с инлайн-кнопками"""
    keyboard = [
        [InlineKeyboardButton("💨 Сделать заказ кальяна", callback_data='hookah_order')],
        [InlineKeyboardButton("🛒 Корзина", callback_data='cart')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Для новых пользователей отправляем новое сообщение
    if update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    # Для существующих диалогов редактируем предыдущее сообщение
    elif update.callback_query:
        query = update.callback_query
        await query.edit_message_text(message, reply_markup=reply_markup)


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовый ввод (квартира, время доставки, телефон)"""
    user_id = update.message.from_user.id
    text = update.message.text
    state = context.user_data.get('delivery_state')

    # Обработка команды /start
    if text.lower() in ["/start", "старт"]:
        await start(update, context)
        return

    # Обработка данных доставки
    if state == 'waiting_apartment':
        # Сохраняем квартиру
        if user_id not in delivery_data:
            delivery_data[user_id] = {}
        delivery_data[user_id]['apartment'] = text

        # Сбрасываем состояние
        context.user_data.pop('delivery_state', None)

        await update.message.reply_text(
            f"✅ Номер квартиры сохранен: {text}\n"
            "Продолжайте заполнять данные доставки:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏢 Вернуться к доставке", callback_data='back_to_delivery')]])
        )

    elif state == 'waiting_time':
        # Сохраняем время
        if user_id not in delivery_data:
            delivery_data[user_id] = {}
        delivery_data[user_id]['delivery_time'] = text

        # Сбрасываем состояние
        context.user_data.pop('delivery_state', None)

        await update.message.reply_text(
            f"✅ Время доставки сохранено: {text}\n"
            "Продолжайте заполнять данные доставки:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏢 Вернуться к доставке", callback_data='back_to_delivery')]])
        )

    elif state == 'waiting_phone':
        # Сохраняем телефон
        if user_id not in delivery_data:
            delivery_data[user_id] = {}
        delivery_data[user_id]['phone'] = text

        # Сбрасываем состояние
        context.user_data.pop('delivery_state', None)

        await update.message.reply_text(
            f"✅ Номер телефона сохранен: {text}\n"
            "Продолжайте заполнять данные доставки:",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏢 Вернуться к доставке", callback_data='back_to_delivery')]])
        )
    else:
        # Если текст не относится к доставке, показываем главное меню
        await show_main_menu(update, context, "Пожалуйста, используйте кнопки меню:")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    user_id = update.message.from_user.id

    # Сбрасываем состояние пользователя
    context.user_data.clear()
    if user_id in user_carts:
        del user_carts[user_id]
    if user_id in delivery_data:
        del delivery_data[user_id]

    # Отправляем приветственное сообщение с главным меню
    await show_main_menu(
        update,
        context,
        "🔥 Добро пожаловать в форму заказа кальяна в ЖК Prime Park!\n"
        "Используйте кнопки меню для управления заказом."
    )


async def prefill_delivery_data(user_id, last_order_data):
    """Заполняет данные доставки из последнего заказа"""
    if user_id not in delivery_data:
        delivery_data[user_id] = {}

    # Заполняем только если поля пустые
    if not delivery_data[user_id].get('tower') and last_order_data.get('tower'):
        delivery_data[user_id]['tower'] = last_order_data['tower']
    if not delivery_data[user_id].get('apartment') and last_order_data.get('apartment'):
        delivery_data[user_id]['apartment'] = last_order_data['apartment']
    if not delivery_data[user_id].get('phone') and last_order_data.get('phone'):
        delivery_data[user_id]['phone'] = last_order_data['phone']
    if not delivery_data[user_id].get('delivery_time') and last_order_data.get('delivery_time'):
        delivery_data[user_id]['delivery_time'] = last_order_data['delivery_time']


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Всегда подтверждаем callback
    data = query.data
    user_id = query.from_user.id

    # Обработка подтверждения заказа администратором
    if data.startswith('confirm_'):
        order_id = data.split('_')[1]
        await handle_order_confirmation(update, context, 'confirm', order_id)
        return

    # Обработка отмены заказа администратором
    if data.startswith('cancel_'):
        order_id = data.split('_')[1]
        await handle_order_confirmation(update, context, 'cancel', order_id)
        return

    # Обработка кнопки "Сделать заказ кальяна"
    if data == 'hookah_order':
        # Проверяем, есть ли данные последнего заказа
        last_order = context.user_data.get('last_order')

        # Если есть данные последнего заказа, предзаполняем доставку
        if last_order:
            await prefill_delivery_data(user_id, last_order)

        # Находим продукты для крепостей
        light_product = next((p for p in products if p['id'] == STRENGTH_PRODUCT_IDS['light']), None)
        medium_product = next((p for p in products if p['id'] == STRENGTH_PRODUCT_IDS['medium']), None)

        if not light_product or not medium_product:
            await query.answer("❌ Кальяны временно недоступны")
            return

        # Формируем сообщение с ценами
        keyboard = [
            [InlineKeyboardButton(f"Лёгкий ({light_product['price']} руб.)", callback_data='strength_light')],
            [InlineKeyboardButton(f"Средний ({medium_product['price']} руб.)", callback_data='strength_medium')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
        ]

        await query.edit_message_text(
            "🌀 Выберите крепость кальяна:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    # Обработка выбора крепости
    elif data.startswith('strength_'):
        strength = data.split('_')[1]
        product_id = STRENGTH_PRODUCT_IDS[strength]

        # Получаем продукт по ID
        product = next((p for p in products if p['id'] == product_id), None)
        if not product:
            await query.answer("❌ Товар не найден")
            return

        # Сохраняем крепость и продукт
        context.user_data['hookah_strength'] = strength
        context.user_data['selected_hookah'] = product_id

        # Сбрасываем выбранные вкусы
        context.user_data['selected_flavors'] = []

        # Переходим к выбору вкусов/миксов
        await show_flavors_menu(update, context, query)

    # Обработка выбора вкуса
    elif data.startswith('flavor_'):
        flavor = data.split('_')[1]
        selected_flavors = context.user_data.get('selected_flavors', [])

        # Добавляем или удаляем вкус
        if flavor in selected_flavors:
            selected_flavors.remove(flavor)
        else:
            selected_flavors.append(flavor)

        context.user_data['selected_flavors'] = selected_flavors

        # Обновляем меню
        await show_flavors_menu(update, context, query)

    # Обработка выбора микса
    elif data.startswith('mix_'):
        mix_id = data.split('_')[1]
        mix_name = MIXES.get(mix_id)

        if not mix_name:
            await query.answer("❌ Микс не найден")
            return

        product_id = context.user_data.get('selected_hookah')
        strength = context.user_data.get('hookah_strength')

        if not product_id or not strength:
            await query.answer("❌ Ошибка выбора. Начните заново.")
            return

        product = next((p for p in products if p['id'] == product_id), None)
        if not product:
            await query.answer("❌ Товар не найден")
            return

        # Формируем комментарий
        strength_text = {
            'light': 'лёгкий',
            'medium': 'средний'
        }.get(strength, strength)

        comment = f"{strength_text}, {mix_name}"

        # Добавляем в корзину
        if user_id not in user_carts:
            user_carts[user_id] = []

        # Ищем такой же кальян с таким же комментарием
        item_exists = False
        for item in user_carts[user_id]:
            if item['id'] == product_id and item.get('comment') == comment:
                item['quantity'] += 1
                item_exists = True
                break

        if not item_exists:
            user_carts[user_id].append({
                "id": product_id,
                "name": product['name'],
                "price": product['price'],
                "quantity": 1,
                "comment": comment
            })

        await query.answer(f"✅ {mix_name} добавлен в корзину!")

        # Очищаем состояние
        context.user_data.pop('selected_hookah', None)
        context.user_data.pop('hookah_strength', None)
        context.user_data.pop('selected_flavors', None)

        # Создаем клавиатуру с двумя кнопками
        keyboard = [
            [
                InlineKeyboardButton("➕ Добавить еще 1 кальян", callback_data='hookah_order'),
                InlineKeyboardButton("🛒 Перейти в корзину", callback_data='cart')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Редактируем сообщение
        await query.edit_message_text(
            "🍇 Микс добавлен в корзину!",
            reply_markup=reply_markup
        )

    # Завершение выбора вкусов
    elif data == 'flavors_done':
        selected_flavors = context.user_data.get('selected_flavors', [])

        if not selected_flavors:
            await query.answer("❌ Выберите хотя бы один вкус!")
            return

        product_id = context.user_data.get('selected_hookah')
        strength = context.user_data.get('hookah_strength')

        if not product_id or not strength:
            await query.answer("❌ Ошибка заказа. Начните заново.")
            return

        product = next((p for p in products if p['id'] == product_id), None)
        if not product:
            await query.answer("❌ Товар не найден")
            return

        # Формируем комментарий
        strength_text = {
            'light': 'лёгкий',
            'medium': 'средний'
        }.get(strength, strength)

        comment = f"{strength_text}, Вкусы: {', '.join(selected_flavors)}"

        # Добавляем в корзину
        if user_id not in user_carts:
            user_carts[user_id] = []

        # Ищем такой же кальян с таким же комментарием
        item_exists = False
        for item in user_carts[user_id]:
            if item['id'] == product_id and item.get('comment') == comment:
                item['quantity'] += 1
                item_exists = True
                break

        if not item_exists:
            user_carts[user_id].append({
                "id": product_id,
                "name": product['name'],
                "price": product['price'],
                "quantity": 1,
                "comment": comment
            })

        await query.answer(f"✅ {product['name']} добавлен в корзину!")

        # Очищаем состояние
        context.user_data.pop('selected_hookah', None)
        context.user_data.pop('hookah_strength', None)
        context.user_data.pop('selected_flavors', None)

        # Создаем клавиатуру с двумя кнопками
        keyboard = [
            [
                InlineKeyboardButton("➕ Добавить еще 1 кальян", callback_data='hookah_order'),
                InlineKeyboardButton("🛒 Перейти в корзину", callback_data='cart')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Редактируем сообщение
        await query.edit_message_text(
            "🍇 Кальян добавлен в корзину!",
            reply_markup=reply_markup
        )

    # Возврат к выбору крепости
    elif data == 'back_to_strength':
        # Возвращаемся к выбору крепости
        # Находим продукты для крепостей
        light_product = next((p for p in products if p['id'] == STRENGTH_PRODUCT_IDS['light']), None)
        medium_product = next((p for p in products if p['id'] == STRENGTH_PRODUCT_IDS['medium']), None)

        if not light_product or not medium_product:
            await query.answer("❌ Кальяны временно недоступны")
            return

        keyboard = [
            [InlineKeyboardButton(f"Лёгкий ({light_product['price']} руб.)", callback_data='strength_light')],
            [InlineKeyboardButton(f"Средний ({medium_product['price']} руб.)", callback_data='strength_medium')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
        ]

        await query.edit_message_text(
            "🌀 Выберите крепость кальяна:",
            reply_markup=InlineKeyboardMarkup(keyboard))

    # Просмотр корзины
    elif data == 'cart':
        if user_id not in user_carts or not user_carts[user_id]:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
            await query.edit_message_text(
                "🛒 Ваша корзина пуста",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        total = 0
        message = "🛒 Ваша корзина:\n\n"
        for item in user_carts[user_id]:
            # Добавляем комментарий, если он есть
            comment = f" ({item['comment']})" if 'comment' in item and item['comment'] else ''
            message += f"• {item['name']}{comment} - {item['quantity']} шт. x {item['price']}₽\n"
            total += item['price'] * item['quantity']
        message += f"\n💸 Итого: {total}₽"

        keyboard = [
            [InlineKeyboardButton("💳 Оформить заказ", callback_data='checkout')],
            [InlineKeyboardButton("🗑️ Очистить корзину", callback_data='clear_cart')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
        ]

        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

    # Оформление заказа (переход к заполнению данных доставки)
    elif data == 'checkout':
        if user_id not in user_carts or not user_carts[user_id]:
            await query.answer("❌ Корзина пуста!")
            return

        # Переходим к заполнению данных доставки
        await show_delivery_menu(update, context, query)

    # Возврат в корзину из меню доставки
    elif data == 'back_to_cart':
        if user_id not in user_carts or not user_carts[user_id]:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
            await query.edit_message_text(
                "🛒 Ваша корзина пуста",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return

        total = 0
        message = "🛒 Ваша корзина:\n\n"
        for item in user_carts[user_id]:
            comment = f" ({item.get('comment', '')})" if item.get('comment') else ''
            message += f"• {item['name']}{comment} - {item['quantity']} шт. x {item['price']}₽\n"
            total += item['price'] * item['quantity']
        message += f"\n💸 Итого: {total}₽"

        keyboard = [
            [InlineKeyboardButton("💳 Оформить заказ", callback_data='checkout')],
            [InlineKeyboardButton("🗑️ Очистить корзину", callback_data='clear_cart')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
        ]

        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

    # Возврат в меню доставки
    elif data == 'back_to_delivery':
        await show_delivery_menu(update, context, query)

    # Выбор башни
    elif data.startswith('tower_'):
        tower = data.split('_')[1]
        if user_id not in delivery_data:
            delivery_data[user_id] = {}
        delivery_data[user_id]['tower'] = tower
        await query.answer(f"✅ Башня {tower} выбрана")
        await show_delivery_menu(update, context, query)

    # Запрос на ввод квартиры
    elif data == 'input_apartment':
        context.user_data['delivery_state'] = 'waiting_apartment'
        await query.edit_message_text(
            "🏠 Введите номер квартиры (например: 302Г):\n"
            "Укажите номер этажа и букву корпуса, если необходимо",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_delivery')]])
        )

    # Запрос на ввод времени доставки
    elif data == 'input_time':
        context.user_data['delivery_state'] = 'waiting_time'
        await query.edit_message_text(
            "⏰ Введите дату и время доставки (например: 01.01 15:00):\n"
            "Укажите дату и время в формате ДД.ММ ЧЧ:ММ",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_delivery')]])
        )

    # Запрос на ввод телефона
    elif data == 'input_phone':
        context.user_data['delivery_state'] = 'waiting_phone'
        await query.edit_message_text(
            "📱 Введите ваш номер телефона для связи:\n"
            "Пример: +7 (999) 123-45-67 или 89991234567",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_delivery')]])
        )

    # Переход к оформлению заказа
    elif data == 'proceed_to_checkout':
        # Проверка заполненности всех полей доставки
        if user_id not in delivery_data:
            await query.answer("❌ Заполните все данные доставки!")
            return

        delivery_info = delivery_data[user_id]
        required_fields = ['tower', 'apartment', 'delivery_time', 'phone']
        if not all(delivery_info.get(field) for field in required_fields):
            await query.answer("❌ Заполните все данные доставки!")
            return

        # Формируем данные заказа
        total = sum(item['price'] * item['quantity'] for item in user_carts[user_id])
        order_data = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),  # Дата оформления
            "delivery_date_time": delivery_info['delivery_time'],  # Дата и время доставки
            "username": query.from_user.full_name,  # Имя клиента
            "phone": delivery_info['phone'],  # Телефон
            "tower": delivery_info['tower'],  # Башня
            "apartment": delivery_info['apartment'],  # Квартира
            "cart": user_carts[user_id],  # Корзина с товарами
            "total": total,  # Итоговая сумма
            "user_id": user_id,  # ID пользователя
            "username_tg": query.from_user.username or ""  # Telegram username
        }

        # Генерируем уникальный ID заказа
        order_id = str(uuid.uuid4())

        # Сохраняем заказ в Google Таблицу
        try:
            save_order(order_data)
        except Exception as e:
            print(f"Ошибка сохранения заказа: {e}")
            await context.bot.send_message(
                ADMIN_CHAT_ID,
                f"⚠️ ОШИБКА СОХРАНЕНИЯ ЗАКАЗА!\n"
                f"От: @{query.from_user.username}\n"
                f"Ошибка: {str(e)[:200]}"
            )

        # Отправляем уведомление администратору
        admin_message = (
            f"🆕 НОВЫЙ ЗАКАЗ! ID: {order_id}\n"
            f"От: {order_data['username']} (@{order_data['username_tg']})\n"
            f"Телефон: {order_data['phone']}\n"
            f"Башня: {order_data['tower']}, Квартира: {order_data['apartment']}\n"
            f"Время доставки: {order_data['delivery_date_time']}\n\n"
            f"Состав заказа:\n"
        )

        for item in order_data['cart']:
            comment = f" ({item['comment']})" if 'comment' in item and item['comment'] else ''
            admin_message += f"• {item['name']}{comment} - {item['quantity']} шт. x {item['price']}₽\n"

        admin_message += f"\n💸 Итого: {order_data['total']}₽"

        # Кнопки подтверждения/отмены для администратора
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f'confirm_{order_id}'),
                InlineKeyboardButton("❌ Отменить", callback_data=f'cancel_{order_id}')
            ]
        ]

        # Отправляем сообщение администратору
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Сохраняем информацию для отслеживания подтверждения
        pending_orders[order_id] = {
            'user_id': user_id,
            'chat_id': query.message.chat_id,
            'message_id': query.message.message_id,
            'timestamp': time.time(),
            'order_data': order_data
        }

        # Проверяем наличие job_queue
        if context.application.job_queue is not None:
            # Запускаем таймер на 30 минут для автоматической отмены (900 секунд)
            context.application.job_queue.run_once(
                auto_cancel_order,
                900,
                data=order_id,
                name=f'cancel_{order_id}'
            )
        else:
            print("⚠️ JobQueue не инициализирован! Заказ не будет автоматически отменен")
            await context.bot.send_message(
                ADMIN_CHAT_ID,
                f"⚠️ JobQueue не инициализирован! Заказ {order_id} не будет автоматически отменен"
            )

        # Сохраняем данные заказа для повторного использования
        context.user_data['last_order'] = {
            'tower': delivery_info['tower'],
            'apartment': delivery_info['apartment'],
            'phone': delivery_info['phone'],
            'delivery_time': delivery_info['delivery_time']
        }

        # Очистка корзины
        if user_id in user_carts:
            user_carts[user_id] = []

        # Формируем детали заказа для клиента (указываем, что ожидается подтверждение)
        order_details = "⏳ Ваш заказ оформлен и ожидает подтверждения маэстро (обычно это происходит в течение 15 минут) !\n\n"
        order_details += "📋 Детали заказа:\n"
        for item in order_data['cart']:
            comment = f" ({item.get('comment', '')})" if item.get('comment') else ''
            order_details += f"• {item['name']}{comment} - {item['quantity']} шт. x {item['price']}₽\n"
        order_details += f"\n💸 Итого: {total}₽\n\n"
        order_details += f"🏢 Башня: {order_data['tower']}\n"
        order_details += f"🏠 Квартира: {order_data['apartment']}\n"
        order_details += f"⏰ Время доставки: {order_data['delivery_date_time']}\n"
        order_details += f"📱 Телефон: {order_data['phone']}\n\n"
        order_details += "Как только маэстро подтвердит заказ, мы сообщим вам!"

        # Обновляем сообщение у клиента - добавляем кнопку "Заказать еще"
        await query.edit_message_text(
            order_details,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Заказать кальян(ы) еще раз", callback_data='hookah_order'),
                    InlineKeyboardButton("✍️ Связаться с маэстро", callback_data='contact_hookah_master')
                ]
            ])
        )

    # Обработка кнопки "Связаться с кальянщиком"
    elif data == 'contact_hookah_master':
        user_name = query.from_user.full_name
        username = f"@{query.from_user.username}" if query.from_user.username else "без username"

        # Сообщение админу
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"👤 Клиент хочет уточнить детали заказа!\n"
            f"Имя: {user_name}\n"
            f"Username: {username}\n"
            f"ID: {user_id}\n\n"
            f"Пожалуйста, свяжитесь с клиентом для уточнения деталей."
        )

        await query.answer("✅ Запрос отправлен! Маэстро свяжется с вами в ближайшее время.")

        # Создаем кнопку для нового заказа
        order_button = InlineKeyboardButton(
            "💨 Заказать еще один кальян",
            callback_data='hookah_order'
        )

        await query.edit_message_text(
            "✅ Запрос на связь отправлен маэстро!\n"
            "Он свяжется с вами в ближайшее время для уточнения деталей заказа.\n\n"
            "Спасибо за ваш заказ! ❤️",
            reply_markup=InlineKeyboardMarkup([[order_button]])
        )

    # Очистка корзины
    elif data == 'clear_cart':
        if user_id in user_carts:
            user_carts[user_id] = []
        await show_main_menu(update, context, "🗑️ Корзина очищена! Выберите действие:")

    # Возврат в главное меню
    elif data == 'back_to_main':
        await show_main_menu(update, context)

    # Обработка кнопки "Помощь"
    elif data == 'help':
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        await query.edit_message_text(
            "❓ Помощь:\n\n"
            "1. Нажмите '💨 Сделать заказ кальяна' для начала заказа\n"
            "2. Выберите крепость и вкусы\n"
            "3. Перейдите в корзину для оформления\n"
            "4. Заполните данные доставки\n\n"
            "При возникновении вопросов свяжитесь с маэстро на экране оформления заказа.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# Функция автоматической отмены заказа
async def auto_cancel_order(context: ContextTypes.DEFAULT_TYPE):
    order_id = context.job.data
    order_info = pending_orders.get(order_id)

    if not order_info:
        return  # Заказ уже обработан

    # Удаляем из ожидающих
    del pending_orders[order_id]

    # Отправляем сообщение клиенту
    await context.bot.send_message(
        chat_id=order_info['chat_id'],
        text="⏱ К сожалению, на выбранное вами время у маэстро закончились свободные кальяны, попробуйте выбрать другое время"
    )

    # Уведомляем администратора
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"⚠️ ЗАКАЗ АВТОМАТИЧЕСКИ ОТМЕНЁН ПО ТАЙМАУТУ\nID: {order_id}"
    )


# Обработка подтверждения/отмены заказа
async def handle_order_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, order_id: str):
    query = update.callback_query
    await query.answer()

    order_info = pending_orders.get(order_id)
    if not order_info:
        await query.edit_message_text("⚠️ Этот заказ уже обработан или срок подтверждения истёк")
        return

    # Удаляем из ожидающих
    del pending_orders[order_id]

    # Отменяем запланированную автоматическую отмену
    if context.application.job_queue is not None:
        current_jobs = context.application.job_queue.get_jobs_by_name(f'cancel_{order_id}')
        for job in current_jobs:
            job.schedule_removal()

    # Определяем сообщение для клиента
    if action == 'confirm':
        client_message = "✅ Заказ подтвержден и будет доставлен в указанное время!"
        admin_status = "ПОДТВЕРЖДЁН"
    else:
        client_message = "⏱ К сожалению, на выбранное вами время у маэстро закончились свободные кальяны, попробуйте выбрать другое время"
        admin_status = "ОТМЕНЁН"

    # Отправляем статус клиенту
    await context.bot.send_message(
        chat_id=order_info['chat_id'],
        text=client_message
    )

    # Обновляем сообщение у администратора
    original_text = query.message.text
    new_text = f"{original_text}\n\n---\nСТАТУС: {admin_status} маэстро"
    await query.edit_message_text(new_text, reply_markup=None)


def main():
    # Создаем Application стандартным способом
    app = Application.builder() \
        .token(TOKEN) \
        .arbitrary_callback_data(True) \
        .build()

    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    print("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()