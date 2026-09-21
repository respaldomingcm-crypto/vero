import os
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
import httpx
from groq import Groq

app = FastAPI(title="VERO - See it. Solved.")

# ENV VARS - Set these in Render / Vercel
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "vero2026")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

SYSTEM_PROMPT = """
You are VERO. You are not a describer, you are a solver.
From VER + Resolver. Latin Verus = True.
User sends a photo of a real-life problem (bill, fridge, contract, bank statement).
You MUST return JSON with:
{
 "what_it_is": "short clear explanation in Spanish",
 "hidden_cost": "how much money/time is being lost, e.g. $399 MXN",
 "action_plan": "2 bullet points of what you will do",
 "draft_message": "ready to send email/complaint text",
 "savings": 1847
}
Rules:
- Always Spanish, informal, directo.
- Never say "soy una IA". You are VERO.
- Quantify savings.
- End with question: ¿Le doy a Sí, hazlo?
"""

@app.get("/")
async def root():
    return {"status": "VERO online", "tagline": "Apunta. VERO resuelve."}

# WhatsApp Verification (Meta requirement)
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
        # Extract message
        entry = body["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return JSONResponse({"status": "no message"})
        
        msg = entry["messages"][0]
        from_number = msg["from"]
        msg_type = msg["type"]

        analysis_text = ""
        
        if msg_type == "image":
            # Get image id
            image_id = msg["image"]["id"]
            # Download image URL from Meta
            async with httpx.AsyncClient() as http_client:
                media_resp = await http_client.get(
                    f"https://graph.facebook.com/v20.0/{image_id}",
                    headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
                )
                media_url = media_resp.json().get("url")
                # Download actual image bytes (simplified - in prod download and upload to Groq vision)
                # For hackathon MVP: we call Groq Vision directly with URL
                if client:
                    completion = client.chat.completions.create(
                        model="meta-llama/llama-4-maverick-17b-128e-instruct",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": [
                                {"type": "text", "text": "Analiza esta foto de un problema real. Devuelve SOLO el JSON."},
                                {"type": "image_url", "image_url": {"url": media_url}}
                            ]}
                        ],
                        temperature=0.2,
                        max_tokens=600
                    )
                    analysis_text = completion.choices[0].message.content
        else:
            text = msg.get("text", {}).get("body", "")
            if client:
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Usuario dice: {text}. Si no hay foto, pídele una foto de su problema (factura, refri, recibo)."}
                    ]
                )
                analysis_text = completion.choices[0].message.content

        # Send back to WhatsApp
        if analysis_text:
            await send_whatsapp_message(from_number, format_vero_response(analysis_text))

    except Exception as e:
        print(f"Error VERO: {e}")

    return JSONResponse({"status": "ok"})

def format_vero_response(json_text: str) -> str:
    # MVP formatter - in prod parse JSON
    return f"""👁️ *VERO vio esto:*\n\n{json_text}\n\n¿Quieres que lo haga por ti? Responde *Sí, hazlo* 👇"""

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

# Run: uvicorn main:app --host 0.0.0.0 --port 10000
