from twilio.rest import Client
from flask import Flask, request, jsonify
import requests
import os
import pandas as pd
import numpy as np
import joblib
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from datetime import datetime, timezone, timedelta
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse
import openrouteservice

# ========================
# 🔁 FUNCIONES AUXILIARES
# ========================
def extraer_variables(df):
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hora'] = df['timestamp'].dt.hour + df['timestamp'].dt.minute / 60
    df['dia_semana'] = df['timestamp'].dt.weekday
    df['evento'] = df['evento'].fillna('sin_evento').astype(str).str.lower()
    df['zona'] = df['zona'].fillna('sin_zona').astype(str).str.lower()
    df['latitud'] = df['latitud'].astype(str).str.replace(',', '.').astype(float)
    df['longitud'] = df['longitud'].astype(str).str.replace(',', '.').astype(float)
    return df

# ========================
# 🚀 CARGA DE MODELOS
# ========================
modelo_general = joblib.load("modelo_general.joblib")
transformer_general = joblib.load("transformer_general.joblib")
modelo_horario = joblib.load("modelo_horario.joblib")
scaler_horario = joblib.load("scaler_horario.joblib")

# ========================
# 🌎 CONFIG SERVIDOR
# ========================
ARGENTINA_TZ = timezone(timedelta(hours=-3))

geolocator = Nominatim(user_agent="mi-app-coordenadas")  # podés personalizar el nombre
reverse = RateLimiter(geolocator.reverse, min_delay_seconds=1)

# Variables de entorno o directas
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")  # número de Twilio
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")  # tu número para recibir alertas
TWILIO_FROM_NUMBER_LLAMADA=os.getenv("TWILIO_FROM_NUMBER_LLAMADA")   # número de Twilio con voz
NUMERO_TELEFONO_DESTINO_LLAMADA=os.getenv("NUMERO_TELEFONO_DESTINO_LLAMADA")


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://project-ifts.netlify.app"}})

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")



def obtener_direccion(lat, lon):
    try:
        location = reverse((lat, lon), language='es')
        return location.address if location else "Dirección no encontrada"
    except Exception as e:
        print("⚠️ Error al obtener dirección:", str(e))
        return "Error al obtener dirección"
    

def obtener_ubicaciones_por_dia(dia_semana_nombre):
    """
    Consulta Supabase para obtener las ubicaciones filtrando por día de la semana
    dia_semana_nombre: nombre del día en inglés con inicial mayúscula, ej: 'Monday'
    """
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # Traer datos (puede ser mucho, luego optimizar paginación)
    url = f"{SUPABASE_URL}/rest/v1/ubicaciones?select=latitud,longitud,timestamp,direccion&order=timestamp.asc"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return None, f"Error al obtener datos: {response.status_code}"

    datos = response.json()
    if not datos:
        return None, "No hay datos"

    # Convertir a DataFrame
    df = pd.DataFrame(datos)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['dia_semana'] = df['timestamp'].dt.day_name()

    # Filtrar por día pedido
    df_filtrado = df[df['dia_semana'] == dia_semana_nombre]

    # Filtrar coordenadas válidas (limpio)
    df_filtrado = df_filtrado[
        (df_filtrado['latitud'] < 0) & (df_filtrado['latitud'] > -60) &
        (df_filtrado['longitud'] < -50) & (df_filtrado['longitud'] > -70)
    ]

    if df_filtrado.empty:
        return None, "No hay datos para ese día"

    # Ordenar por timestamp
    df_filtrado = df_filtrado.sort_values('timestamp')

    # Extraer lista de coordenadas para ORS
    coords = df_filtrado[['longitud', 'latitud']].values.tolist()

    # Reducir puntos si hay muchos
    if len(coords) > 50:
        coords = coords[::5]

    return coords, None


@app.route('/')
def home():
    return "✅ Servidor Flask funcionando correctamente", 200

@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        print("📥 Datos recibidos:", data)

        # Extraer datos esperados del formato manual
        lat = data.get("latitud")
        lon = data.get("longitud")
        timestamp_str = data.get("timestamp")
        evento = data.get("evento", None)
        zona = data.get("zona", None)
        device_id = data.get("device", "sin_tid")

        # Parsear fecha
        fecha = (
            datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            if timestamp_str else None
        )
        fecha_str = fecha.strftime("%Y-%m-%d %H:%M:%S") if fecha else None

        # Armar payload
        payload = {
            "latitud": lat,
            "longitud": lon,
            "evento": evento,
            "zona": zona,
            "timestamp": fecha_str,
            "device": device_id
        }

        # 🆕 Agregar dirección al payload
        try:
            payload["direccion"] = obtener_direccion(float(lat), float(lon))
        except Exception as e:
            print("⚠️ Error al obtener dirección:", str(e))
            payload["direccion"] = "No disponible"

        try:
            # Preparar dataframe para predicción
            dato = {
                "latitud": lat,
                "longitud": lon,
                "evento": evento,
                "zona": zona,
                "timestamp": fecha_str
            }
            df = pd.DataFrame([dato])
            df_proc = extraer_variables(df)

            # Predicción general
            X_general = transformer_general.transform(df_proc)
            pred_general = modelo_general.predict(X_general)[0]

            # Predicción horaria
            X_hora = scaler_horario.transform(df_proc[["hora"]])
            pred_hora = modelo_horario.predict(X_hora)[0]

            # Resultado combinado
            es_anomalo = 1 if pred_general == -1 or pred_hora == -1 else 0
            payload["es_anomalo"] = es_anomalo
            print(f"🔎 General: {pred_general}, Horario: {pred_hora} → Final: {'ANOMALÍA' if es_anomalo else 'Normal'}")

            if es_anomalo == 1:
                try:
                    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
                    mensaje_alerta = f"🚨 ALERTA: Anomalía detectada\n" \
                                      f"🕒 Fecha y hora: {fecha_str}\n" \
                                      f"https://www.google.com/maps?q={lat},{lon}" \
                                      f"¿Confirmás que es una anomalía?\n" \
                                      f"Respondé *SI* para activar el protocolo de seguridad o *NO* para ignorar."
                    sms = client.messages.create(
                        body=mensaje_alerta,
                        from_=TWILIO_FROM_NUMBER,
                        to=TWILIO_TO_NUMBER
                    )
                    print(f"📤 SMS enviado: SID {sms.sid}")
                except Exception as sms_error:
                   print("❌ Error al enviar SMS:", str(sms_error))


        except Exception as e:
            print("⚠️ Error en predicción:", str(e))
            payload["es_anomalo"] = None

        # Enviar a Supabase
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/ubicaciones",
                json=payload,
                headers=headers
            )
            print("✅ Supabase:", resp.status_code, resp.json())
        except Exception as e:
            print("❌ Error al guardar en Supabase:", str(e))

        return jsonify({"status": "ok", "anomalo": payload.get("es_anomalo")})

    except Exception as e:
        print("❌ Error general:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/ultima_ubicacion', methods=['GET'])
def obtener_ultima_ubicacion():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # Ordenar por fecha más reciente
    # url = f"{SUPABASE_URL}/rest/v1/ubicaciones?order=timestamp.desc&limit=1"
    url = f"{SUPABASE_URL}/rest/v1/ubicaciones?order=id.desc&limit=1"

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({
                "error": "No se pudo obtener la ubicación",
                "detalle": response.text
            }), response.status_code

        datos = response.json()
        if not datos:
            return jsonify({"mensaje": "No hay ubicaciones registradas"}), 404

        ultima = datos[0]
        print("📍 Última ubicación registrada:", ultima)

         #🆕 Convertir latitud y longitud a dirección
        try:
            lat = float(ultima.get("latitud"))
            lon = float(ultima.get("longitud"))
            direccion = obtener_direccion(lat, lon)
            ultima["direccion"] = direccion
        except Exception as e:
            print("⚠️ No se pudo obtener dirección:", str(e))
            ultima["direccion"] = "No disponible"

        return jsonify(ultima), 200

    except Exception as e:
        print("❌ Error al consultar Supabase:", str(e))
        return jsonify({"error": "Error interno"}), 500

@app.route('/responder_alerta', methods=['POST'])
def responder_alerta():
    try:
        mensaje = request.form.get('Body', '').strip().lower()
        numero = request.form.get('From')
        print(f"📨 Respuesta recibida de {numero}: {mensaje}")

        respuesta = MessagingResponse()

        if mensaje in ['si', 'sí']:
            # Aquí podrías activar algo más, como guardar en Supabase o activar un protocolo
            respuesta.message("✅ Protocolo de seguridad ACTIVADO. Gracias por confirmar.")
            print("🚨 Se activó el protocolo de seguridad.")

               # 👉 Iniciar llamada automática
            client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

            llamada = client.calls.create(
                # Podés usar esto directamente con TwiML embebido...
                twiml='<Response><Say voice="alice" language="es-ES">Se ha detectado un movimiento inusual en la zona. Estamos dando aviso a la comisaría más cercana.</Say></Response>',
                
                # ... o bien redirigir a una URL externa que devuelva TwiML (opcional)
                # url="https://tu-app.herokuapp.com/voz_alerta",

                from_=TWILIO_FROM_NUMBER_LLAMADA,   # número de Twilio con voz
                to=NUMERO_TELEFONO_DESTINO_LLAMADA          # a quién llamar (tutor/responsable)
            )
            print(f"📞 Llamada iniciada. SID: {llamada.sid}")
        elif mensaje == 'no':
            respuesta.message("❎ Anomalía descartada. Gracias por tu respuesta.")
            print("ℹ️ Anomalía descartada por el tutor.")
        else:
            respuesta.message("❓ Respuesta no entendida. Por favor respondé con 'SI' o 'NO'.")
            print("⚠️ Respuesta inválida.")

        return str(respuesta)

    except Exception as e:
        print("❌ Error procesando respuesta:", str(e))
        return "Error", 500
    
@app.route('/ruta/<dia>', methods=['GET'])
def ruta_dia(dia):
    dias_validos = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']

    dia = dia.lower()
    if dia not in dias_validos:
        return jsonify({"error": "Día inválido, usar monday a friday"}), 400

    # Convertir a formato con mayúscula inicial para comparar
    dia_nombre = dia.capitalize()

    # Obtener coordenadas filtradas
    coordenadas, error = obtener_ubicaciones_por_dia(dia_nombre)
    if error:
        return jsonify({"error": error}), 404

    # Instanciar cliente ORS
    API_KEY = os.getenv("ORS_API_KEY")  # asegurate que esté en variables de entorno
    client = openrouteservice.Client(key=API_KEY)

    try:
        ruta = client.directions(
            coordinates=coordenadas,
            profile='foot-walking',
            format='geojson'
        )
    except openrouteservice.exceptions.ApiError as e:
        return jsonify({"error": f"Error ORS: {str(e)}"}), 500

    return jsonify(ruta)
