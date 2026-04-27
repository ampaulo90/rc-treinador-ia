import pandas as pd
import re
import json
import requests
from datetime import timedelta, datetime

# ------------------------------------------------------------
# Conversão de pace e tempo
# ------------------------------------------------------------
def pace_to_decimal(pace_str):
    if pd.isna(pace_str):
        return 0.0
    pace_str = str(pace_str).strip().replace(" min/km", "")
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
    tempo_str = str(tempo_str).replace(" min", "").replace(" s", "").strip()
    partes = tempo_str.split(':')
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
# Processamento correto do CSV do Garmin Forerunner 265
# ------------------------------------------------------------
def processar_csv_garmin(df, fc_max=185):
    # Normaliza colunas
    df.columns = [str(col).strip().lower() for col in df.columns]
    col_pace = detectar_coluna(df, ["ritmo médio", "pace", "ritmo"])
    col_fc = detectar_coluna(df, ["fc média", "heart rate", "bpm", "frequência cardíaca média"])
    col_dist = detectar_coluna(df, ["distância", "distance"])
    col_tempo = detectar_coluna(df, ["tempo", "time"])
    col_tipo = detectar_coluna(df, ["tipo de etapa", "step type"])

    if not col_pace:
        raise ValueError(f"Coluna pace não encontrada. Colunas: {list(df.columns)}")

    # Filtra resumo
    if col_tipo:
        mask = ~df[col_tipo].astype(str).str.contains("resumo|summary", case=False, na=False)
        df_filtrado = df[mask].copy()
    else:
        df_filtrado = df.copy()

    # Distância (já em km)
    if col_dist:
        if df_filtrado[col_dist].max() > 100:
            distancia_km = df_filtrado[col_dist].sum() / 1000
        else:
            distancia_km = df_filtrado[col_dist].sum()
    else:
        distancia_km = 0

    df_filtrado["pace_decimal"] = df_filtrado[col_pace].apply(pace_to_decimal)
    pace_medio = df_filtrado["pace_decimal"].mean()
    fc_media = df_filtrado[col_fc].mean() if col_fc else 0

    if col_tempo:
        df_filtrado["tempo_segundos"] = df_filtrado[col_tempo].apply(time_to_seconds)
        tempo_total_seg = df_filtrado["tempo_segundos"].sum()
        tempo_total_str = str(timedelta(seconds=int(tempo_total_seg)))
        tempo_min = tempo_total_seg / 60
    else:
        tempo_total_str = "N/A"
        tempo_min = 0

    carga = calcular_carga_treino(tempo_min, fc_media, fc_max) if fc_max else tempo_min

    pace_por_lap = df_filtrado["pace_decimal"].tolist()
    fc_por_lap = df_filtrado[col_fc].tolist() if col_fc else []

    return {
        "distancia_km": round(distancia_km, 2),
        "pace_medio_min_km": round(pace_medio, 2),
        "fc_media_bpm": round(fc_media, 1),
        "tempo_total_str": tempo_total_str,
        "tempo_min": round(tempo_min, 2),
        "carga": round(carga, 2),
        "pace_por_lap": pace_por_lap,
        "fc_por_lap": fc_por_lap,
        "num_laps": len(df_filtrado)
    }

def calcular_carga_treino(tempo_min, fc_media, fc_max):
    if fc_max == 0 or fc_media == 0:
        return round(tempo_min, 2)
    intensidade = fc_media / fc_max
    carga = tempo_min * (intensidade ** 2)
    return round(carga, 2)

# ------------------------------------------------------------
# Zonas
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
    return {
        "Z1 (regenerativo)": (pace_limiar_min_km + 1.0, pace_limiar_min_km + 2.0),
        "Z2 (aeróbico leve)": (pace_limiar_min_km + 0.30, pace_limiar_min_km + 1.0),
        "Z3 (aeróbico moderado)": (pace_limiar_min_km + 0.10, pace_limiar_min_km + 0.30),
        "Z4 (limiar)": (pace_limiar_min_km - 0.10, pace_limiar_min_km + 0.10),
        "Z5 (VO2max)": (pace_limiar_min_km - 0.40, pace_limiar_min_km - 0.10)
    }

def classificar_zona_por_pace(pace_min_km, pace_limiar):
    for zona, (inf, sup) in calcular_zonas_pace(pace_limiar).items():
        if inf <= pace_min_km <= sup:
            return zona
    return "Fora"

def calcular_distribuicao_intensidade(historico, pace_limiar):
    if not historico:
        return {}
    dist = {}
    for t in historico:
        pace = t.get("pace_medio_min_km", 0)
        if pace > 0:
            zona = classificar_zona_por_pace(pace, pace_limiar)
            dist[zona] = dist.get(zona, 0) + 1
    total = sum(dist.values())
    return {z: round(v/total*100,1) for z,v in dist.items()} if total else {}

# ------------------------------------------------------------
# ACWR
# ------------------------------------------------------------
def calcular_acwr_profissional(historico):
    if len(historico) < 7:
        return None, "Histórico insuficiente (<7 dias)"
    cargas = [h["carga"] for h in historico[:28]]
    aguda = sum(cargas[:7]) / 7
    cronica = sum(cargas[:28]) / 28 if len(cargas) >= 28 else sum(cargas) / len(cargas)
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
# DeepSeek API (compatível com OpenAI)
# ------------------------------------------------------------
def call_deepseek(api_key, prompt, temperature=0.7):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature
    }
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"Erro DeepSeek: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()

def gerar_plano_semanal_deepseek(api_key, perfil, ultimo_treino, historico_cargas, semana_inicio):
    pace_limiar = perfil.get("pace_limiar_km_min", 5.46)
    fc_max = perfil.get("fc_max", 185)
    vo2max = perfil.get("vo2max", 41)
    acwr, status_acwr = calcular_acwr_profissional(historico_cargas) if historico_cargas else (None, "Sem dados")
    ultimo_texto = f"pace {decimal_to_pace(ultimo_treino['pace_medio_min_km'])}/km, FC {ultimo_treino['fc_media_bpm']}bpm" if ultimo_treino else "nenhum"

    prompt = f"""
Você é um treinador de corrida de elite. Crie um plano de treinos para a semana que começa em {semana_inicio} (segunda a domingo).

Dados do atleta:
- VO2max: {vo2max}
- FC máxima: {fc_max} bpm
- Pace de limiar: {decimal_to_pace(pace_limiar)}/km ({pace_limiar} min/km)
- ACWR atual: {acwr} ({status_acwr})
- Último treino: {ultimo_texto}

Regras:
- Periodização polarizada: 80% volume leve (Z1/Z2), 20% intenso (Z3-Z5).
- Se ACWR > 1.3: semana de deload (reduzir 30% de volume e intensidade).
- Se ACWR < 0.8: pode aumentar volume 10%.
- Incluir um dia de descanso completo.

Retorne APENAS um JSON onde as chaves são datas YYYY-MM-DD (segunda a domingo). Cada valor é um objeto com:
{{ "nome": "...", "aquecimento": "...", "repeticoes": int, "duracao": "...", "alvo": "...", "recuperacao": "...", "cooldown": "...", "tipo": "..." }}
Para descanso: {{ "descanso": true }}

Exemplo:
{{
  "2026-05-04": {{"nome": "Rodagem regenerativa", "aquecimento": "10min @H(z1)", "repeticoes": 1, "duracao": "40min", "alvo": "@H(z2)", "recuperacao": "0", "cooldown": "5min", "tipo": "regenerativo"}},
  "2026-05-05": {{"descanso": true}}
}}

Não adicione texto fora do JSON.
"""
    resposta = call_deepseek(api_key, prompt, temperature=0.8)
    resposta = resposta.strip("`").replace("json", "").strip()
    try:
        return json.loads(resposta)
    except:
        # Fallback seguro
        return gerar_plano_fallback(semana_inicio, pace_limiar)

def gerar_plano_fallback(semana_inicio, pace_limiar):
    start = datetime.strptime(semana_inicio, "%Y-%m-%d")
    plano = {}
    for i in range(7):
        dia = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        if i % 2 == 0:
            plano[dia] = {
                "nome": "Intervalado",
                "aquecimento": "15min @H(z2)",
                "repeticoes": 6,
                "duracao": "800m",
                "alvo": f"@P({decimal_to_pace(pace_limiar-0.3)}-{decimal_to_pace(pace_limiar-0.1)})",
                "recuperacao": "2min @H(z1)",
                "cooldown": "10min @H(z1)",
                "tipo": "intervalado"
            }
        else:
            plano[dia] = {"descanso": True}
    return plano

# ------------------------------------------------------------
# Exportação YAML
# ------------------------------------------------------------
def exportar_plano_yaml(plano_semanal, semana_inicio):
    yaml_lines = ["settings:", "  deleteSameNameWorkout: true", "", "workouts:"]
    workouts_map = {}
    for data, treino in plano_semanal.items():
        if treino.get("descanso"):
            continue
        nome = treino["nome"].lower().replace(" ", "_")
        if nome not in workouts_map:
            workouts_map[nome] = treino
    for nome, t in workouts_map.items():
        yaml_lines.append(f"  {nome}:")
        yaml_lines.append(f"    - warmup: {t['aquecimento']}")
        yaml_lines.append(f"    - repeat({t['repeticoes']}):")
        yaml_lines.append(f"        - run: {t['duracao']} {t['alvo']}")
        if t['recuperacao'] != "0":
            yaml_lines.append(f"        - recovery: {t['recuperacao']}")
        yaml_lines.append(f"    - cooldown: {t['cooldown']}")
    yaml_lines.append("")
    yaml_lines.append("schedulePlan:")
    yaml_lines.append(f"  start_from: {semana_inicio}")
    yaml_lines.append("  workouts:")
    for data in sorted(plano_semanal.keys()):
        treino = plano_semanal[data]
        if treino.get("descanso"):
            yaml_lines.append("    - rest")
        else:
            yaml_lines.append(f"    - {treino['nome'].lower().replace(' ', '_')}")
    return "\n".join(yaml_lines)

# ------------------------------------------------------------
# Localização e clima
# ------------------------------------------------------------
def obter_localizacao_e_clima():
    try:
        ip_resp = requests.get("http://ip-api.com/json/", timeout=5)
        ip_data = ip_resp.json()
        cidade = ip_data.get("city", "Desconhecida")
        lat = ip_data.get("lat")
        lon = ip_data.get("lon")
        if lat and lon:
            clima_resp = requests.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true",
                timeout=5
            )
            clima_data = clima_resp.json()
            temp = clima_data.get("current_weather", {}).get("temperature")
            return cidade, round(temp, 1) if temp else None
        return cidade, None
    except:
        return "Não detectada", None
