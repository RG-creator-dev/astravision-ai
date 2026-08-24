# -*- coding: utf-8 -*-
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('astravision')

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def obtener_o_crear_usuario(telegram_id: int):
    res = supabase.table("users").select("*").eq("telegram_id", telegram_id).execute()
    if res.data:
        return res.data[0]
    
    nuevo_usuario = {
        "telegram_id": telegram_id,
        "credits": 3,
        "is_premium": False
    }
    insert_res = supabase.table("users").insert(nuevo_usuario).execute()
    return insert_res.data[0]

def descontar_credito(telegram_id: int, creditos_actuales: int):
    nuevos_creditos = max(0, creditos_actuales - 1)
    supabase.table("users").update({"credits": nuevos_creditos}).eq("telegram_id", telegram_id).execute()

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = obtener_o_crear_usuario(user.id)
    creditos = "Ilimitados (Premium)" if db_user["is_premium"] else db_user["credits"]
    
    await update.message.reply_text(
        f"✨ *Bienvenido a Astravisión AI*, {user.first_name}!\n\n"
        f"🔮 Envía una foto clara de la *palma de tu mano* (Quiromancia) o de los *posos de tu taza de café* (Cafemancia).\n\n"
        f"📊 *Tus créditos disponibles:* {creditos}\n\n"
        f"Usa /creditos para consultar tu saldo en cualquier momento.",
        parse_mode="Markdown"
    )

async def creditos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = obtener_o_crear_usuario(user.id)
    creditos = "Ilimitados (Premium)" if db_user["is_premium"] else db_user["credits"]
    
    await update.message.reply_text(
        f"📊 *Estado de tu Cuenta - Astravisión*\n\n"
        f"👤 ID: {user.id}\n"
        f"🔮 Créditos disponibles: *{creditos}*\n\n"
        f"Si tus créditos se agotan, pronto podrás adquirir paquetes directamente desde nuestra web.",
        parse_mode="Markdown"
    )

async def imagen_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    db_user = obtener_o_crear_usuario(telegram_id)
    
    if not db_user["is_premium"] and db_user["credits"] <= 0:
        await update.message.reply_text(
            "🔮 *Has agotado tus lecturas gratuitas.*\n\n"
            "Pronto podrás adquirir más créditos o activar el plan Premium para consultas ilimitadas.",
            parse_mode="Markdown"
        )
        return

    msg_espera = await update.message.reply_text("✨ *Conectando con los astros y analizando la imagen...*", parse_mode="Markdown")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()
        
        prompt = (
            "Eres Astravisión AI, un místico experto en quiromancia y cafemancia. "
            "Examina detalladamente la imagen adjunta. Si es una mano, interpreta sus líneas principales y montes. "
            "Si es una taza de café, interpreta los símbolos y patrones formados por los residuos. "
            "Ofrece una lectura mística, esperanzadora, constructiva y estructurada con emoticonos astrológicos."
        )
        
        image_part = {"mime_type": "image/jpeg", "data": bytes(image_bytes)}
        response = model.generate_content([prompt, image_part])
        
        if not db_user["is_premium"]:
            descontar_credito(telegram_id, db_user["credits"])
            
        await msg_espera.delete()
        await update.message.reply_text(response.text, parse_mode="Markdown")
        
    except Exception as e:
        log.error(f"Error procesando imagen: {e}")
        await msg_espera.edit_text("❌ Ocurrió un error al interpretar la imagen. Por favor, intenta de nuevo con una foto más clara.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("creditos", creditos_handler))
    app.add_handler(MessageHandler(filters.PHOTO, imagen_handler))
    
    log.info("Iniciando Bot Astravisión...")
    app.run_polling()

if __name__ == '__main__':
    main()
