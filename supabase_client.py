import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

def salvar_perfil(supabase: Client, user_id: str, dados: dict):
    dados["user_id"] = user_id
    return supabase.table("perfil").upsert(dados, on_conflict="user_id").execute()

def obter_perfil(supabase: Client, user_id: str):
    resp = supabase.table("perfil").select("*").eq("user_id", user_id).execute()
    return resp.data[0] if resp.data else None

def salvar_treino_realizado(supabase: Client, user_id: str, data: str, metricas: dict, csv_text: str = None):
    data_obj = {
        "user_id": user_id, "data": data,
        "distancia_km": metricas["distancia_km"],
        "pace_medio_min_km": metricas["pace_medio_min_km"],
        "fc_media_bpm": metricas["fc_media_bpm"],
        "tempo_total_str": metricas["tempo_total_str"],
        "tempo_min": metricas.get("tempo_min", 0),
        "carga": metricas.get("carga", 0),
        "csv_raw": csv_text
    }
    return supabase.table("treinos_realizados").upsert(data_obj, on_conflict="user_id,data").execute()

def listar_treinos_realizados(supabase: Client, user_id: str, limit=50):
    resp = supabase.table("treinos_realizados")\
        .select("*")\
        .eq("user_id", user_id)\
        .order("data", desc=True)\
        .limit(limit)\
        .execute()
    return resp.data if resp.data else []

def salvar_plano_semanal(supabase: Client, user_id: str, semana_inicio: str, plano_json: dict):
    return supabase.table("planos_semanais").upsert(
        {"user_id": user_id, "semana_inicio": semana_inicio, "plano": plano_json},
        on_conflict="user_id,semana_inicio"
    ).execute()

def obter_plano_semanal(supabase: Client, user_id: str, semana_inicio: str):
    resp = supabase.table("planos_semanais")\
        .select("plano")\
        .eq("user_id", user_id)\
        .eq("semana_inicio", semana_inicio)\
        .execute()
    return resp.data[0]["plano"] if resp.data else None
