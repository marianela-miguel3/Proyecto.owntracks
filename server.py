from flask import Flask, request, jsonify
import requests
import os
import pandas as pd
import joblib
import numpy as np
from datetime import datetime, timezone, timedelta
from flask_cors import CORS

# Zona horaria de Argentina
ARGENTINA_TZ = timezone(timedelta(hours=-3))

# Cargar modelos
pipeline = joblib.load("pipeline_anomalias.joblib")
modelo_horario, scaler_hora = joblib.load("modelo_horarios.joblib")

# Extraer componentes del pipeline
transformer = pipeline.named_steps['preprocesamiento_completo'].named_steps['column_transformer']
modelo_general = pipeline.named_steps['modelo']

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://project-ifts.netlify.app"}})

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

@app.route('/')
def home():
    return "✅ Servidor Flask actualizado funcionando correctamente 🚀", 200


@app.route('/ubicacion', methods=['POST'])
def recibir_ubicacion():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No se recibieron datos"}), 400

        tipo = data.get("_type")
        if tipo not in ["location", "transition"]:
            return jsonify({"status": "ignored"}), 200

        timestamp = data.get("tst")
        fecha = (
            datetime.fromtimestamp(timestamp, tz=timezone.utc)
            .astimezone(ARGENTINA_TZ)
            .strftime("%Y-%m-%d %H:%M")
        ) if timestamp else None

        evento = data.get("event") if tipo == "transition" else None
        zona = data.get("desc") or (data.get("inregions")[0] if data.get("inregions") else None)
        if tipo == "location" and not zona:
            zona = (data.get("inregions")[0] if data.get("inregions") else None)

        lat = data.get("lat")
        lon = data.get("lon")
        device_id = data.get("tid")

        payload = {
            "latitud": lat,
            "longitud": lon,
            "evento": evento,
            "zona": zona,
            "timestamp": fecha,
            "device": device_id
        }

        # --------- PREDICCIÓN DE ANOMALÍA ---------
        try:
            # Preparar el dato como DataFrame
            ts = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(ARGENTINA_TZ)
            df_nuevo = pd.DataFrame([{
                "timestamp": ts,
                "latitud": lat,
                "longitud": lon,
                "evento": evento,
                "zona": zona
            }])

            # General
            X_general = transformer.transform(pipeline.named_steps['preprocesamiento_completo'].named_steps['preprocesamiento_funcional'].transform(df_nuevo))
            pred_general = modelo_general.predict(X_general)[0]

            # Horario
            hora = ts.hour + ts.minute / 60
            X_hora = scaler_hora.transform([[hora]])
            pred_horario = modelo_horario.predict(X_hora)[0]

            # Anomalía final
            anomalia_final = -1 if (pred_general == -1 or pred_horario == -1) else 1
            payload["es_anomalo"] = int(anomalia_final)
        except Exception as e:
            print("⚠️ Error en predicción:", str(e))
            payload["es_anomalo"] = None

        # --------- GUARDAR EN SUPABASE ---------
        try:
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
            print("✅ Supabase:", resp.status_code, resp.json())
        except Exception as e:
            print("❌ Error al guardar en Supabase:", str(e))

        return jsonify({"status": "ok", "anomalo": payload.get("es_anomalo")})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

        return jsonify(datos[0]), 200

    except Exception as e:
        return jsonify({"error": "Error interno"}), 500

