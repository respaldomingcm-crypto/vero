import os
import base64
from fastapi import FastAPI, Request, Query, UploadFile, File
from fastapi.responses import PlainTextResponse, JSONResponse
import httpx
from groq import Groq

app = FastAPI(title="VERO - See it. Solved.")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vero2026")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
You are VERO. You are not a describer, you are a solver. From VER + Resolver.
User sends a photo of a problem (CFE bill, ticket, fridge, contract).

You MUST return JSON with:
{
 "what_it_is": "explicación clara y VERDADERA en español",
 "hidden_cost": "si hay ahorro real, si no hay, di 'No hay sobrecosto, tu tarifa es correcta'",
 "action_plan": "2 bullets realistas",
 "draft_message": "texto listo para enviar si aplica",
 "savings": 0
}

REGLAS CRÍTICAS - NO INVENTAR:
1. CFE MEM: Si el recibo dice Mercado Eléctrico Mayorista, NO digas que es un error. Significa que el usuario superó ~1MW o el umbral de Suministro Básico y es Usuario Calificado por la Ley de la Industria Eléctrica. Su tarifa es NO REGULADA, con precios marginales variables por hora. Requiere medición horaria. No es un cobro indebido. Explica esto.
2. Solo reporta ahorro si es REAL y verificable. Si no hay estafa, di la verdad: "Tu recibo es correcto para tu nivel de consumo".
3. Siempre en español, informal, directo.
4. Nunca digas "soy una IA". Eres VERO.
5. Si no puedes verificar un dato, NO lo inventes.
6. Termina con: ¿Le doy a Sí, hazlo? solo si hay acción real que hacer.

Ejemplo MEM correcto:
what_it_is: "Recibo CFE por $1,358 en esquema MEM. Estás como Usuario Calificado porque tu consumo (19,055 kWh) supera el límite de tarifa doméstica."
hidden_cost: "No hay sobrecosto indebido. Los $387 de Transmisión y $312 de Capacidad son parte normal de la tarifa MEM no regulada."
"""

@app.get("/")
async def root():
    return {"status": "VERO online", "tagline": "Apunta. VERO resuelve."}

@app.post("/analyze")
async def analyze_ticket(file: UploadFile = File(...)):
    if not client:
        return JSONResponse({"error": "GROQ_API_KEY no configurada en Render"}, status_code=500)
    try:
        image_bytes = await file.read()
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:{file.content_type};base64,{b64_image}"
        completion = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analiza esta foto de un problema real. Devuelve SOLO el JSON. No inventes cargos indebidos."},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
            temperature=0.2,
            max_tokens=800
        )
        result = completion.choices[0].message.content
        return JSONResponse({"vero_result": result})
    except Exception as e:
        print(f"Error /analyze: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Verification failed", status_code=403)

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    try:
        entry = body["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return JSONResponse({"status": "no message"})
        msg = entry["messages"][0]
        from_number = msg["from"]
        msg_type = msg["type"]
        analysis_text = ""
        if msg_type == "image":
            image_id = msg["image"]["id"]
            async with httpx.AsyncClient() as http_client:
                media_resp = await http_client.get(
                    f"https://graph.facebook.com/v20.0/{image_id}",
                    headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
                )
                media_url = media_resp.json().get("url")
                if client:
                    completion = client.chat.completions.create(
                        model="qwen/qwen3.8-27b",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": [
                                {"type": "text", "text": "Analiza esta foto. Devuelve SOLO el JSON. No inventes."},
                                {"type": "image_url", "image_url": {"url": media_url}}
                            ]}
                        ],
                        temperature=0.2,
                        max_tokens=800
                    )
                    analysis_text = completion.choices[0].message.content
        else:
            text = msg.get("text", {}).get("body", "")
            if client:
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Usuario dice: {text}. Pídele una foto de su problema."}
                    ]
                )
                analysis_text = completion.choices[0].message.content
        if analysis_text:
            await send_whatsapp_message(from_number, f"👁 *VERO vio esto:*\n\n{analysis_text}")
    except Exception as e:
        print(f"Error VERO: {e}")
    return JSONResponse({"status": "ok"})

def format_vero_response(json_text: str) -> str:
    return f"👁 *VERO vio esto:*\n\n{json_text}\n\n¿Quieres que lo haga por ti? Responde *Sí, hazlo* 👇"

async def send_whatsapp_message(to: str, text: str):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        print("Missing WhatsApp creds")
        return
    url = f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text[:4000]}
    }
    async with httpx.AsyncClient() as http_client:
        await http_client.post(url, json=payload, headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        })
