import os
import io
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from PIL import Image

# 1. Configuración de Flask y Variables de Entorno
app = Flask(__name__)

# Mantenemos las claves exactamente como las tienes en tu panel de Render
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://astravision-ai.onrender.com")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("ERROR: La variable TELEGRAM_BOT_TOKEN no está configurada en Render.")

if not GEMINI_API_KEY:
    raise ValueError("ERROR: La variable GEMINI_API_KEY no está configurada en Render.")

# 2. Inicializar Clientes (Google GenAI y Telegram)
client_ai = genai.Client(api_key=GEMINI_API_KEY)
ptb_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Modelo de la serie 3 para esta prueba
CURRENT_MODEL = "gemini-3.0-flash"

# Instrucciones del Sistema para Astravisión AI
SYSTEM_INSTRUCTION = (
    "Eres Astravisión AI, una especialista mística en quiromancia y lecturas visuales. "
    "Tu objetivo es interpretar los trazos, líneas de las manos e imágenes que el usuario envíe. "
    "Responde siempre con un tono visionario, claro, respetuoso y profesional."
)

# 3. Función de análisis multimodal con Gemini
def analizar_lectura(image_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(image_bytes))

    response = client_ai.models.generate_content(
        model=CURRENT_MODEL,
        contents=[
            image,
            "Analiza detalladamente esta imagen. Interpreta sus trazos, líneas y símbolos místicos."
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.7,
        )
    )
    return response.text

# 4. Handlers del Bot de Telegram
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "Buscador"
    mensaje = (
        f"✨ Bienvenido a Astravisión AI {user_name}, especialista mística en quiromancia.\n\n"
        "Envía una fotografía de tu mano para analizar los trazos místicos y revelar el destino."
    )
    await update.message.reply_text(mensaje)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✨ Analizando los trazos místicos y revelando el destino...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        loop = asyncio.get_running_loop()
        resultado = await loop.run_in_executor(None, analizar_lectura, photo_bytes)

        await update.message.reply_text(resultado)

    except Exception as e:
        error_msg = f"❌ Error ({CURRENT_MODEL}): {str(e)}"
        await update.message.reply_text(error_msg)

# Registrar Handlers
ptb_app.add_handler(CommandHandler("start", start_handler))
ptb_app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

# 5. Rutas HTTP de Flask
@app.route("/", methods=["GET", "HEAD"])
def index():
    return f"Astravisión AI en vivo. Modelo activo: {CURRENT_MODEL}", 200

@app.route(f"/telegram/{TELEGRAM_BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_app.bot)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb_app.process_update(update))
        loop.close()

        return "OK", 200

# 6. Registro de Webhook automático
def setup_webhook():
    webhook_url = f"{RENDER_EXTERNAL_URL}/telegram/{TELEGRAM_BOT_TOKEN}"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(ptb_app.bot.set_webhook(url=webhook_url))
    loop.close()
    if success:
        print(f"🤖 Webhook registrado exitosamente en: {webhook_url}")

setup_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
