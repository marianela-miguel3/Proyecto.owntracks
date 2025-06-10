from flask import Flask, request, jsonify
import requests
import os
import pandas as pd
import numpy as np
import joblib
from datetime import datetime, timezone, timedelta
from flask_cors import CORS

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

        device_id = data.get("tid")
        tipo = data.get("_type")
        print("📥 Datos recibidos:", data)

        if tipo not in ["location", "transition"]:
            print("⚠️ Tipo no válido:", tipo)
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
            evento = data.get("event")
            zona = data.get("desc") or (data.get("inregions")[0] if data.get("inregions") else None)
        elif tipo == "location":
            zona = data.get("inregions")[0] if data.get("inregions") else None

        payload = {
            "latitud": lat,
            "longitud": lon,
            "evento": evento,
            "zona": zona,
            "timestamp": fecha,
            "device": device_id
        }

        try:
            # Preparar datos
            dato = {
                "latitud": lat,
                "longitud": lon,
                "evento": evento,
                "zona": zona,
                "timestamp": fecha
            }
            df = pd.DataFrame([dato])
            df_proc = extraer_variables(df)

            # Predicción general
            X_general = transformer_general.transform(df_proc)
            pred_general = modelo_general.predict(X_general)[0]

            # Predicción horaria
            X_hora = scaler_horario.transform(df_proc[["hora"]])
            pred_hora = modelo_horario.predict(X_hora)[0]

            # Combinación
            es_anomalo = 1 if pred_general == -1 or pred_hora == -1 else 0
            payload["es_anomalo"] = es_anomalo
            print(f"🔎 General: {pred_general}, Horario: {pred_hora} → Final: {'ANOMALÍA' if es_anomalo else 'Normal'}")

        except Exception as e:
            print("⚠️ Error en predicción:", str(e))
            payload["es_anomalo"] = None

        # Guardar en Supabase
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
        return jsonify({"error": str(e)}), 500
