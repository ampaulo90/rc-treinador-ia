import pandas as pd
import re
from datetime import timedelta

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

def processar_csv(df, fc_max=185):
    col_pace = detectar_coluna(df, ["ritmo médio", "pace", "ritmo"])
    col_fc = detectar_coluna(df, ["fc média", "heart rate", "bpm"])
    col_dist = detectar_coluna(df, ["distância", "distance"])
    col_tempo = detectar_coluna(df, ["tempo", "time"])

    if not col_pace:
        raise Exception(f"Coluna de pace não encontrada. Colunas: {list(df.columns)}")

    df_clean = df.copy()
    df_clean["pace_decimal"] = df_clean[col_pace].apply(pace_to_decimal)
    if col_tempo:
        df_clean["tempo_segundos"] = df_clean[col_tempo].apply(time_to_seconds)

    distancia_km = df_clean[col_dist].sum() / 1000 if col_dist else 0
    pace_medio = df_clean["pace_decimal"].mean()
    fc_media = df_clean[col_fc].mean() if col_fc else 0
    tempo_total_seg = df_clean["tempo_segundos"].sum() if col_tempo else 0
    tempo_total_str = str(timedelta(seconds=int(tempo_total_seg))) if tempo_total_seg else "N/A"

    pace_por_lap = df_clean["pace_decimal"].tolist()
    fc_por_lap = df_clean[col_fc].tolist() if col_fc else []

    return {
        "distancia_km": round(distancia_km, 2),
        "pace_medio": round(pace_medio, 2),
        "fc_media": round(fc_media, 1),
        "tempo_total_str": tempo_total_str,
        "pace_por_lap": pace_por_lap,
        "fc_por_lap": fc_por_lap,
        "num_laps": len(df_clean)
    }

def gerar_yaml(nome, aquecimento, repeticoes, duracao, alvo, recuperacao, cooldown):
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
