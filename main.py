import os
import asyncio
import hmac
import hashlib
import json
import requests
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
from google import genai

# ==========================================
# 1. CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")

# Inicialización de clientes
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = Flask(__name__)

# ==========================================
# 2. FUNCIONES DE BASE DE DATOS (SUPABASE)
# ==========================================
def get_or_create_user(telegram_id: int, username: str):
    """Consulta o registra a un usuario en Supabase asignándole lecturas iniciales."""
    if not supabase:
        return {"credits": 3, "is_vip": False}
    try:
        res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
        if res.data:
            return res.data[0]
        else:
            new_user = {
                "telegram_id": telegram_id,
                "username": username or "Usuario",
                "credits": 3,
                "is_vip": False
            }
            inserted = supabase.table("users").insert(new_user).execute()
            return inserted.data[0]
    except Exception as e:
        print(f"Error en Supabase: {e}")
        return {"credits": 3, "is_vip": False}

def update_user_credits(telegram_id: int, new_credits: int):
    """Actualiza la cantidad de créditos de un usuario."""
    if supabase:
        try:
            supabase.table("users").update({"credits": new_credits}).eq("telegram_id", telegram_id).execute()
        except Exception as e:
            print(f"Error al actualizar créditos: {e}")

# ==========================================
# 3. LÓGICA DE GEMINI (INTELIGENCIA ARTIFICIAL)
# ==========================================
def generar_respuesta_astrologica(prompt_usuario: str) -> str:
    """Envía la consulta del usuario a la API de Gemini con rol de astrólogo profesional."""
    if not gemini_client:
        return "El servicio de Inteligencia Artificial no está configurado actualmente."
    
    system_instruction = (
        "Eres AstraVisión AI, una astróloga mística, empática, seria y profesional. "
        "Respondes preguntas sobre carta astral, tránsito planetario, horóscopo y compatibilidad. "
        "Tus respuestas son elegantes, claras y estructuradas con emojis relacionados con el cosmos."
    )
    
    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt_usuario,
            config={'system_instruction': system_instruction}
        )
        return response.text
    except Exception as e:
        print(f"Error en Gemini API: {e}")
        return "Lo siento, las energías cósmicas están turbias en este momento (Error de procesamiento). Inténtalo más tarde."

# ==========================================
# 4. COMANDOS Y EVENTOS DE TELEGRAM
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)
    
    msg = (
        f"✨ **¡Bienvenido a AstraVisión AI, {user.first_name}!** ✨\n\n"
        f"Soy tu guía astrológica impulsada por inteligencia artificial.\n"
        f"Tienes **{db_user.get('credits', 0)} lecturas disponibles**.\n\n"
        f"🔮 Escribe tu consulta (ejemplo: *'¿Qué energías me depara el tránsito de Saturno en mi signo?'* o tu fecha y hora de nacimiento)."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_text = update.message.text
    db_user = get_or_create_user(user.id, user.username)
    
    credits = db_user.get("credits", 0)
    is_vip = db_user.get("is_vip", False)
    
    if not is_vip and credits <= 0:
        await update.message.reply_text(
            "🔒 **Has agotado tus lecturas gratuitas.**\n\n"
            "Para continuar consultando, adquiere un paquete de lecturas desde nuestra web o solicita un enlace de pago.",
            parse_mode="Markdown"
        )
        return

    # Mensaje de espera mientras Gemini genera la respuesta
    waiting_msg = await update.message.reply_text("🔮 *Consultando la alineación de las estrellas...*", parse_mode="Markdown")
    
    # Respuesta de IA
    respuesta = generar_respuesta_astrologica(user_text)
    
    # Descontar crédito si no es VIP
    if not is_vip:
        update_user_credits(user.id, credits - 1)
    
    await waiting_msg.edit_text(respuesta)

# ==========================================
# 5. ENDPOINTS WEB Y PASARELA NOWPAYMENTS (FLASK)
# ==========================================
@app.route('/', methods=['GET'])
def health_check():
    """Ruta para mantener activo el servidor en Render."""
    return jsonify({
        "status": "online",
        "service": "AstraVision AI Full Service"
    }), 200

@app.route('/create-payment-web', methods=['POST'])
def create_payment_web():
    """Ruta invocada por el botón de pago en la landing page HTML."""
    if not NOWPAYMENTS_API_KEY:
        return jsonify({"error": "NOWPAYMENTS_API_KEY no configurada"}), 500

    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "price_amount": 2.0,  # $2.00 USD
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "ipn_callback_url": "https://astravision-ai.onrender.com/webhook/nowpayments",
        "order_description": "Acceso Ilimitado AstraVisión AI",
        "success_url": "https://rg-creator-dev.github.io/astravision-ai/?status=success",
        "cancel_url": "https://rg-creator-dev.github.io/astravision-ai/?status=cancel"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        res_data = response.json()
        if response.status_code in [200, 201]:
            return jsonify({"invoice_url": res_data.get("invoice_url")}), 200
        return jsonify({"error": "No se pudo generar la factura", "details": res_data}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/webhook/nowpayments', methods=['POST'])
def nowpayments_webhook():
    """Recibe y verifica la confirmación automática de NOWPayments con IPN Secret."""
    request_data = request.get_data()
    received_sig = request.headers.get('x-nowpayments-sig')

    # Verificación de seguridad mediante Firma IPN (si está configurada)
    if NOWPAYMENTS_IPN_SECRET and received_sig:
        try:
            data_dict = json.loads(request_data)
            sorted_data = json.dumps(data_dict, sort_keys=True, separators=(',', ':'))
            h = hmac.new(NOWPAYMENTS_IPN_SECRET.encode('utf-8'), sorted_data.encode('utf-8'), hashlib.sha512)
            calculated_sig = h.hexdigest()
            
            if calculated_sig != received_sig:
                print("⚠️ Firma IPN no válida recibida en Webhook.")
                return jsonify({"error": "Invalid signature"}), 400
        except Exception as e:
            print(f"Error verificando firma IPN: {e}")

    data = request.get_json() or {}
    payment_status = data.get('payment_status')
    
    if payment_status == 'finished':
        pay_amount = data.get('price_amount')
        order_id = data.get('order_id', 'N/A')
        print(f"✅ ¡Pago verificado en NOWPayments! Orden: {order_id} por ${pay_amount} USD")
        
    return jsonify({"status": "received"}), 200

# ==========================================
# 6. INICIALIZACIÓN Y ARRANQUE DEL BOT
# ==========================================
def setup_telegram_bot():
    """Configura la aplicación del Bot de Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ No se detectó TELEGRAM_BOT_TOKEN. El bot no se iniciará.")
        return None
    
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return telegram_app

if __name__ == '__main__':
    # Iniciar bot de Telegram en segundo plano
    bot_app = setup_telegram_bot()
    if bot_app:
        loop = asyncio.get_event_loop()
        loop.create_task(bot_app.initialize())
        loop.create_task(bot_app.start())
        loop.create_task(bot_app.updater.start_polling())
        print("🤖 Bot de Telegram iniciado correctamente.")

    # Iniciar servidor Flask en el puerto asignado por Render
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
