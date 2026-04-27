import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from supabase_client import (
    init_supabase, salvar_perfil, obter_perfil,
    salvar_treino_realizado, listar_treinos_realizados,
    salvar_plano_semanal, obter_plano_semanal
)
from utils import (
    processar_csv_garmin, decimal_to_pace, calcular_zonas_fc, calcular_zonas_pace,
    calcular_acwr_profissional, calcular_distribuicao_intensidade, exportar_plano_yaml,
    gerar_plano_semanal_deepseek, obter_localizacao_e_clima
)

st.set_page_config(page_title="RC Treinador IA (DeepSeek)", layout="wide")
st.title("🏁 RC Treinador Digital IA")
st.caption("Planejamento semanal com DeepSeek, análise pós-treino e clima")

# Supabase
if "supabase" not in st.session_state:
    try:
        st.session_state.supabase = init_supabase()
        st.session_state.user_id = "default_user"
    except Exception as e:
        st.error(f"Erro Supabase: configure os secrets. {e}")
        st.stop()

perfil = obter_perfil(st.session_state.supabase, st.session_state.user_id)
st.session_state.perfil = perfil

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/running.png", width=80)
    if perfil:
        st.success(f"Atleta: {perfil.get('nome', '')}")
        st.caption(f"VO₂max: {perfil.get('vo2max', '-')} | FCmax: {perfil.get('fc_max', '-')}")
    else:
        st.warning("Perfil não configurado.")
    st.divider()
    cidade, temp = obter_localizacao_e_clima()
    st.metric("🌍 Local", cidade)
    if temp:
        st.metric("🌡️ Temperatura", f"{temp}°C")
    st.divider()
    deepseek_key = st.text_input("🔑 DeepSeek API Key", type="password", value="sk-9d87c603a7c54096b4a4bb0e618ed3c9")
    if deepseek_key:
        st.session_state.deepseek_key = deepseek_key
    else:
        st.session_state.deepseek_key = None

tab_perfil, tab_calendario, tab_analisar, tab_historico = st.tabs(
    ["👤 Meu Perfil", "📅 Plano Semanal (IA)", "📊 Analisar CSV", "📈 Histórico & ACWR"]
)

# ------------------------------------------------------------
# Perfil
# ------------------------------------------------------------
with tab_perfil:
    st.subheader("Configuração do Atleta")
    with st.form("perfil_form"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome", value=perfil.get("nome", "Ampaulo Castro") if perfil else "Ampaulo Castro")
            data_nasc = st.text_input("Nascimento (DD-MM-YYYY)", value=perfil.get("data_nascimento", "15-07-1990") if perfil else "15-07-1990")
            altura = st.number_input("Altura (cm)", 100, 220, value=perfil.get("altura_cm", 180) if perfil else 180)
            peso = st.number_input("Peso (kg)", 40, 150, value=perfil.get("peso_kg", 99) if perfil else 99)
        with col2:
            fc_max = st.number_input("FC máxima (bpm)", 120, 220, value=perfil.get("fc_max", 185) if perfil else 185)
            fc_repouso = st.number_input("FC repouso (bpm)", 40, 100, value=perfil.get("fc_repouso", 52) if perfil else 52)
            vo2max = st.number_input("VO₂max", 30, 85, value=perfil.get("vo2max", 41) if perfil else 41)
            pace_limiar = st.number_input("Pace limiar (min/km)", 3.0, 8.0,
                                         value=float(perfil.get("pace_limiar_km_min", 5.46)) if perfil else 5.46, step=0.01)
        submitted = st.form_submit_button("Salvar Perfil")
        if submitted:
            try:
                data_obj = datetime.strptime(data_nasc, "%d-%m-%Y").date()
                data_formatada = data_obj.isoformat()
            except:
                st.error("Data inválida. Use DD-MM-YYYY")
                st.stop()
            dados = {
                "nome": nome, "data_nascimento": data_formatada, "altura_cm": altura, "peso_kg": peso,
                "fc_max": fc_max, "fc_repouso": fc_repouso, "vo2max": vo2max, "pace_limiar_km_min": pace_limiar
            }
            salvar_perfil(st.session_state.supabase, st.session_state.user_id, dados)
            st.success("Perfil salvo! Recarregue a página.")
            st.rerun()

    if fc_max and fc_repouso:
        st.subheader("Zonas FC")
        for zona, lim in calcular_zonas_fc(fc_max, fc_repouso).items():
            st.write(f"**{zona}**: {lim['min']}–{lim['max']} bpm")
    if pace_limiar:
        st.subheader("Zonas Pace")
        for zona, (inf, sup) in calcular_zonas_pace(pace_limiar).items():
            st.write(f"**{zona}**: {decimal_to_pace(inf)} – {decimal_to_pace(sup)}/km")

# ------------------------------------------------------------
# Calendário semanal com DeepSeek
# ------------------------------------------------------------
with tab_calendario:
    if not perfil:
        st.error("Configure seu perfil primeiro.")
    else:
        if not st.session_state.get("deepseek_key"):
            st.warning("Insira sua API Key DeepSeek na sidebar.")
        st.subheader("Plano da Semana")
        hoje = datetime.today().date()
        segunda = hoje - timedelta(days=hoje.weekday())
        semana_inicio = segunda.strftime("%Y-%m-%d")

        if st.button("🔄 Gerar / Atualizar Plano com DeepSeek"):
            if not st.session_state.deepseek_key:
                st.error("Adicione a chave DeepSeek.")
            else:
                with st.spinner("IA DeepSeek criando seu plano semanal..."):
                    historico = listar_treinos_realizados(st.session_state.supabase, st.session_state.user_id, limit=30)
                    ultimo = historico[0] if historico else None
                    plano = gerar_plano_semanal_deepseek(
                        st.session_state.deepseek_key, perfil, ultimo, historico, semana_inicio
                    )
                    salvar_plano_semanal(st.session_state.supabase, st.session_state.user_id, semana_inicio, plano)
                    st.success("Plano gerado e salvo!")
                    st.rerun()

        plano = obter_plano_semanal(st.session_state.supabase, st.session_state.user_id, semana_inicio)
        if not plano:
            st.info("Nenhum plano ainda. Clique no botão acima.")
        else:
            cols = st.columns(7)
            for i, dia in enumerate(sorted(plano.keys())[:7]):
                treino = plano.get(dia, {})
                with cols[i]:
                    data_obj = datetime.strptime(dia, "%Y-%m-%d")
                    st.write(f"**{data_obj.strftime('%a, %d/%m')}**")
                    if treino.get("descanso"):
                        st.write("😴 Descanso")
                    else:
                        st.write(f"🏃 {treino.get('nome', 'Treino')}")
                        st.caption(f"{treino.get('repeticoes',1)}x {treino.get('duracao')} {treino.get('alvo','')}")
            yaml_content = exportar_plano_yaml(plano, semana_inicio)
            st.download_button("📥 Exportar YAML", yaml_content, file_name=f"plano_{semana_inicio}.yaml")

# ------------------------------------------------------------
# Analisar CSV
# ------------------------------------------------------------
with tab_analisar:
    st.subheader("Envie o CSV do Garmin")
    uploaded = st.file_uploader("CSV", type="csv")
    if uploaded:
        try:
            df = pd.read_csv(uploaded, skipinitialspace=True, na_values=[''])
            fc_max = perfil.get("fc_max", 185) if perfil else 185
            metricas = processar_csv_garmin(df, fc_max)
            col1, col2, col3 = st.columns(3)
            col1.metric("Distância", f"{metricas['distancia_km']:.2f} km")
            col2.metric("Pace médio", decimal_to_pace(metricas['pace_medio_min_km']))
            col3.metric("FC média", f"{metricas['fc_media_bpm']:.0f} bpm")

            if metricas.get('pace_por_lap'):
                fig = px.line(y=metricas['pace_por_lap'], title="Pace por etapa (min/km)")
                st.plotly_chart(fig, use_container_width=True)

            # Salvar
            data_hoje = datetime.today().strftime("%Y-%m-%d")
            csv_text = uploaded.getvalue().decode("utf-8", errors="ignore")
            salvar_treino_realizado(st.session_state.supabase, st.session_state.user_id, data_hoje, metricas, csv_text)
            st.success("Treino salvo!")
        except Exception as e:
            st.error(f"Erro: {e}")
            st.info("Verifique as colunas: 'Ritmo médio', 'FC Média', 'Distância', 'Tempo'.")

# ------------------------------------------------------------
# Histórico e ACWR
# ------------------------------------------------------------
with tab_historico:
    historico = listar_treinos_realizados(st.session_state.supabase, st.session_state.user_id, limit=50)
    if not historico:
        st.info("Nenhum treino registrado.")
    else:
        df_h = pd.DataFrame(historico).sort_values("data")
        fig = px.line(df_h, x="data", y="distancia_km", title="Evolução da Distância")
        st.plotly_chart(fig, use_container_width=True)
        acwr, status = calcular_acwr_profissional(historico)
        if acwr:
            st.metric("ACWR", acwr, delta=status)
        if perfil and perfil.get("pace_limiar_km_min"):
            dist_int = calcular_distribuicao_intensidade(historico, perfil["pace_limiar_km_min"])
            if dist_int:
                st.subheader("Distribuição por Zonas")
                st.json(dist_int)
        st.dataframe(df_h[["data", "distancia_km", "pace_medio_min_km", "fc_media_bpm", "tempo_total_str"]])
