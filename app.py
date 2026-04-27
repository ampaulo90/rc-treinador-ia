import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from supabase_client import (
    init_supabase, salvar_perfil, obter_perfil,
    salvar_treino_realizado, listar_treinos_realizados,
    obter_plano_semanal, salvar_plano_semanal
)
from utils import (
    processar_csv_garmin, decimal_to_pace,
    calcular_zonas_fc, calcular_zonas_pace,
    calcular_acwr_profissional, calcular_distribuicao_intensidade,
    gerar_yaml_planner
)

st.set_page_config(page_title="RC Treinador Digital", layout="wide")
st.title("🏁 RC Treinador Digital")
st.caption("Treinamento personalizado com análise científica")

# Inicializa Supabase
if "supabase" not in st.session_state:
    try:
        st.session_state.supabase = init_supabase()
        st.session_state.user_id = "default_user"  # Em produção, use autenticação
        st.success("✅ Conectado ao Supabase")
    except Exception as e:
        st.error(f"Erro ao conectar Supabase: {e}. Configure os secrets.")
        st.stop()

# Carrega perfil (se existir)
perfil = obter_perfil(st.session_state.supabase, st.session_state.user_id)
if perfil:
    st.session_state.perfil = perfil
else:
    st.session_state.perfil = None

# Sidebar com status do perfil
with st.sidebar:
    st.image("https://img.icons8.com/ios-filled/100/ffffff/running.png", width=80)
    if st.session_state.perfil:
        st.success(f"Atleta: {st.session_state.perfil.get('nome', '')}")
        st.caption(f"VO₂max: {st.session_state.perfil.get('vo2max', '-')} | FCmax: {st.session_state.perfil.get('fc_max', '-')}")
    else:
        st.warning("Perfil não configurado. Vá na aba 'Meu Perfil'.")

# Abas
tab_perfil, tab_gerar, tab_analisar, tab_historico = st.tabs([
    "👤 Meu Perfil", "🏋️ Gerar Treino (YAML)", "📊 Analisar CSV", "📈 Histórico & Carga"
])

# ------------------------------------------------------------
# ABA PERFIL
# ------------------------------------------------------------
with tab_perfil:
    st.subheader("Configuração do Atleta")
    with st.form("perfil_form"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome completo", value=perfil.get("nome", "") if perfil else "")
            # Campo de data no formato DD-MM-YYYY
            data_nasc_str = st.text_input("Data de nascimento (DD-MM-YYYY)", 
                                          value=perfil.get("data_nascimento", "01-01-1990") if perfil else "01-01-1990")
            altura = st.number_input("Altura (cm)", 100, 220, value=perfil.get("altura_cm", 170) if perfil else 170)
            peso = st.number_input("Peso (kg)", 40, 150, value=perfil.get("peso_kg", 70) if perfil else 70)
        with col2:
            fc_max = st.number_input("FC máxima (bpm)", 120, 220, value=perfil.get("fc_max", 185) if perfil else 185)
            fc_repouso = st.number_input("FC repouso (bpm)", 40, 100, value=perfil.get("fc_repouso", 52) if perfil else 52)
            vo2max = st.number_input("VO₂max estimado", 30, 85, value=perfil.get("vo2max", 52) if perfil else 52)
            pace_limiar = st.number_input("Pace de limiar (min/km) - Ex: 4:30 = 4.5", 3.0, 8.0, 
                                          value=float(perfil.get("pace_limiar_km_min", 4.5)) if perfil else 4.5, step=0.1)
        submitted = st.form_submit_button("Salvar Perfil")
        
        if submitted:
            # Converte data de DD-MM-YYYY para YYYY-MM-DD
            try:
                from datetime import datetime
                data_obj = datetime.strptime(data_nasc_str, "%d-%m-%Y").date()
                data_formatada = data_obj.isoformat()
            except ValueError:
                st.error("Data inválida. Use o formato DD-MM-YYYY (ex: 15-07-1990)")
                st.stop()
            
            dados = {
                "nome": nome,
                "data_nascimento": data_formatada,
                "altura_cm": altura,
                "peso_kg": peso,
                "fc_max": fc_max,
                "fc_repouso": fc_repouso,
                "vo2max": vo2max,
                "pace_limiar_km_min": pace_limiar
            }
            salvar_perfil(st.session_state.supabase, st.session_state.user_id, dados)
            st.success("Perfil salvo com sucesso!")
            st.rerun()

    if fc_max and fc_repouso:
        st.subheader("📊 Zonas de Treino (por Frequência Cardíaca)")
        zonas_fc = calcular_zonas_fc(fc_max, fc_repouso)
        for zona, limites in zonas_fc.items():
            st.write(f"**{zona}**: {limites['min']} – {limites['max']} bpm")

    if pace_limiar:
        st.subheader("📊 Zonas de Treino (por Pace)")
        zonas_pace = calcular_zonas_pace(pace_limiar)
        for zona, (inf, sup) in zonas_pace.items():
            st.write(f"**{zona}**: {decimal_to_pace(inf)} – {decimal_to_pace(sup)}/km")

# ------------------------------------------------------------
# ABA GERAR TREINO (YAML)
# ------------------------------------------------------------
with tab_gerar:
    st.subheader("Criar treino manualmente e exportar para Garmin")
    col1, col2 = st.columns(2)
    with col1:
        nome = st.text_input("Nome do treino", "treino_vo2max")
        aquecimento = st.text_input("Aquecimento", "15min @H(z2)")
        repeticoes = st.number_input("Repetições", 1, 20, 6)
        duracao = st.text_input("Duração do intervalo", "800m")
    with col2:
        alvo = st.text_input("Alvo (pace ou FC)", "@P(4:00-4:10)")
        recuperacao = st.text_input("Recuperação", "2min @H(z1)")
        cooldown = st.text_input("Arrefecimento", "10min @H(z1)")

    if st.button("📥 Exportar YAML", type="primary"):
        yaml_content = gerar_yaml_planner(nome, aquecimento, repeticoes, duracao, alvo, recuperacao, cooldown)
        st.download_button("Baixar .yaml", yaml_content, file_name=f"{nome}.yaml", mime="text/yaml")
        st.success("YAML gerado!")

# ------------------------------------------------------------
# ABA ANALISAR CSV
# ------------------------------------------------------------
with tab_analisar:
    st.subheader("Envie o CSV do treino realizado (Garmin Connect)")
    uploaded_file = st.file_uploader("Arquivo CSV", type="csv")
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success("Arquivo carregado. Processando...")

            # Usar FC máxima do perfil se disponível, senão 185
            fc_max_perfil = st.session_state.perfil.get("fc_max", 185) if st.session_state.perfil else 185
            metricas = processar_csv_garmin(df, fc_max=fc_max_perfil)

            col1, col2, col3 = st.columns(3)
            col1.metric("Distância", f"{metricas['distancia_km']:.2f} km")
            col2.metric("Pace médio", decimal_to_pace(metricas['pace_medio_min_km']))
            col3.metric("FC média", f"{metricas['fc_media_bpm']:.0f} bpm")

            if metricas.get('pace_por_lap'):
                fig = px.line(y=metricas['pace_por_lap'], title="Pace por volta (min/km)")
                st.plotly_chart(fig, use_container_width=True)

            # Salvar no histórico (data atual)
            data_hoje = datetime.today().strftime("%Y-%m-%d")
            csv_text = uploaded_file.getvalue().decode("utf-8")
            salvar_treino_realizado(st.session_state.supabase, st.session_state.user_id, data_hoje, metricas, csv_text)
            st.success("Treino salvo no histórico!")

        except Exception as e:
            st.error(f"Erro ao processar CSV: {e}")
            st.info("Verifique se o CSV contém colunas como 'Ritmo médio', 'FC Média', 'Distância'.")

# ------------------------------------------------------------
# ABA HISTÓRICO E CARGA (ACWR)
# ------------------------------------------------------------
with tab_historico:
    st.subheader("Evolução e Carga de Treino")
    historico = listar_treinos_realizados(st.session_state.supabase, st.session_state.user_id, limit=50)
    if historico:
        # Gráfico de distância
        df_hist = pd.DataFrame(historico)
        df_hist = df_hist.sort_values("data")
        fig_dist = px.line(df_hist, x="data", y="distancia_km", title="Distância por treino (km)")
        st.plotly_chart(fig_dist, use_container_width=True)

        # ACWR
        acwr, status_acwr = calcular_acwr_profissional(historico)
        if acwr:
            st.metric("ACWR (Carga Aguda/Crônica)", acwr, delta=status_acwr)

        # Distribuição de intensidade (se tiver pace limiar no perfil)
        if st.session_state.perfil and st.session_state.perfil.get("pace_limiar_km_min"):
            pace_limiar = st.session_state.perfil["pace_limiar_km_min"]
            dist_intensidade = calcular_distribuicao_intensidade(historico, pace_limiar)
            if dist_intensidade:
                st.subheader("Distribuição por Zonas (últimos treinos)")
                st.json(dist_intensidade)
    else:
        st.info("Nenhum treino registrado. Suba um CSV na aba 'Analisar CSV'.")
