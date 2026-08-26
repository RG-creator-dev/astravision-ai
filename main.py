import os
import io
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types
from PIL import Image

# 1. Configuración de Flask y Clientes
app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Ej: https://astravision-ai.onrender.com

# Inicializar cliente de Google GenAI
client_ai = genai.Client(api_key=GEMINI_API_KEY)

# Configurar Aplicación de Telegram
ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()

# 2. Instrucciones del Sistema para Astravisión AI
SYSTEM_INSTRUCTION = (
    "Eres Astravisión AI, un místico experto en quiromancia y lecturas visuales. "
    "Tu objetivo es interpretar los trazos, líneas de las manos e imágenes que el usuario envíe. "
    "Responde siempre con un tono visionario, claro, respetuoso y profesional."
)

# Modelo actual que iremos probando
CURRENT_MODEL = "gemini-3.0-flash"

# 3. Función de análisis multimodal con Gemini
def analizar_lectura(image_bytes: bytes) -> str:
    # Convertir bytes de la imagen a objeto PIL
    image = Image.open(io.BytesIO(image_bytes))

    # Realizar llamada a la API de Gemini
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

# 4. Handlers de Telegram
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "Buscador"
    mensaje = (
        f"✨ Bienvenida a Astravisión AI, {user_name}, especialista místico en quiromancia.\n\n"
        "Envía una fotografía de tu mano o consulta visual para revelar lo que los trazos tienen guardado para ti."
    )
    await update.message.reply_text(mensaje)

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Enviar mensaje de espera inmediato
    status_msg = await update.message.reply_text("✨ Analizando los trazos místicos y revelando el destino...")

    try:
        # Descargar la foto enviada por el usuario
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        # Ejecutar llamada a la API en un hilo secundario para no bloquear el bot
        loop = asyncio.get_running_loop()
        resultado = await loop.run_in_executor(None, analizar_lectura, photo_bytes)

        # Enviar el análisis al usuario
        await update.message.reply_text(resultado)

    except Exception as e:
        error_msg = f"❌ Error al procesar la imagen ({CURRENT_MODEL}): {str(e)}"
        await update.message.reply_text(error_msg)

# Registrar Handlers
ptb_app.add_handler(CommandHandler("start", start_handler))
ptb_app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

# 5. Rutas de Flask para Webhook
@app.route("/", methods=["GET", "HEAD"])
def index():
    return f"Astravisión AI en vivo. Modelo activo: {CURRENT_MODEL}", 200

@app.route(f"/telegram/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_app.bot)
        
        # Procesar actualización en el loop de eventos asíncrono
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(ptb_app.process_update(update))
        loop.close()

        return "OK", 200

# 6. Registrar Webhook al iniciar
def setup_webhook():
    if WEBHOOK_URL:
        full_url = f"{WEBHOOK_URL}/telegram/{TELEGRAM_TOKEN}"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(ptb_app.bot.set_webhook(url=full_url))
        loop.close()
        if success:
            print(f"🤖 Webhook registrado exitosamente en: {full_url}")

# Inicialización
setup_webhook()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
