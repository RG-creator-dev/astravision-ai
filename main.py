import os
import io
import asyncio
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
from google import genai
from PIL import Image

# Variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
WEBHOOK_URL = f"https://astravision-ai.onrender.com/telegram/{TELEGRAM_BOT_TOKEN}"

# Clientes
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error inicializando Supabase: {e}")

client_ai = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = Flask(__name__)
CORS(app)

# Inicialización de la aplicación de Telegram
telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build() if TELEGRAM_BOT_TOKEN else None

def get_or_create_user(telegram_id: int, username: str):
    if not supabase:
        return {"credits": 3, "is_vip": False}
    try:
        res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
        if res.data:
            return res.data[0]
        else:
            new_user = {"telegram_id": telegram_id, "username": username or "Usuario", "credits": 3, "is_vip": False}
            inserted = supabase.table("users").insert(new_user).execute()
            return inserted.data[0]
    except Exception as e:
        print(f"Error Supabase: {e}")
        return {"credits": 3, "is_vip": False}

def update_user_credits(telegram_id: int, new_credits: int):
    if supabase:
        try:
            supabase.table("users").update({"credits": new_credits}).eq("telegram_id", telegram_id).execute()
        except Exception as e:
            print(f"Error actualizando créditos: {e}")

def analizar_lectura(prompt_text: str, image_pil=None) -> str:
    if not client_ai:
        return "El servicio de IA no está configurado (falta GEMINI_API_KEY)."
    
    system_instruction = (
        "Eres AstraVisión AI, una experta mística en Quiromancia (lectura de la palma de la mano) y Cafemancia (lectura del poso de café). "
        "Si recibes una imagen de una mano, analiza visualmente las líneas (Corazón, Cabeza, Vida, Destino) y montes. "
        "Si recibes una imagen de una taza de café, analiza las formas y patrones dejados por los residuos. "
        "Si recibes solo texto, responde desde la perspectiva mística de la quiromancia y cafemancia. "
        "Estructura tus lecturas con tono sabio, místico, inspirador y empático, usando emojis pertinentes."
    )
    
    try:
        contents = [system_instruction, prompt_text]
        if image_pil:
            contents.append(image_pil)

        response = client_ai.models.generate_content(
            model='gemini-2.0-flash',
            contents=contents,
        )
        return response.text
    except Exception as e:
        print(f"Error en Gemini API: {e}")
        return f"Ocurrió un detalle místico al leer la imagen: {str(e)}"

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)
    msg = (
        f"🖐️☕ **¡Bienvenido a AstraVisión AI, {user.first_name}!**\n\n"
        f"Especialista mística en **Quiromancia** (Lectura de Mano) y **Cafemancia** (Lectura de Café).\n"
        f"Tienes **{db_user.get('credits', 0)} lecturas gratuitas** disponibles.\n\n"
        f"📸 **Envía una foto clara de tu palma o de tu taza de café** junto a tu pregunta en el comentario (ej: *'¿Cómo me ves en el amor?'*)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)
    
    credits = db_user.get("credits", 0)
    is_vip = db_user.get("is_vip", False)
    
    if not is_vip and credits <= 0:
        await update.message.reply_text("🔒 Has agotado tus lecturas gratuitas. Adquiere acceso ilimitado en nuestra web para continuar.")
        return

    waiting_msg = await update.message.reply_text("🔮 *Analizando los trazos místicos y revelando el destino...*", parse_mode="Markdown")
    
    image_pil = None
    prompt_text = "Realiza una lectura detallada enfocada en mi energía actual y las señales reveladas."

    try:
        if update.message.photo:
            photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
            image_bytes = io.BytesIO()
            await photo_file.download_to_memory(image_bytes)
            image_bytes.seek(0)
            image_pil = Image.open(image_bytes)
            
            if update.message.caption:
                prompt_text = update.message.caption
        elif update.message.text:
            prompt_text = update.message.text

        respuesta = analizar_lectura(prompt_text, image_pil)
        
        if not is_vip:
            update_user_credits(user.id, credits - 1)
            
        await waiting_msg.edit_text(respuesta)

    except Exception as e:
        print(f"Error procesando mensaje/foto: {e}")
        await waiting_msg.edit_text(f"⚠️ Ocurrió una interrupción al procesar la imagen: {str(e)}")

# Registro de Handlers de Telegram
if telegram_app:
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, handle_message))

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "service": "AstraVision Quiromancia y Cafemancia"}), 200

def process_update_in_thread(update):
    asyncio.run(telegram_app.process_update(update))

@app.route(f'/telegram/<token>', methods=['POST'])
def telegram_webhook(token):
    if token != TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    
    threading.Thread(target=process_update_in_thread, args=(update,)).start()
    
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    if telegram_app:
        asyncio.run(telegram_app.initialize())
        
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
        print(f"🤖 Webhook registrado exitosamente en: {WEBHOOK_URL}")

    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
