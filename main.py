import os
import base64
from fastapi import FastAPI, Request, Query, UploadFile, File
from fastapi.responses import PlainTextResponse, JSONResponse
import httpx
from groq import Groq

app = FastAPI(title="VERO - See it. Solved. v3")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vero2026")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
You are VERO - Ver + Resolver. Analizas fotos de problemas reales (recibos CFE, tickets, refri, contratos).

DEVUELVE SOLO JSON valido:
{
 "what_it_is": "string en espanol",
 "hidden_cost": "string en espanol",
 "action_plan": "string con bullets •",
 "draft_message": "string",
 "savings": number
}

CONOCIMIENTO REAL CFE - NO INVENTAR - CRITICO:
1. UMBRAL MEM: Para ser Usuario Calificado en Mercado Electrico Mayorista (MEM) la Ley de la Industria Electrica y la CRE exigen minimo 1 Megavatio (1 MW = 1,000 kW) de demanda maxima en el punto de suministro. Solo grandes industrias, hoteles medianos/grandes, centros comerciales con subestaciones de media o alta tension.

2. RECIBO $1,300 NO ES MEM NUNCA: Un recibo de $1,300 pesos mensuales es domestico o pequeno negocio en baja tension, muy por debajo de 1 MW. NO califica para MEM. Si aparece leyenda MEM en recibo de $1,300 es:
   - Error de impresion o reetiquetado masivo: formatos de CFE agrupan leyendas regulatorias generales.
   - Homonimos o error de Ruta/RPU: sistema CFE asocio tu RPU a clave de media tension por error.

3. QUE HACER PARA $1,300 CON LEYENDA MEM: No buscar Suministrador Calificado. No es tramite de mercado. Solo aclaracion de Suministro Basico. Llamar al 071 o ir a Centro de Atencion CFE para aclarar estatus y asegurar que este catalogado en tarifa domestica/comercial baja tension regulada.

REGLAS DE ORO:
- Si recibo < $5,000 y dice MEM => Es ERROR de CFE, explica umbral 1 MW.
- No inventes ahorro de $712 como fraude. No hay sobrecosto MEM real porque no esta realmente en MEM.
- Si no hay ahorro real, pon savings: 0
- Espanol mexicano, directo, honesto.
- Nunca digas "soy una IA". Eres VERO.

EJEMPLO CORRECTO PARA ESTE CASO DE $1,358:
{
 "what_it_is": "Recibo CFE por $1,358 MXN con leyenda de MEM, pero tu consumo es domestico de baja tension y no calificas para MEM.",
 "hidden_cost": "No hay sobrecosto de $712 por MEM. Con $1,300/mes estas muy por debajo del umbral de 1 MW que exige la CRE para Usuario Calificado. La leyenda es un error de impresion o de tu RPU en el sistema de CFE.",
 "action_plan": "• No necesitas Suministrador Calificado ni tramites de mercado. Tu consumo pertenece a Tarifa Regulada de Suministro Basico.\\n• Solo llama al 071 o acude a tu Centro de Atencion CFE con tu RPU para aclarar el estatus y que lo recataloguen correctamente a tarifa domestica/baja tension.",
 "draft_message": "Asunto: Aclaracion de leyenda MEM en recibo domestico - RPU 05DN10F010560220\\n\\nEstimados CFE, mi recibo de $1,358 aparece con referencia a Mercado Mayorista, pero mi consumo es domestico de baja tension muy por debajo de 1 MW. Solicito verificar que mi contrato este correctamente catalogado en Tarifa de Suministro Basico y se elimine la leyenda de MEM por error de sistema. RPU: 05DN10F010560220 - Servicio 9686006000014. Quedo atento.",
 "savings": 0
}
"""

@app.get("/")
async def root():
    return {"status": "VERO online v3 - Honesto", "model": "qwen/qwen3.8-27b", "tagline": "Apunta. VERO resuelve."}

@app.post("/analyze")
async def analyze_ticket(file: UploadFile = File(...)):
    if not client:
        return JSONResponse({"error": "Falta GROQ_API_KEY en Render"}, status_code=500)
    try:
        image_bytes = await file.read()
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:{file.content_type};base64,{b64_image}"
        completion = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analiza esta foto. Devuelve SOLO el JSON honesto. Si es recibo CFE de $1300 con leyenda MEM, explica que NO califica para MEM por umbral 1MW y que es error de CFE. No inventes fraudes."},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
            temperature=0.1,
            max_tokens=900
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
        analysis_text = ""
        if msg["type"] == "image" and client:
            image_id = msg["image"]["id"]
            async with httpx.AsyncClient() as http_client:
                media_resp = await http_client.get(
                    f"https://graph.facebook.com/v20.0/{image_id}",
                    headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
                )
                media_data = media_resp.json()
                media_url = media_data.get("url")
                if media_url:
                    completion = client.chat.completions.create(
                        model="qwen/qwen3.8-27b",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": [
                                {"type": "text", "text": "Analiza esta foto. JSON honesto. Si es $1300 con MEM, es error CFE."},
                                {"type": "image_url", "image_url": {"url": media_url}}
                            ]}
                        ],
                        temperature=0.1,
                        max_tokens=900
                    )
                    analysis_text = completion.choices[0].message.content
        if analysis_text:
            await send_whatsapp_message(from_number, f"👁 VERO:\n\n{analysis_text}")
    except Exception as e:
        print(f"Error webhook VERO: {e}")
    return JSONResponse({"status": "ok"})

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
        await http_client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                "Content-Type": "application/json"
            }
        )
