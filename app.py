import streamlit as st
import pandas as pd
import plotly.express as px
from utils import processar_csv, decimal_to_pace, gerar_yaml

st.set_page_config(page_title="RC Treinador Digital", layout="wide")
st.title("🏃 RC Treinador Digital")
st.caption("Gere treinos e analise CSVs do Garmin")

with st.sidebar:
    st.subheader("Perfil do Atleta")
    vo2max = st.number_input("VO₂max", 30, 85, 52)
    fc_max = st.number_input("FC máxima", 120, 220, 185)

tab1, tab2 = st.tabs(["📅 Gerar Treino", "📊 Analisar CSV"])

with tab1:
    st.subheader("Crie seu treino e exporte para YAML")
    nome = st.text_input("Nome do treino", "treino_intervalado")
    aquecimento = st.text_input("Aquecimento", "15min @H(z2)")
    repeticoes = st.number_input("Repetições", 1, 20, 6)
    duracao = st.text_input("Duração do intervalo", "800m")
    alvo = st.text_input("Alvo", "@P(4:00-4:10)")
    recuperacao = st.text_input("Recuperação", "2min @H(z1)")
    cooldown = st.text_input("Arrefecimento", "10min @H(z1)")

    if st.button("Exportar YAML"):
        yaml_content = gerar_yaml(nome, aquecimento, repeticoes, duracao, alvo, recuperacao, cooldown)
        st.download_button("📥 Baixar arquivo .yaml", yaml_content, file_name=f"{nome}.yaml")

with tab2:
    st.subheader("Analise um treino realizado (CSV do Garmin)")
    uploaded = st.file_uploader("Envie o arquivo CSV", type="csv")
    if uploaded:
        df = pd.read_csv(uploaded)
        try:
            metricas = processar_csv(df, fc_max)
            col1, col2, col3 = st.columns(3)
            col1.metric("Distância", f"{metricas['distancia_km']:.2f} km")
            col2.metric("Pace médio", decimal_to_pace(metricas['pace_medio']))
            col3.metric("FC média", f"{metricas['fc_media']:.0f} bpm")
            if metricas.get('pace_por_lap'):
                fig = px.line(y=metricas['pace_por_lap'], title="Pace por volta (min/km)")
                st.plotly_chart(fig, use_container_width=True)
            st.success("Análise concluída!")
        except Exception as e:
            st.error(f"Erro: {e}")
