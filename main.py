import os
import io
import asyncio
import threading
from flask import Flask
from PIL import Image
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai

# ------------------------------------------------------------------
# 1. Servidor Web Mínimo (Mantiene activo Render en el Plan Gratuito)
# ------------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Astravisión AI está activo y funcionando.", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# Iniciar servidor web en un hilo secundario
threading.Thread(target=run_web_server, daemon=True).start()

# ------------------------------------------------------------------
# 2. Configuración de API Keys y Cliente Gemini
# ------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Cliente de la librería oficial google-genai
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.6-flash"

# ------------------------------------------------------------------
# 3. Funciones del Bot de Telegram
# ------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "¡Hola! Soy Astravisión AI. Envíame un texto o una imagen y te responderé de inmediato."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=user_text
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error al procesar el mensaje: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or "Describe o analiza esta imagen."
    try:
        # Descargar la foto enviada por Telegram
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        # Enviar la imagen y el texto a Gemini 2.5 Flash
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, caption]
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error al procesar la imagen: {e}")

# ------------------------------------------------------------------
# 4. Inicialización Principal del Bot
# ------------------------------------------------------------------
def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("Falta la variable de entorno TELEGRAM_BOT_TOKEN")
    if not GEMINI_API_KEY:
        raise ValueError("Falta la variable de entorno GEMINI_API_KEY")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Registradores de comandos y mensajes
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot Astravisión AI iniciado correctamente...")
    app.run_polling()

if __name__ == "__main__":
    main()
