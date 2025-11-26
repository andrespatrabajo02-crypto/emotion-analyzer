import time
import re
import hashlib
import logging
import json  # Para parsear JSON de env var
from typing import List, Tuple
import os

# Dependencias externas (instala con: pip install gspread google-auth google-auth-oauthlib textblob deep-translator langdetect openai tenacity vaderSentiment)
import gspread
from google.oauth2.service_account import Credentials
from textblob import TextBlob
from deep_translator import GoogleTranslator
from langdetect import detect
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # Nueva: Para análisis más robusto

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================================
# 🔑 CONFIGURACIÓN
# ==========================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Setear en env: export OPENAI_API_KEY="tu-key"
if not OPENAI_API_KEY:
    raise ValueError("❌ Setear OPENAI_API_KEY en variables de entorno.")

client = OpenAI(api_key=OPENAI_API_KEY)

# Autenticación con Google Sheets (usa google-auth moderna)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
key_data = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')  # Multiline env var en Render
if not key_data:
    raise ValueError("❌ Setear GOOGLE_SERVICE_ACCOUNT_JSON en env vars.")
credentials_info = json.loads(key_data)
credentials = Credentials.from_service_account_info(credentials_info, scopes=scope)
client_sheet = gspread.authorize(credentials)
sheet = client_sheet.open("sheetspython").sheet1

# Configurables
CHECK_INTERVAL = 5  # Segundos entre checks
LOOP_TIMEOUT = 86400  # 24 horas max (en segundos)
CONECTOR_SPANISH = r'\b(pero|aunque|sin embargo|además|mientras|cuando|porque)\b'
CONECTOR_ENGLISH = r'\b(but|although|however|besides|while|when|because)\b'

PALABRAS_NEGATIVAS = {'miss', 'lonely', 'afraid', 'scared', 'worried', 'pain', 'hurt', 'sad', 'alone', 'anxious', 'nervous'}
PALABRAS_POSITIVAS = {'hope', 'better', 'grateful', 'thankful', 'happy', 'good', 'great', 'wonderful', 'improve', 'recovering'}
PALABRAS_FRUSTRACION = {'frustración', 'impaciencia', 'esperas', 'demora', 'lento', 'frustrating', 'impatient', 'waiting', 'delay', 'slow'}  # Específicas para contexto médico (es/en)

# Inicializar VADER
analyzer = SentimentIntensityAnalyzer()

# ==========================================================
# ✨ IA: CORREGIR ORTOGRAFÍA, COMAS Y GRAMÁTICA
# ==========================================================
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def corregir_texto(texto: str) -> str:
    try:
        prompt = (
            "Corrige ortografía, comas, puntuación y gramática del siguiente texto, "
            "sin cambiar su significado. Devuélvelo corregido:\n\n"
            f"{texto}"
        )

        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1  # Bajo para consistencia
        )
        return respuesta.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"⚠️ Error corrigiendo texto: {e}")
        return texto

# ==========================================================
# 📌 FUNCIONES DE ANÁLISIS EMOCIONAL
# ==========================================================
def detectar_idioma(texto: str) -> str:
    try:
        return detect(texto)
    except Exception:
        return "es"

def traducir_texto_completo(texto: str, destino: str = 'en') -> str:
    try:
        idioma_origen = detectar_idioma(texto)
        if idioma_origen != destino:
            return GoogleTranslator(source=idioma_origen, target=destino).translate(texto)
        return texto
    except Exception as e:
        logger.warning(f"⚠️ Error traduciendo: {e}")
        return texto

def dividir_texto(texto: str, idioma: str) -> List[str]:
    oraciones = re.split(r'[.!?]+', texto)
    frases_finales = []
    conectores = CONECTOR_SPANISH if idioma.startswith("es") else CONECTOR_ENGLISH

    for oracion in oraciones:
        oracion = oracion.strip()
        if not oracion:
            continue

        palabras = oracion.split()
        if len(palabras) <= 15:
            frases_finales.append(oracion)
            continue

        # Dividir por conectores
        sub_frases = re.split(conectores, oracion, flags=re.IGNORECASE)
        temp = ""
        for i, parte in enumerate(sub_frases):
            temp += parte + " "
            if i % 2 == 0 and len(temp.split()) >= 5:
                frases_finales.append(temp.strip())
                temp = ""
        if temp.strip():
            frases_finales.append(temp.strip())

    return frases_finales

def analizar_emocion(frase: str) -> Tuple[str, float, float, List[str]]:
    # VADER para compound y breakdown (más robusto a contrastes)
    vader_scores = analyzer.polarity_scores(frase)
    polaridad = vader_scores['compound']  # -1 (neg) a +1 (pos)
    
    # TextBlob para subjetividad
    blob = TextBlob(frase)
    subjetividad = blob.sentiment.subjectivity
    
    # Ajustes por palabras clave (más peso a frustración)
    frase_lower = frase.lower()
    for palabra in PALABRAS_NEGATIVAS:
        if palabra in frase_lower:
            polaridad -= 0.15
    for palabra in PALABRAS_POSITIVAS:
        if palabra in frase_lower:
            polaridad += 0.10
    emociones_multi = []
    for pal in PALABRAS_FRUSTRACION:
        if pal in frase_lower:
            polaridad -= 0.20
            emociones_multi.append('Frustración 😠')
    
    # Clasificación principal (umbral más sensible para mixtos)
    if polaridad >= 0.3:
        emocion_principal = "Alegría 😄"
    elif 0.05 <= polaridad < 0.3:
        emocion_principal = "Tranquilidad 🙂"
    elif -0.05 < polaridad < 0.05:
        emocion_principal = "Neutral 😐"
    elif -0.3 <= polaridad <= -0.05:
        emocion_principal = "Tristeza 😔"
    else:
        emocion_principal = "Enojo 😡"
    
    # Agrega multi si aplica
    if emociones_multi:
        emocion_final = f"{emocion_principal} + {', '.join(emociones_multi)}"
    else:
        emocion_final = emocion_principal
    
    return emocion_final, round(polaridad, 2), round(subjetividad, 2), emociones_multi

def analizar_texto_completo(texto: str) -> str:
    idioma = detectar_idioma(texto)
    texto_traducido = traducir_texto_completo(texto)  # Traducir una sola vez
    frases = dividir_texto(texto_traducido, idioma)  # Dividir después de traducir

    resultados = []
    oraciones_original = re.split(r'[.!?]+', texto)
    for idx, frase in enumerate(frases):
        emocion, polaridad, subjetividad, multi = analizar_emocion(frase)
        # Mapear a frase original (mejorado para evitar index errors)
        frase_original = oraciones_original[idx % len(oraciones_original)].strip() if oraciones_original else frase
        resultados.append(f"'{frase_original}' → {emocion} (pol: {polaridad}, subj: {subjetividad})")

    return "\n".join(resultados)

# ==========================================================
# 🔄 MONITOREO PRINCIPAL
# ==========================================================
def hash_texto(texto: str) -> str:
    return hashlib.md5(texto.encode()).hexdigest() if texto else ""

logger.info("📡 Monitoreando Google Sheet en la nube...")

valor_anterior_hash = ""
start_time = time.time()

while (time.time() - start_time) < LOOP_TIMEOUT:
    try:
        texto = sheet.acell('A3').value
        hash_actual = hash_texto(texto)

        if texto and hash_actual != valor_anterior_hash:
            logger.info(f"🆕 Cambio detectado: {texto[:50]}...")

            # Corregir con IA
            texto_corregido = corregir_texto(texto)
            sheet.update_acell('A4', f"Corregido: {texto_corregido}")

            # Análisis emocional
            resultados = analizar_texto_completo(texto_corregido)
            sheet.update_acell('B3', resultados)

            logger.info(f"✏️ Corregido: {texto_corregido[:50]}...")
            logger.info("🧠 Emociones:\n" + resultados)

            valor_anterior_hash = hash_actual

    except gspread.exceptions.APIError as e:
        logger.error(f"❌ Error de API Google Sheets: {e}. Reintentando...")
    except Exception as e:
        logger.error(f"❌ Error general: {e}")

    time.sleep(CHECK_INTERVAL)

logger.info("⏰ Timeout alcanzado. Script finalizado.")
