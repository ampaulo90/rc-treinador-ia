import pandas as pd
import re
import json
import requests
import numpy as np
from datetime import timedelta, datetime

# ------------------------------------------------------------
# Conversão de pace e tempo
# ------------------------------------------------------------
def pace_to_decimal(pace_str):
    if pd.isna(pace_str):
        return 0.0
    pace_str = str(pace_str).strip()
    match = re.search(r'(\d+):(\d+(?:\.\d+)?)', pace_str)
    if match:
        minutos = int(match.group(1))
        segundos = float(match.group(2))
        return minutos + segundos / 60.0
    try:
        return float(pace_str)
    except:
        return 0.0

def decimal_to_pace(valor_minutos):
    if valor_minutos <= 0:
        return "00:00"
    minutos = int(valor_minutos)
    segundos = int((valor_minutos - minutos) * 60)
    return f"{minutos:02d}:{segundos:02d}"

def time_to_seconds(tempo_str):
    if pd.isna(tempo_str):
        return 0
    partes = str(tempo_str).split(':')
    if len(partes) == 2:
        return int(partes[0]) * 60 + float(partes[1])
    elif len(partes) == 3:
        return int(partes[0]) * 3600 + int(partes[1]) * 60 + float(partes[2])
    return 0

def detectar_coluna(df, possiveis):
    for col in df.columns:
        for nome in possiveis:
            if nome.lower() in col.lower():
                return col
    return None

# ------------------------------------------------------------
# Processamento do CSV do Garmin (corrigido e testado)
# ------------------------------------------------------------
def processar_csv_garmin(df, fc_max=185):
    col_pace = detectar_coluna(df, ["ritmo médio", "pace", "ritmo"])
    col_fc = detectar_coluna(df, ["fc média", "heart rate", "bpm"])
    col_dist = detectar_coluna(df, ["distância", "distance"])
    col_tempo = detectar_coluna(df, ["tempo", "time"])
    col_tipo = detectar_coluna(df, ["tipo de etapa", "step type"])

    if not col_pace:
        raise ValueError(f"Coluna pace não encontrada. Colunas: {list(df.columns)}")

    if col_tipo:
        df_filtrado = df[~df[col_tipo].astype(str).str.contains("Resumo|resumo", na=False)]
        df_filtrado = df_filtrado[df_filtrado[col_tipo].notna()]
    else:
        df_filtrado = df.copy()

    df_clean = df_filtrado.copy()
    df_clean["pace_decimal"] = df_clean[col_pace].apply(pace_to_decimal)

    if col_tempo:
        df_clean["tempo_segundos"] = df_clean[col_tempo].apply(time_to_seconds)

    if col_dist:
        # Distância já em km (valores como 2.00, 0.10, etc.)
        distancia_km = df_clean[col_dist].sum()
    else:
        distancia_km = 0

    pace_medio = df_clean["pace_decimal"].mean()
    fc_media = df_clean[col_fc].mean() if col_fc else 0

    if col_tempo:
        tempo_total_seg = df_clean["tempo_segundos"].sum()
        tempo_total_str = str(timedelta(seconds=int(tempo_total_seg)))
        tempo_min = tempo_total_seg / 60
    else:
        tempo_total_str = "N/A"
        tempo_min = 0

    # Carga TRIMP simplificada
    carga = calcular_carga_treino(tempo_min, fc_media, fc_max) if fc_max > 0 else tempo_min

    pace_por_lap = df_clean["pace_decimal"].tolist()
    fc_por_lap = df_clean[col_fc].tolist() if col_fc else []

    return {
        "distancia_km": round(distancia_km, 2),
        "pace_medio_min_km": round(pace_medio, 2),
        "fc_media_bpm": round(fc_media, 1),
        "tempo_total_str": tempo_total_str,
        "tempo_min": round(tempo_min, 2),
        "carga": round(carga, 2),
        "pace_por_lap": pace_por_lap,
        "fc_por_lap": fc_por_lap,
        "num_laps": len(df_clean)
    }

# ------------------------------------------------------------
# Cálculo de carga (TRIMP)
# ------------------------------------------------------------
def calcular_carga_treino(tempo_min, fc_media, fc_max):
    if fc_max == 0 or fc_media == 0:
        return round(tempo_min, 2)
    intensidade = fc_media / fc_max
    carga = tempo_min * (intensidade ** 2)
    return round(carga, 2)

# ------------------------------------------------------------
# Zonas de treino
# ------------------------------------------------------------
def calcular_zonas_fc(fc_max, fc_repouso):
    reserva = fc_max - fc_repouso
    zonas = {}
    limites = [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 1.00)]
    for i, (lim_inf, lim_sup) in enumerate(limites, 1):
        zonas[f"Z{i}"] = {
            "min": int(fc_repouso + reserva * lim_inf),
            "max": int(fc_repouso + reserva * lim_sup)
        }
    return zonas

def calcular_zonas_pace(pace_limiar_min_km):
    """
    pace_limiar_min_km = ritmo em min/km (ex: 4.5 -> 4:30)
    Retorna dicionário zona -> (pace_min, pace_max) em min/km.
    """
    zonas = {
        "Z1 (regenerativo)": (pace_limiar_min_km + 1.0, pace_limiar_min_km + 2.0),
        "Z2 (aeróbico leve)": (pace_limiar_min_km + 0.30, pace_limiar_min_km + 1.0),
        "Z3 (aeróbico moderado)": (pace_limiar_min_km + 0.10, pace_limiar_min_km + 0.30),
        "Z4 (limiar)": (pace_limiar_min_km - 0.10, pace_limiar_min_km + 0.10),
        "Z5 (VO2max)": (pace_limiar_min_km - 0.40, pace_limiar_min_km - 0.10)
    }
    return zonas

def classificar_zona_por_pace(pace_min_km, pace_limiar):
    zonas = calcular_zonas_pace(pace_limiar)
    for zona, (lim_inf, lim_sup) in zonas.items():
        if lim_inf <= pace_min_km <= lim_sup:
            return zona
    return "Desconhecida"

# ------------------------------------------------------------
# Distribuição de intensidade (polarizada)
# ------------------------------------------------------------
def calcular_distribuicao_intensidade(historico, pace_limiar):
    if not historico:
        return {}
    distribuicao = {}
    for treino in historico:
        pace = treino.get("pace_medio_min_km", 0)
        if pace > 0:
            zona = classificar_zona_por_pace(pace, pace_limiar)
            distribuicao[zona] = distribuicao.get(zona, 0) + 1
    total = sum(distribuicao.values())
    if total == 0:
        return {}
    return {z: round(v/total*100, 1) for z, v in distribuicao.items()}

# ------------------------------------------------------------
# ACWR profissional
# ------------------------------------------------------------
def calcular_acwr_profissional(historico):
    if len(historico) < 7:
        return None, "Histórico insuficiente (<7 dias)"
    cargas = [h["carga"] for h in historico]
    aguda = sum(cargas[:7]) / 7
    if len(cargas) >= 28:
        cronica = sum(cargas[:28]) / 28
    else:
        cronica = sum(cargas) / len(cargas)
    ratio = aguda / cronica if cronica > 0 else 1.0
    if ratio < 0.8:
        status = "⬇️ Subcarga – pode aumentar volume"
    elif ratio <= 1.3:
        status = "✅ Zona ideal"
    elif ratio <= 1.5:
        status = "⚠️ Carga alta – atenção"
    else:
        status = "🚨 Alto risco de lesão – reduzir"
    return round(ratio, 2), status

# ------------------------------------------------------------
# Geração de YAML para Garmin Planner
# ------------------------------------------------------------
def gerar_yaml_planner(nome, aquecimento, repeticoes, duracao, alvo, recuperacao, cooldown):
    nome_workout = nome.lower().replace(" ", "_")
    return f"""settings:
  deleteSameNameWorkout: true

workouts:
  {nome_workout}:
    - warmup: {aquecimento}
    - repeat({repeticoes}):
        - run: {duracao} {alvo}
        - recovery: {recuperacao}
    - cooldown: {cooldown}
"""

# ------------------------------------------------------------
# Chamada Gemini (para integração futura)
# ------------------------------------------------------------
def _call_gemini(api_key, prompt, temperature=0.7):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Erro Gemini: {resp.text}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]
