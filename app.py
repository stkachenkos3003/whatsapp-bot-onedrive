from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello from Render Deployment!"

@app.route("/webhook", methods=["POST"])
def webhook():
    # Читаем текст сообщения (Body) из request.form
    incoming_msg = request.form.get("Body", "")
    resp = MessagingResponse()
    
    # Формируем ответ
    if incoming_msg.strip():
        resp.message(f"Вы прислали: {incoming_msg}")
    else:
        resp.message("Сообщение пустое, попробуйте ещё раз.")

    return str(resp)  # Возвращаем TwiML

if __name__ == "__main__":
    app.run(port=5000)
