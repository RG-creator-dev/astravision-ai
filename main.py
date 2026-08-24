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
# 1. Servidor Web Mínimo (Mantiene activo Render)
# ------------------------------------------------------------------
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Astravisión AI está activo.", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web_server, daemon=True).start()

# ------------------------------------------------------------------
# 2. Configuración de API Keys y Cliente Gemini
# ------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-3.6-flash"

# Prompt del sistema para definir la personalidad de AstraVisión AI
SYSTEM_PROMPT = """
Eres AstraVisión AI, una vidente, astróloga y mística experta en artes adivinatorias como la quiromancia (lectura de mano), la lecturas de posos de café (cafemancia), lecturas de cartas y astrología.

Tu objetivo es brindar lecturas místicas, profundas, intuitivas y empáticas:
1. Si el usuario te envía la imagen de una palma de la mano, realiza una lectura de quiromancia enfocándote en la Línea de la Vida, la Línea del Corazón, la Línea de la Cabeza y los Montes (Venus, Júpiter, etc.).
2. Si te envía una taza de café, interpreta los símbolos y figuras de los posos de café.
3. Si envía texto o preguntas astrales, responde con un tono místico, sabio y orientador.
4. NUNCA hagas descripciones técnicas ni analices el fondo de las fotos (no hables de paredes, luces, ni muebles). Ve directamente a la interpretación esotérica.
"""

# ------------------------------------------------------------------
# 3. Funciones del Bot de Telegram
# ------------------------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✨ Bienvenido a AstraVisión AI ✨\n\nSoy tu guía mística y astrológica. Envíame una fotografía de la palma de tu mano o tu taza de café, o hazme una consulta astral."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        prompt = f"{SYSTEM_PROMPT}\n\nConsulta del usuario: {user_text}"
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error astral: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or "Realiza la lectura mística de esta imagen."
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        prompt = f"{SYSTEM_PROMPT}\n\nInstrucción para la imagen: {caption}"
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[image, prompt]
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        await update.message.reply_text(f"Ocurrió un error al interpretar la imagen: {e}")

# ------------------------------------------------------------------
# 4. Inicialización Principal
# ------------------------------------------------------------------
def main():
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        raise ValueError("Faltan las variables de entorno requeridas.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot Astravisión AI iniciado correctamente...")
    app.run_polling()

if __name__ == "__main__":
    main()
