from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import requests
from requests.auth import HTTPBasicAuth
import os
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

# Ссылка для загрузки в папку WhatsAppFiles в корне OneDrive
file_name_onedrive = "some_unique_name.xlsx"
UPLOAD_URL = f"https://graph.microsoft.com/v1.0/users/{USER_UPN}/drive/root:/WhatsAppFiles/{file_name_onedrive}:/content"

app = Flask(__name__)

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


def upload_to_onedrive(local_file_path):
    """
    Загружает локальный файл в OneDrive (корневую папку 'WhatsAppFiles').
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    with open(local_file_path, "rb") as f:
        resp = requests.put(UPLOAD_URL, headers=headers, data=f)

    if resp.status_code == 201:
        print("Файл успешно загружен в OneDrive!")
    else:
        raise Exception(f"Ошибка загрузки: {resp.status_code}, {resp.text}")


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Основной обработчик входящих WhatsApp-сообщений
    """
    data = request.form
    incoming_text = data.get("Body", "")
    num_media = int(data.get("NumMedia", 0))

    resp = MessagingResponse()

    if num_media > 0:
        # Допустим, обрабатываем только первое вложение
        media_url = data.get("MediaUrl0")
        content_type = data.get("MediaContentType0")  # может быть xlsx, docx, pdf, и т.д.
        try:
            # Шаг 1: скачать файл локально
            local_file = download_file_from_twilio(media_url, "temp_file")
            
            # Шаг 2: загрузить файл в OneDrive
            upload_to_onedrive(local_file)
            
            # Шаг 3: удалить локальный файл (чтобы не засорять сервер)
            if os.path.exists(local_file):
                os.remove(local_file)

            resp.message(f"Файл получен ({content_type}) и загружен в облако!")
        
        except Exception as e:
            print(f"Ошибка: {e}")
            resp.message("Ошибка при загрузке файла.")
    else:
        # Нет вложений — это текст
        resp.message(f"Вы написали: {incoming_text}")

    return str(resp)


@app.route("/")
def index():
    return "Hello from the WhatsApp -> OneDrive bot!"


if __name__ == "__main__":
    app.run(port=5000, debug=True)
