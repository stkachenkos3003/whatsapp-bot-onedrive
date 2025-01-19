from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
import time
import os
from requests.auth import HTTPBasicAuth
import msal

# -----------------------------------------
# Константы для Twilio (Вынести в Env Vars)
# -----------------------------------------
TWILIO_ACCOUNT_SID = "ACbe089f13a1eada6857d74d24c7e41e87"
TWILIO_AUTH_TOKEN = "0373e28512a6b4a1302bd2d176727ab6"

# -----------------------------------------
# Константы для Microsoft Graph (Вынести в Env Vars)
# -----------------------------------------
CLIENT_ID = "4d379371-81d6-4ae2-834d-f1f1df1d2014"
CLIENT_SECRET = "faF8Q~1y_fnvVlZ7MHYuGDq7v2joRb6b-NrEva9r"
TENANT_ID = "a0cd680a-617d-480a-9460-adb573d57b0a"
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["https://graph.microsoft.com/.default"]

# Пример: загрузка в OneDrive конкретного пользователя (UPN)
# (Пусть это будет ваш UPN; убедитесь, что OneDrive активирована)
USER_UPN = "admin@shefergroup.onmicrosoft.com"

# Обратите внимание, что указываем только до WhatsAppFiles/ (папка),
# а *название файла* мы подставим потом (см. upload_to_onedrive).
BASE_UPLOAD_URL = f"https://graph.microsoft.com/v1.0/users/{USER_UPN}/drive/root:/WhatsAppFiles"

# Словарь MIME → расширения
MIME_EXTENSIONS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    # ... добавляйте при необходимости ...
}

def get_extension(content_type):
    return MIME_EXTENSIONS.get(content_type, ".bin")

def get_access_token():
    msal_app = msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )
    result = msal_app.acquire_token_for_client(scopes=SCOPES)
    if "access_token" in result:
        return result["access_token"]
    else:
        raise Exception(f"Не удалось получить токен: {result}")

def download_file_from_twilio(media_url, local_filename="received_file"):
    resp = requests.get(media_url, auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    if resp.status_code == 200:
        with open(local_filename, "wb") as f:
            f.write(resp.content)
        return local_filename
    else:
        raise Exception(f"Ошибка скачивания файла: {resp.status_code}, {resp.text}")

def upload_to_onedrive(local_file_path, filename_onedrive):
    """
    local_file_path: локальный путь к скачанному файлу
    filename_onedrive: имя файла, под которым сохранить в папке WhatsAppFiles
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    # Формируем полный URL с именем файла, например:
    # https://graph.microsoft.com/v1.0/users/UPN/drive/root:/WhatsAppFiles/test.xlsx:/content
    upload_url = f"{BASE_UPLOAD_URL}/{filename_onedrive}:/content"

    with open(local_file_path, "rb") as f:
        resp = requests.put(upload_url, headers=headers, data=f)

    if resp.status_code == 201:
        print("Файл успешно загружен в OneDrive!")
    else:
        raise Exception(f"Ошибка загрузки: {resp.status_code}, {resp.text}")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.form
    num_media = int(data.get("NumMedia", 0))
    from_raw = data.get("From", "")  # "whatsapp:+12345678901"
    sender_number = from_raw.replace("whatsapp:", "")

    resp = MessagingResponse()

    if num_media > 0:
        media_url = data.get("MediaUrl0")
        content_type = data.get("MediaContentType0")  # MIME
        try:
            local_file = download_file_from_twilio(media_url, "temp_file")
            # Формируем имя "номер_отправителя_timestamp.расширение"
            extension = get_extension(content_type)
            timestamp = int(time.time())
            filename_onedrive = f"{sender_number}_{timestamp}{extension}"

            upload_to_onedrive(local_file, filename_onedrive)
            resp.message(f"Файл {filename_onedrive} успешно получен и загружен!")
            # Удаляем временный
            if os.path.exists(local_file):
                os.remove(local_file)
        except Exception as e:
            print(f"Ошибка: {e}")
            resp.message("Ошибка при загрузке файла.")
    else:
        # Если нет медиа, обрабатываем как текст
        text_body = data.get("Body", "").strip()
        if text_body:
            resp.message(f"Вы написали: {text_body}")
        else:
            resp.message("Сообщение пустое, попробуйте ещё раз.")

    return str(resp)

@app.route("/")
def index():
    return "Hello from the WhatsApp -> OneDrive bot!"

if __name__ == "__main__":
    app.run(port=5000, debug=True)
