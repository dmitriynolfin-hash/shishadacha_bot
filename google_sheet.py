import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
import time

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

CREDS_FILE = 'credentials.json'  # Замените на имя вашего файла с ключом
SPREADSHEET_NAME = 'Заказы shisha dacha bot'
WORKSHEET_NAME = 'Orders'


def save_order(order_data):
    """
    Сохраняет заказ в Google Таблицу
    Принимает только один аргумент - словарь order_data
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # секунды

    for attempt in range(MAX_RETRIES):
        try:
            # Аутентификация
            creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPE)
            client = gspread.authorize(creds)

            # Открываем таблицу
            spreadsheet = client.open(SPREADSHEET_NAME)
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)

            # Форматируем данные о товарах
            products_details = []
            for item in order_data['cart']:  # Используем корзину из order_data
                comment = item.get('comment', '')
                product_info = f"{item['name']} {comment}"
                products_details.append(f"{item['quantity']}x {product_info}")

            products_str = "\n".join(products_details)

            # Подготавливаем данные для записи
            order_row = [
                order_data['date'],
                order_data['delivery_date_time'],
                order_data['username'],
                order_data['phone'],
                order_data['tower'],
                order_data['apartment'],
                products_str,
                order_data['total'],
                str(order_data['user_id']),
                order_data['username_tg'] or ""
            ]

            # Добавляем новую строку
            worksheet.append_row(order_row)

            print(f"Заказ успешно сохранен: {order_data['username']}")
            return True

        except APIError as e:
            if e.response.status_code == 403 and 'disabled' in str(e).lower():
                print(f"Ошибка доступа к API (попытка {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"Критическая ошибка API: {e}")
                raise
        except Exception as e:
            print(f"Общая ошибка при сохранении заказа: {e}")
            raise

    print("Не удалось сохранить заказ после нескольких попыток")
    return False