from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import os
import requests

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vero2026")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "1377462945443421")

@app.get("/")
async def root():
    return {"status": "VERO running OK"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    print(f"Verificando: {token}")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge, status_code=200)
    return PlainTextResponse("Forbidden", status_code=403)

@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print(f"RECIBIDO: {body}")
    try:
        value = body["entry"][0]["changes"][0]["value"]
        if "statuses" in value:
            return {"status": "ok"}
        if "messages" not in value:
            return {"status": "ok"}

        msg = value["messages"][0]
        from_number = msg["from"]
        text = msg.get("text", {}).get("body", "hola")

        url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
        data = {
            "messaging_product": "whatsapp",
            "to": from_number,
            "type": "text",
            "text": {"body": f"¡VERO ya funciona! Me dijiste: {text}"}
        }
        r = requests.post(url, headers=headers, json=data)
        print(f"Enviado: {r.text}")
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}
