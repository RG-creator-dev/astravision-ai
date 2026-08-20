import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from test_vision import analizar_imagen_mistica

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI(title="AstraVision AI Webhook")

def enviar_mensaje_telegram(chat_id: int, texto: str):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def obtener_ruta_imagen_telegram(file_id: str) -> str:
    # 1. Obtener la ruta del archivo en los servidores de Telegram
    res = requests.get(f"{TELEGRAM_API_URL}/getFile", params={"file_id": file_id}).json()
    file_path = res["result"]["file_path"]
    
    # 2. Descargar la imagen
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    img_data = requests.get(download_url).content
    
    # 3. Guardar localmente en samples
    local_path = os.path.join("samples", f"{file_id}.jpg")
    with open(local_path, "wb") as f:
        f.write(img_data)
        
    return local_path

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        
        # Caso 1: El usuario envía una foto
        if "photo" in data["message"]:
            enviar_mensaje_telegram(chat_id, "🔮 *AstraVision AI está canalizando la lectura de tu imagen...*")
            
            # Telegram envía varias resoluciones; tomamos la de mayor calidad (la última)
            foto_mas_grande = data["message"]["photo"][-1]
            file_id = foto_mas_grande["file_id"]
            
            # Obtener idioma del usuario de Telegram
            idioma_usuario = data["message"]["from"].get("language_code", "es")
            idioma_nombre = "Español" if idioma_usuario.startswith("es") else "English"
            
            try:
                ruta_local = obtener_ruta_imagen_telegram(file_id)
                resultado = analizar_imagen_mistica(ruta_local, idioma=idioma_nombre)
                
                # Formatear respuesta al usuario
                if "error" in resultado:
                    enviar_mensaje_telegram(chat_id, f"⚠️ Error: {resultado['error']}")
                else:
                    respuesta = (
                        f"✨ *{resultado.get('teaser', '')}*\n\n"
                        f"🔮 *Revelación de la Mente:*\n{resultado.get('revelacion_mente', '')}\n\n"
                        f"💫 *Señal del Destino:*\n{resultado.get('senal_destino', '')}\n\n"
                        f"📜 *Consejo del Oráculo:*\n{resultado.get('consejo_oraculo', '')}"
                    )
                    enviar_mensaje_telegram(chat_id, respuesta)
                    
                # Limpiar archivo temporal
                if os.path.exists(ruta_local):
                    os.remove(ruta_local)
                    
            except Exception as e:
                enviar_mensaje_telegram(chat_id, f"⚠️ Ocurrió un fallo en el procesamiento: {str(e)}")
                
        # Caso 2: El usuario envía texto
        elif "text" in data["message"]:
            enviar_mensaje_telegram(
                chat_id, 
                "👋 ¡Bienvenido a *AstraVision AI*!\n\nEnvíame una fotografía clara de la palma de tu mano, tus posos de café o cartas de tarot para revelarte tu lectura visual."
            )

    return {"status": "ok"}