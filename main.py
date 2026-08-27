import os
import io
import logging
import asyncio
import requests
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

    if supabase:
        try:
            res = supabase.table("users").select("*").eq("telegram_id", str(user_id)).execute()
            if not res.data:
                supabase.table("users").insert({
                    "telegram_id": str(user_id),
                    "credits": 1,
                    "is_premium": False
                }).execute()
        except Exception as e:
            logger.error(f"Error en Supabase start: {e}")

    mensaje = f"✨ ¡Bienvenido a AstraVisión AI, {first_name}! ✨\n\nEnvíame una fotografía clara de la palma de tu mano y revelaré las líneas de tu destino."
    await update.message.reply_text(mensaje)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    user_data = None
    if supabase:
        try:
            res = supabase.table("users").select("*").eq("telegram_id", str(user_id)).execute()
            if res.data:
                user_data = res.data[0]
            else:
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

    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    image = Image.open(io.BytesIO(image_bytes))

    prompt = (
        "Eres AstraVisión AI, un bot místico experto en quiromancia. Analiza esta imagen de una mano y realiza "
        "una lectura mística detallada, profunda y reveladora sobre el destino, salud, amor y fortuna. "
        "Usa emojis, tono místico y positivo."
    )

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

    if supabase and user_data:
        try:
            nuevos_creditos = max(0, creditos - 1)
            supabase.table("users").update({"credits": nuevos_creditos}).eq("telegram_id", str(user_id)).execute()
        except Exception as e:
            logger.error(f"Error actualizando créditos: {e}")

    await context.bot.send_message(chat_id=chat_id, text=respuesta_texto)

if tg_app:
    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

async def procesar_update_seguro(update: Update):
    async with tg_app:
        await tg_app.process_update(update)

# Rutas Flask
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "Servidor AstraVisión AI Activo y Running", 200

@app.route(f'/telegram/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.method == "POST" and tg_app:
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        asyncio.run(procesar_update_seguro(update))
        return "ok", 200
    return "bad request", 400

# Ruta para la pasarela de pago en la web
@app.route('/create-payment-web', methods=['POST'])
def create_payment_web():
    if not NOWPAYMENTS_API_KEY:
        return jsonify({"error": "NOWPayments API Key no configurada"}), 500
        
    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "price_amount": 5.00,
        "price_currency": "usd",
        "fixed_rate": False,
        "order_description": "AstraVisión AI - Acceso Ilimitado",
        "ipn_callback_url": "https://astravision-ai.onrender.com/nowpayments-ipn",
        "success_url": "https://t.me/astravision_ai_bot",
        "cancel_url": "https://rg-creator-dev.github.io/astravision-ai/"
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code in [200, 201]:
            data = res.json()
            return jsonify({"invoice_url": data.get("invoice_url")}), 200
        else:
            logger.error(f"Error creando factura NOWPayments: {res.text}")
            return jsonify({"error": "No se pudo generar la factura"}), 500
    except Exception as e:
        logger.error(f"Excepción en create_payment_web: {e}")
        return jsonify({"error": "Error de conexión"}), 500

def setup_webhook():
    if TELEGRAM_BOT_TOKEN:
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
