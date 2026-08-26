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
from google.genai import types as genai_types
from PIL import Image

# ============================================================
# VARIABLES DE ENTORNO
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")  # necesario para validar el webhook de pago
WEBHOOK_URL = f"https://astravision-ai.onrender.com/telegram/{TELEGRAM_BOT_TOKEN}"

# Orígenes permitidos para CORS (solo tu web, no "*", ya que hay un endpoint de pagos)
ALLOWED_ORIGINS = [
    "https://rg-creator-dev.github.io",
]

# ============================================================
# CLIENTES
# ============================================================
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Error inicializando Supabase: {e}")

# IMPORTANTE: se fuerza api_version="v1" (estable) en vez del "v1beta" que
# el SDK usa por defecto. El v1beta es donde ocurren la mayoría de los 404
# de modelos que "sí existen" según ListModels.
client_ai = None
if GEMINI_API_KEY:
    client_ai = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=genai_types.HttpOptions(api_version="v1"),
    )

# Lista de modelos a intentar en orden. Si el primero no está habilitado
# en tu proyecto/región, se prueba el siguiente automáticamente.
MODELOS_VISION_FALLBACK = [
    "gemini-2.5-flash",
    "gemini-2.0-flash-001",
    "gemini-2.0-flash",
]

app = Flask(__name__)
CORS(app, resources={r"/create_payment": {"origins": ALLOWED_ORIGINS},
                      r"/payment_webhook": {"origins": "*"}})

telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build() if TELEGRAM_BOT_TOKEN else None


# ============================================================
# SUPABASE: USUARIOS Y CRÉDITOS
# ============================================================

def get_or_create_user(telegram_id: int, username: str):
    if not supabase:
        return {"credits": 3, "is_vip": False}
    try:
        res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
        if res.data:
            return res.data[0]
        new_user = {"telegram_id": telegram_id, "username": username or "Usuario",
                     "credits": 3, "is_vip": False}
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


def set_user_vip(telegram_id: int, is_vip: bool = True):
    """Se usará desde el webhook de confirmación de pago (ver sección 4)."""
    if supabase:
        try:
            supabase.table("users").update({"is_vip": is_vip}).eq("telegram_id", telegram_id).execute()
        except Exception as e:
            print(f"Error actualizando estatus VIP: {e}")


# ============================================================
# 1. GEMINI VISION: modelo versionado + fallback + API v1
# ============================================================

def analizar_lectura(prompt_text: str, image_pil=None) -> str:
    if not client_ai:
        return "El servicio de IA no está configurado (falta GEMINI_API_KEY)."

    system_instruction = (
        "Eres AstraVisión AI, una experta mística en Quiromancia (lectura de la palma de la mano) "
        "y Cafemancia (lectura del poso de café). "
        "Si recibes una imagen de una mano, analiza visualmente las líneas (Corazón, Cabeza, Vida, Destino) "
        "y montes. Si recibes una imagen de una taza de café, analiza las formas y patrones dejados por "
        "los residuos. Si recibes solo texto, responde desde la perspectiva mística de la quiromancia y "
        "cafemancia. Estructura tus lecturas con tono sabio, místico, inspirador y empático, usando "
        "emojis pertinentes."
    )

    contents = [prompt_text]
    if image_pil:
        contents.append(image_pil)

    ultimo_error = None
    for modelo in MODELOS_VISION_FALLBACK:
        try:
            response = client_ai.models.generate_content(
                model=modelo,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                ),
            )
            return response.text
        except Exception as e:
            ultimo_error = e
            print(f"Modelo '{modelo}' falló, probando el siguiente. Detalle: {e}")
            continue

    print(f"Error en Gemini API (todos los modelos fallaron): {ultimo_error}")
    return f"Ocurrió un detalle místico al leer la imagen: {ultimo_error}"


# ============================================================
# HANDLERS DE TELEGRAM
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)
    msg = (
        f"🖐️☕ **¡Bienvenido a AstraVisión AI, {user.first_name}!**\n\n"
        f"Especialista mística en **Quiromancia** (Lectura de Mano) y **Cafemancia** (Lectura de Café).\n"
        f"Tienes **{db_user.get('credits', 0)} lecturas gratuitas** disponibles.\n\n"
        f"📸 **Envía una foto clara de tu palma o de tu taza de café** junto a tu pregunta en el "
        f"comentario (ej: *'¿Cómo me ves en el amor?'*)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)

    credits = db_user.get("credits", 0)
    is_vip = db_user.get("is_vip", False)

    if not is_vip and credits <= 0:
        await update.message.reply_text(
            "🔒 Has agotado tus lecturas gratuitas. Adquiere acceso ilimitado en nuestra web para continuar."
        )
        return

    waiting_msg = await update.message.reply_text(
        "🔮 *Analizando los trazos místicos y revelando el destino...*", parse_mode="Markdown"
    )

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

        # analizar_lectura es una llamada de red síncrona (bloqueante). La
        # sacamos del hilo del event loop para no congelar el procesamiento
        # de otros updates mientras Gemini responde.
        respuesta = await asyncio.to_thread(analizar_lectura, prompt_text, image_pil)

        if not is_vip:
            update_user_credits(user.id, credits - 1)

        await waiting_msg.edit_text(respuesta)

    except Exception as e:
        print(f"Error procesando mensaje/foto: {e}")
        await waiting_msg.edit_text(f"⚠️ Ocurrió una interrupción al procesar la imagen: {str(e)}")


if telegram_app:
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, handle_message))


# ============================================================
# 2. EVENT LOOP PERSISTENTE (corrige "Event loop is closed")
# ============================================================
# En vez de crear y destruir un event loop nuevo con asyncio.run() en cada
# webhook (lo cual rompe los clientes HTTP internos de python-telegram-bot,
# que quedan atados al loop en el que fueron creados), se crea UN SOLO loop
# de fondo al arrancar la app, y cada update se agenda ahí con
# run_coroutine_threadsafe. Flask sigue siendo síncrono y responde de
# inmediato a Telegram.

_bg_loop = asyncio.new_event_loop()


def _run_bg_loop():
    asyncio.set_event_loop(_bg_loop)
    _bg_loop.run_forever()


_bg_thread = threading.Thread(target=_run_bg_loop, daemon=True)
_bg_thread.start()


def _init_telegram_app():
    async def _init():
        await telegram_app.initialize()
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        print(f"🤖 Webhook registrado exitosamente en: {WEBHOOK_URL}")

    fut = asyncio.run_coroutine_threadsafe(_init(), _bg_loop)
    fut.result(timeout=30)


if telegram_app:
    _init_telegram_app()


# ============================================================
# RUTAS FLASK
# ============================================================

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"status": "online", "service": "AstraVision Quiromancia y Cafemancia"}), 200


@app.route(f'/telegram/<token>', methods=['POST'])
def telegram_webhook(token):
    if token != TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)

    # Se agenda en el loop persistente en vez de crear uno nuevo por request.
    asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), _bg_loop)

    return jsonify({"status": "ok"}), 200


# ============================================================
# 3. ENDPOINT DE PAGOS — NOWPayments (creación de invoice)
# ============================================================

@app.route('/create_payment', methods=['POST'])
def create_payment():
    if not NOWPAYMENTS_API_KEY:
        return jsonify({"error": "NOWPayments no configurado"}), 500

    body = request.get_json(silent=True) or {}
    telegram_id = body.get("telegram_id")  # opcional: para asociar el pago a un usuario

    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "price_amount": 1.00,
        "price_currency": "usd",
        "order_description": "Acceso Ilimitado AstraVisión AI",
        "success_url": "https://rg-creator-dev.github.io/astravision-ai/?status=success",
        "cancel_url": "https://rg-creator-dev.github.io/astravision-ai/?status=cancel",
        "ipn_callback_url": "https://astravision-ai.onrender.com/payment_webhook",
    }
    if telegram_id:
        # order_id permite recuperar a qué usuario corresponde el pago
        # cuando llegue la confirmación por IPN.
        payload["order_id"] = str(telegram_id)

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        return jsonify({"invoice_url": data.get("invoice_url")}), 200
    except requests.exceptions.RequestException as e:
        print(f"Error creando invoice en NOWPayments: {e}")
        return jsonify({"error": "No se pudo crear el pago"}), 502


# ============================================================
# 4. WEBHOOK DE CONFIRMACIÓN (IPN) — necesario para activar el VIP
# ============================================================
# create_payment SOLO genera el link de cobro. Sin este webhook, el usuario
# puede pagar y jamás recibir el acceso ilimitado, porque nadie le avisa al
# backend que el pago se completó. NOWPayments llama a esta ruta cuando el
# estado del pago cambia (ej. a "finished").

import hmac
import hashlib
import json


def _verificar_firma_ipn(raw_body: bytes, signature_header: str) -> bool:
    if not NOWPAYMENTS_IPN_SECRET or not signature_header:
        return False
    # NOWPayments firma el JSON con las claves ordenadas alfabéticamente
    payload = json.loads(raw_body)
    ordenado = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    firma_calculada = hmac.new(
        NOWPAYMENTS_IPN_SECRET.encode(), ordenado.encode(), hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(firma_calculada, signature_header)


@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    signature = request.headers.get("x-nowpayments-sig", "")
    raw_body = request.get_data()

    if not _verificar_firma_ipn(raw_body, signature):
        return jsonify({"error": "Firma inválida"}), 403

    data = request.get_json(force=True)
    estado = data.get("payment_status")
    order_id = data.get("order_id")  # telegram_id que enviamos en create_payment

    if estado == "finished" and order_id:
        try:
            set_user_vip(int(order_id), True)
            print(f"✅ Usuario {order_id} activado como VIP tras pago confirmado.")
        except ValueError:
            print(f"order_id inválido recibido en IPN: {order_id}")

    return jsonify({"status": "received"}), 200


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
