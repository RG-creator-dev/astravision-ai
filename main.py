import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from supabase import create_client, Client

# 1. Cargar variables de entorno desde Render (100% seguro)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET")

# Inicializar cliente de Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. Función para crear orden de pago en NOWPayments
def crear_pago_nowpayments(user_id: int, monto_usd: float = 2.0):
    url = "https://api.nowpayments.io/v1/invoice"
    headers = {
        "x-api-key": NOWPAYMENTS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "price_amount": monto_usd,
        "price_currency": "usd",
        "pay_currency": "usdttrc20",
        "ipn_callback_url": f"https://astravision-ai.onrender.com/webhook/nowpayments",  # Ajusta a tu URL de Render
        "order_id": f"READING-{user_id}",
        "order_description": "Paquete de Lecturas Ilimitadas AstraVisión AI"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            data = response.json()
            return data.get("invoice_url")
        else:
            print(f"Error NOWPayments: {response.text}")
            return None
    except Exception as e:
        print(f"Excepción al conectar con NOWPayments: {e}")
        return None

# 3. Manejador de comando /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Consultar o registrar usuario en Supabase
    res = supabase.table("users").select("*").eq("telegram_id", user_id).execute()
    
    if not res.data:
        # Registrar usuario nuevo con 3 lecturas gratuitas
        supabase.table("users").insert({
            "telegram_id": user_id,
            "readings_left": 3
        }).execute()
        readings = 3
    else:
        readings = res.data[0]["readings_left"]
        
    await update.message.reply_text(
        f"✨ ¡Bienvenido a AstraVisión AI!\n\n"
        f"Tienes actualmente **{readings} lecturas gratuitas** disponibles.\n"
        f"Envía una foto de tu mano o tu taza de café para iniciar."
    )

# 4. Manejador para solicitar recarga de lecturas
async def comprar_lecturas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    invoice_url = crear_pago_nowpayments(user_id, monto_usd=2.0)

    if invoice_url:
        keyboard = [[InlineKeyboardButton("💳 Pagar $2.00 USDT (TRC20)", url=invoice_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Has agotado tus lecturas gratuitas.\n\n"
            "Haz clic abajo para adquirir lecturas adicionales con USDT (TRC20) mediante Binance / NOWPayments:",
            reply_markup=reply_markup
        )
    else:
        await query.edit_message_text("Hubo un detalle al generar el enlace de pago. Por favor intenta más tarde.")

# 5. Inicialización del Bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(comprar_lecturas, pattern="^comprar$"))
    
    print("Bot AstraVisión AI en marcha...")
    app.run_polling()
