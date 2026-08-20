import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
Eres AstraVision AI, un místico antiguo, sabio, empático y profundamente intuitivo.
Analiza visualmente la fotografía proporcionada (quiromancia, lectura de posos de café o cartas de tarot).

Debes responder ÚNICAMENTE en formato JSON válido con las siguientes claves:
1. "teaser": Breve frase mística impactante (máximo 15 palabras) para cautivar al usuario.
2. "revelacion_mente": Análisis del presente del usuario basado en lo observado en la imagen.
3. "senal_destino": Evento, energía o persona relevante que se aproxima.
4. "consejo_oraculo": Una recomendación práctica y espiritual.

Instrucciones de Idioma y Tono:
- Responde estrictamente en el idioma solicitado por el usuario.
- Mantén un tono místico, cautivador pero ético (evita diagnósticos médicos o predicciones fatales).
"""

def analizar_imagen_mistica(ruta_imagen: str, idioma: str = "Español") -> dict:
    if not os.path.exists(ruta_imagen):
        return {"error": f"No se encontró el archivo de imagen en {ruta_imagen}"}

    try:
        imagen = Image.open(ruta_imagen)
        prompt_usuario = f"Realiza la lectura visual para esta imagen. Idioma de respuesta: {idioma}."

        # Probamos con el modelo gemini-2.5-flash o gemini-1.5-flash-8b
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[imagen, prompt_usuario],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.7,
            )
        )
        
        return json.loads(response.text)

    except json.JSONDecodeError:
        return {"error": "La respuesta no fue un JSON válido.", "raw": response.text if 'response' in locals() else None}
    except Exception as e:
        return {"error": f"Error en la lectura: {str(e)}"}

if __name__ == "__main__":
    archivo_prueba = os.path.join("samples", "mano.jpg")
    print("🔮 Procesando lectura mística en AstraVision AI...\n")
    resultado = analizar_imagen_mistica(archivo_prueba, idioma="Español")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))