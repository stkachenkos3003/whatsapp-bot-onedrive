from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from requests.auth import HTTPBasicAuth
import os
import msal
import time

app = Flask(__name__)

# -----------------------------------------
# Константы для Twilio (Вынести в Env Vars)
# -----------------------------------------
TWILIO_ACCOUNT_SID = "ACbe089f13a1eada6857d74d24c7e41e87"
TWILIO_AUTH_TOKEN = "179ed89bc958f8354cb5d23358c682cd"

# -----------------------------------------
# Константы для Microsoft Graph (Вынести в Env Vars)
# -----------------------------------------
CLIENT_ID = "4d379371-81d6-4ae2-834d-f1f1df1d2014"
CLIENT_SECRET = "faF8Q~1y_fnvVlZ7MHYuGDq7v2joRb6b-NrEva9r"
TENANT_ID = "a0cd680a-617d-480a-9460-adb573d57b0a"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

# Пример: загрузка в OneDrive конкретного пользователя (UPN).
# Убедитесь, что OneDrive для этого пользователя активирована.
USER_UPN = "admin@shefergroup.onmicrosoft.com"

# Базовый URL для папки WhatsAppFiles (без указания файла):
BASE_UPLOAD_URL = f"https://graph.microsoft.com/v1.0/users/{USER_UPN}/drive/root:/WhatsAppFiles"

# Словарь MIME → расширения (дополните по необходимости)
MIME_EXTENSIONS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    # ... добавляйте другие MIME, если нужно ...
}

def get_extension(content_type):
    """
    По MIME-типу возвращаем подходящее расширение, иначе .bin
    """
    return MIME_EXTENSIONS.get(content_type, ".bin")

def get_access_token():
    """
    Получаем application access token (app-only).
    Убедитесь, что у приложения есть Files.ReadWrite.All (Application) + Admin Consent.
    """
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET
    )
    result = msal_app.acquire_token_for_client(scopes=SCOPES)
    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception("Не удалось получить токен доступа: ", result)

def download_file_from_twilio(media_url, file_name="received_file"):
    """
    Скачивает файл из Twilio (WhatsApp вложение) c Basic Auth (SID, TOKEN),
    сохраняет локально под именем file_name.
    """
    resp = requests.get(media_url, auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    if resp.status_code == 200:
        with open(file_name, "wb") as f:
            f.write(resp.content)
        return file_name
    else:
        raise Exception(f"Ошибка скачивания файла: {resp.status_code}, {resp.text}")

def upload_to_onedrive(local_file_path, final_filename):
    """
    Загружает локальный файл в OneDrive (папка WhatsAppFiles),
    используя final_filename в пути.
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    # Формируем полный URL с именем файла, напр.:
    # https://graph.microsoft.com/v1.0/users/UPN/drive/root:/WhatsAppFiles/filename.xlsx:/content
    upload_url = f"{BASE_UPLOAD_URL}/{final_filename}:/content"

    with open(local_file_path, "rb") as f:
        resp = requests.put(upload_url, headers=headers, data=f)

    # Если файл не существовал — 201 Created, если перезаписываем — 200 OK,
    # но благодаря уникальному имени перезаписи быть не должно.
    if resp.status_code in [200, 201]:
        print(f"Файл {final_filename} успешно загружен (код {resp.status_code}).")
    else:
        print(f"Ошибка загрузки: {resp.status_code}, {resp.text}")
        raise Exception("Ошибка при загрузке.")

@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Основной обработчик входящих WhatsApp-сообщений
    """
    data = request.form
    # Число вложений
    num_media = int(data.get("NumMedia", 0))
    # Текст сообщения (если есть)
    incoming_text = data.get("Body", "").strip()
    # Номер отправителя, например, "whatsapp:+71234567890"
    from_raw = data.get("From", "")
    sender_number = from_raw.replace("whatsapp:", "")  # -> "+71234567890"

    resp = MessagingResponse()

    if num_media > 0:
        # Есть вложение (берём первое)
        media_url = data.get("MediaUrl0")
        content_type = data.get("MediaContentType0") or ""
        try:
            # Скачиваем во временный файл
            local_file = download_file_from_twilio(media_url, "temp_file")

            # Генерируем расширение
            extension = get_extension(content_type)

            # Генерируем уникальный суффикс (timestamp), чтобы не перезаписывать
            unique_part = str(int(time.time()))

            # Сценарий A: вкладка без текста
            # Сценарий B: вложение + есть текст
            if incoming_text:
                # Файл: "номерОтправителя_текст_уникальный.расширение"
                final_filename = f"{sender_number}_{incoming_text}_{unique_part}{extension}"
            else:
                # Файл: "номерОтправителя_уникальный.расширение"
                final_filename = f"{sender_number}_{unique_part}{extension}"

            # Загружаем в OneDrive
            upload_to_onedrive(local_file, final_filename)

            # Удаляем локальный файл
            if os.path.exists(local_file):
                os.remove(local_file)

            resp.message(f"Файл '{final_filename}' успешно загружен в облако!")
        
        except Exception as e:
            print(f"Ошибка: {e}")
            resp.message("Ошибка при загрузке файла.")
    else:
        # Нет вложений — это чисто текст
        if incoming_text:
            resp.message(f"Вы написали: {incoming_text}")
        else:
            resp.message("Сообщение пустое, попробуйте ещё раз.")

    return str(resp)

@app.route("/")
def index():
    return "Hello from the WhatsApp -> OneDrive bot!"

if __name__ == "__main__":
    app.run(port=5000, debug=True)
