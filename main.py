from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import os
import requests

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vero2026")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "1377462945443421")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# 1. ESTA ES LA RUTA QUE META NECESITA PARA VALIDAR - ESTA TE FALTABA
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    print(f"VERIFICACION: mode={mode} token={token} challenge={challenge}")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK VERIFICADO OK!")
        return PlainTextResponse(challenge, status_code=200)
    else:
        print(f"VERIFICACION FALLIDA: esperado {VERIFY_TOKEN} llego {token}")
        return PlainTextResponse("Forbidden", status_code=403)

# Ruta para que tu no veas 405 en /
@app.get("/")
async def root():
    return {"status": "VERO running", "webhook": "/webhook"}

# 2. ESTA ES LA RUTA QUE RECIBE LOS MENSAJES
@app.post("/webhook")
async def receive_message(request: Request):
    body = await request.json()
    print(f"WEBHOOK RECIBIDO: {body}")

    try:
        entry = body["entry"][0]["changes"][0]["value"]

        # Si es solo un status de lectura, ignoramos
        if "statuses" in entry:
            print("Es un status, lo ignoro")
            return {"status": "ok"}

        if "messages" not in entry:
            return {"status": "ok"}

        message = entry["messages"][0]
        from_number = message["from"]

        # Texto del usuario
        user_text = ""
        if message["type"] == "text":
            user_text = message["text"]["body"]
        else:
            user_text = "Me mandaste una imagen/archivo"

        print(f"Mensaje de {from_number}: {user_text}")

        # --- AQUI VA TU LOGICA DE VERO / GROQ ---
        # Por ahora contesta fijo para probar que ya llegan los logs
        respuesta = f"Hola MDom! Ya recibo tus mensajes. Me dijiste: {user_text}. VERO funcionando!"

        # Mandar respuesta por WhatsApp
        url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": from_number,
            "type": "text",
            "text": {"body": respuesta}
        }

        resp = requests.post(url, headers=headers, json=data)
        print(f"Respuesta enviada: {resp.status_code} - {resp.text}")

    except Exception as e:
        print(f"ERROR en webhook: {e}")

    return {"status": "ok"}
