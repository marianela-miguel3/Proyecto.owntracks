from flask import Flask, request, jsonify
import requests
import os
import pandas as pd
import joblib
from datetime import datetime, timezone, timedelta
from flask_cors import CORS


# Cargar el pipeline entrenado
modelo = joblib.load('modelo_entrenado.joblib')

ARGENTINA_TZ = timezone(timedelta(hours=-3))

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://project-ifts.netlify.app"}})

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Las variables de entorno de Supabase no están configuradas correctamente.")

@app.route('/')
def home():
    return "✅ Servidor Flask en Heroku funcionando correctamente 🚀", 200

@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        device_id = data.get("tid")
        tipo = data.get("_type")
        print("📥 Datos recibidos:", data)

        if tipo not in ["location", "transition"]:
            print("⚠️ Ignorando mensaje: tipo no válido:", tipo)
            return jsonify({"status": "ignored"}), 200

        lat = data.get("lat")
        lon = data.get("lon")
        timestamp = data.get("tst")

        fecha = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .astimezone(ARGENTINA_TZ)
            .strftime("%Y-%m-%d %H:%M")
        ) if timestamp else None

        evento = None
        zona = None

        if tipo == "transition":
            evento = data.get("event")  # enter o leave
            zona = data.get("desc") or (data.get("inregions")[0] if data.get("inregions") else None)
        elif tipo == "location":
            zona = data.get("inregions")[0] if data.get("inregions") else None

        # 📦 Convertir a DataFrame de un solo registro
        df_nuevo = pd.DataFrame([{
            "latitud": lat,
            "longitud": lon,
            "evento": evento,
            "zona": zona,
            "timestamp": fecha,
            "device": device_id
        }])

        # 🧠 Aplicar pipeline entrenado
        df_intermedio = df_nuevo.copy()
        for _, step in modelo.named_steps['preprocesamiento'].steps[:-1]:
            df_intermedio = step.transform(df_intermedio)

        df_procesado = modelo.named_steps['preprocesamiento'].named_steps['escalar'].transform(df_intermedio)
        prediccion = modelo.named_steps['modelo'].predict(df_procesado)
        es_anomalo = int(prediccion[0] == -1)

        # ✅ Agregar resultado a payload
        payload = {
            "latitud": lat,
            "longitud": lon,
            "evento": evento,
            "zona": zona,
            "timestamp": fecha,
            "device": device_id,
            "es_anomalo": es_anomalo
        }

        # 🚀 Enviar a Supabase
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/ubicaciones",
            json=payload,
            headers=headers
        )
        print("✅ Supabase:", resp.status_code, resp.text)
        return jsonify({"status": "datos guardados", "es_anomalo": es_anomalo}), 201

    except Exception as e:
        print("❌ Error general:", str(e))
        return jsonify({"error": "Error interno del servidor"}), 500


# @app.route('/ubicacion', methods=['POST'])
# def recibir_ubicacion():
#     try:
#         data = request.json
#         if not data:
#             return jsonify({"error": "No se recibieron datos"}), 400

#         device_id = data.get("tid")
#         tipo = data.get("_type")
#         print("📥 Datos recibidos:", data)

#         if tipo not in ["location", "transition"]:
#             print("⚠️ Ignorando mensaje: tipo no válido:", tipo)
#             return jsonify({"status": "ignored"}), 200

#         lat = data.get("lat")
#         lon = data.get("lon")
#         timestamp = data.get("tst")

#         fecha = (
#             datetime.fromtimestamp(timestamp, tz=timezone.utc)
#             .astimezone(ARGENTINA_TZ)
#             .strftime("%Y-%m-%d %H:%M")
#         ) if timestamp else None

#         headers = {
#             "apikey": SUPABASE_KEY,
#             "Authorization": f"Bearer {SUPABASE_KEY}",
#             "Content-Type": "application/json",
#             "Prefer": "return=representation"
#         }

#         # Datos comunes para guardar en la base
#         evento = None
#         zona = None

#         if tipo == "transition":
#             evento = data.get("event")  # enter o leave
#             zona = data.get("desc") or (data.get("inregions")[0] if data.get("inregions") else None)
#         elif tipo == "location":
#             zona = data.get("inregions")[0] if data.get("inregions") else None

#         payload = {
#             "latitud": lat,
#             "longitud": lon,
#             "evento": evento,
#             "zona": zona,
#             "timestamp": fecha,
#             "device": device_id
#         }

#         try:
#             resp = requests.post(
#                 f"{SUPABASE_URL}/rest/v1/ubicaciones",
#                 json=payload,
#                 headers=headers
#             )
#             print("✅ Supabase:", resp.status_code, resp.text)
#             return jsonify({"status": "datos guardados"}), 201
#         except Exception as e:
#             print("❌ Error al conectar con Supabase:", str(e))
#             return jsonify({"error": "Error al guardar datos"}), 500

#     except Exception as e:
#         print("❌ Error general:", str(e))
#         return jsonify({"error": "Error interno del servidor"}), 500


@app.route('/ultima_ubicacion', methods=['GET'])
def obtener_ultima_ubicacion():
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    url = f"{SUPABASE_URL}/rest/v1/ubicaciones?order=timestamp.desc&limit=1"

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return jsonify({"error": "No se pudo obtener la ubicación", "detalle": response.text}), response.status_code

        datos = response.json()
        if not datos:
            return jsonify({"mensaje": "No hay ubicaciones registradas"}), 404

        print("Última ubicación:", datos[0])
        return jsonify(datos[0]), 200

    except Exception as e:
        print("❌ Error al consultar Supabase:", str(e))
        return jsonify({"error": "Error interno"}), 500
