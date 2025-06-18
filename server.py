from twilio.rest import Client
from flask import Flask, request, jsonify
import requests
import os
import pandas as pd
import numpy as np
import joblib
from datetime import datetime, timezone, timedelta
from flask_cors import CORS
from twilio.twiml.messaging_response import MessagingResponse

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

# Variables de entorno o directas
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")  # número de Twilio
TWILIO_TO_NUMBER = os.getenv("TWILIO_TO_NUMBER")  # tu número para recibir alertas

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://project-ifts.netlify.app"}})

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

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
                                      f"📍 Latitud: {lat}\n" \
                                      f"📍 Longitud: {lon}"\
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
        return jsonify(ultima), 200

    except Exception as e:
        print("❌ Error al consultar Supabase:", str(e))
        return jsonify({"error": "Error interno"}), 500

# @app.route('/responder_alerta', methods=['POST'])
# def responder_alerta():
#     try:
#         mensaje = request.form.get('Body', '').strip().lower()
#         numero = request.form.get('From')
#         print(f"📨 Respuesta recibida de {numero}: {mensaje}")

#         respuesta = MessagingResponse()

#         if mensaje in ['si', 'sí']:
#             # Aquí podrías activar algo más, como guardar en Supabase o activar un protocolo
#             respuesta.message("✅ Protocolo de seguridad ACTIVADO. Gracias por confirmar.")
#             print("🚨 Se activó el protocolo de seguridad.")
#         elif mensaje == 'no':
#             respuesta.message("❎ Anomalía descartada. Gracias por tu respuesta.")
#             print("ℹ️ Anomalía descartada por el tutor.")
#         else:
#             respuesta.message("❓ Respuesta no entendida. Por favor respondé con 'SI' o 'NO'.")
#             print("⚠️ Respuesta inválida.")

#         return str(respuesta)

#     except Exception as e:
#         print("❌ Error procesando respuesta:", str(e))
#         return "Error", 500