import os
import io
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
from google import genai
from google.genai import types
from PIL import Image

# Configuración de Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar Variables de Entorno
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Inicialización de Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error inicializando Supabase: {e}")

# Inicialización del cliente de Gemini
client_gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Lista de modelos visión en orden de intento
MODELOS_VISION_FALLBACK = [
    "gemini-3.6-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

# Inicialización de Flask
app = Flask(__name__)
CORS(app)

# Configuración del Bot de Telegram (vía Webhook)
tg_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build() if TELEGRAM_BOT_TOKEN else None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Usuario"

    # Registrar usuario en Supabase si no existe
    if supabase:
        try:
            res = supabase.table("users").select("*").eq("telegram_id", str(user_id)).execute()
            if not res.data:
                supabase.table("users").insert({
                    "telegram_id": str(user_id),
                    "credits": 1,  # 1 lectura gratuita de bienvenida
                    "is_premium": False
                }).execute()
        except Exception as e:
            logger.error(f"Error en Supabase start: {e}")

    mensaje = f"✨ ¡Bienvenido a AstraVisión AI, {first_name}! ✨\n\nEnvíame una fotografía clara de la palma de tu mano y revelaré las líneas de tu destino."
    await update.message.reply_text(mensaje)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # 1. Verificar créditos en Supabase
    user_data = None
    if supabase:
        try:
            res = supabase.table("users").select("*").eq("telegram_id", str(user_id)).execute()
            if res.data:
                user_data = res.data[0]
            else:
                # Crear si no existía
                insert_res = supabase.table("users").insert({
                    "telegram_id": str(user_id),
                    "credits": 1,
                    "is_premium": False
                }).execute()
                user_data = insert_res.data[0]
        except Exception as e:
            logger.error(f"Error consultando usuario: {e}")

    creditos = user_data.get("credits", 0) if user_data else 0

    if creditos <= 0:
        await update.message.reply_text("⛔ Has agotado tus lecturas disponibles.\n\nAdquiere acceso ilimitado o recarga créditos en nuestra web para continuar.")
        return

    await update.message.reply_text("🔮 *Analizando los trazos místicos de tu mano...*", parse_mode="Markdown")

    # 2. Descargar la imagen enviada por Telegram
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    image = Image.open(io.BytesIO(image_bytes))

    # 3. Prompt de quiromancia
    prompt = (
        "Eres AstraVisión AI, un bot místico experto en quiromancia. Analiza esta imagen de una mano y realiza "
        "una lectura mística detallada, profunda y reveladora sobre el destino, salud, amor y fortuna. "
        "Usa emojis, tono místico y positivo."
    )

    # 4. Procesar con Gemini (Fallback de modelos)
    respuesta_texto = None
    for modelo in MODELOS_VISION_FALLBACK:
        try:
            logger.info(f"Intentando generar lectura con modelo: {modelo}")
            response = client_gemini.models.generate_content(
                model=modelo,
                contents=[prompt, image]
            )
            respuesta_texto = response.text
            if respuesta_texto:
                break
        except Exception as e:
            logger.warning(f"Fallo modelo {modelo}: {e}")

    if not respuesta_texto:
        await update.message.reply_text("⚠️ Ocurrió una interrupción al conectar con los oráculos cósmicos. Intenta nuevamente en unos instantes.")
        return

    # 5. Descontar crédito en Supabase
    if supabase and user_data:
        try:
            nuevos_creditos = max(0, creditos - 1)
            supabase.table("users").update({"credits": nuevos_creditos}).eq("telegram_id", str(user_id)).execute()
        except Exception as e:
            logger.error(f"Error actualizando créditos: {e}")

    # 6. Enviar mensaje de respuesta
    await context.bot.send_message(chat_id=chat_id, text=respuesta_texto)

# Registrar Handlers en el Bot
if tg_app:
    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# Rutas Flask
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "Servidor AstraVisión AI Activo y Running", 200

@app.route(f'/telegram/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.method == "POST" and tg_app:
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        import asyncio
        asyncio.run(tg_app.process_update(update))
        return "ok", 200
    return "bad request", 400

# Endpoint para registrar Webhook al iniciar
def setup_webhook():
    if TELEGRAM_BOT_TOKEN:
        import requests
        webhook_url = f"https://astravision-ai.onrender.com/telegram/{TELEGRAM_BOT_TOKEN}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook?url={webhook_url}"
        r = requests.get(url)
        if r.status_code == 200:
            logger.info(f"🤖 Webhook registrado exitosamente en: {webhook_url}")
        else:
            logger.error(f"Fallo al registrar webhook: {r.text}")

if __name__ == '__main__':
    setup_webhook()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
