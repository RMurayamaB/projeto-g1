"""
Dashboard — Sistema Financeiro e Crédito no Brasil (2015–2024)
Projeto G1 · Linguagem de Programação — Análise e Visualização de Dados com Python

Executar localmente:
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import seaborn as sns
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from database.banco import CONSULTAS, DB_PATH, consultar, criar_banco, get_engine, listar_tabelas, salvar_tabela

# ---------------------------------------------------------------------------
# Configuração geral
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Sistema Financeiro e Crédito no Brasil",
    page_icon=":material/account_balance:",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
CSV_PADRAO = BASE_DIR / "dados" / "simulacao_sistema_financeiro_brasil.csv"

COLUNAS_OBRIGATORIAS = [
    "ano", "mes", "data", "regiao", "uf", "modalidade_credito", "valor_credito",
    "taxa_juros", "inadimplencia_percentual", "quantidade_clientes", "renda_media",
    "prazo_medio_pagamento", "risco_credito", "setor_economico",
]

MESES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
         7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
ORDEM_RISCO = ["Baixo", "Médio", "Alto"]
ORDEM_REGIAO = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]

AZUL = "#0B3D91"
PALETA = ["#0B3D91", "#2E86AB", "#2CA58D", "#F2A541", "#D1495B", "#6C757D", "#8E6C8A"]
CORES_RISCO = {"Baixo": "#2CA58D", "Médio": "#F2A541", "Alto": "#D1495B"}
CORES_REGIAO = dict(zip(ORDEM_REGIAO, ["#2CA58D", "#F2A541", "#8E6C8A", "#0B3D91", "#2E86AB"]))

# Coordenadas aproximadas das capitais (para o mapa interativo)
COORD_UF = {
    "AC": (-9.975, -67.810), "AL": (-9.665, -35.735), "AP": (0.034, -51.069),
    "AM": (-3.119, -60.021), "BA": (-12.971, -38.501), "CE": (-3.717, -38.543),
    "DF": (-15.794, -47.882), "ES": (-20.315, -40.312), "GO": (-16.686, -49.264),
    "MA": (-2.530, -44.302), "MT": (-15.601, -56.097), "MS": (-20.469, -54.620),
    "MG": (-19.916, -43.934), "PA": (-1.455, -48.502), "PB": (-7.119, -34.845),
    "PR": (-25.428, -49.273), "PE": (-8.047, -34.877), "PI": (-5.092, -42.803),
    "RJ": (-22.906, -43.172), "RN": (-5.795, -35.209), "RS": (-30.034, -51.217),
    "RO": (-8.761, -63.903), "RR": (2.823, -60.675), "SC": (-27.595, -48.548),
    "SP": (-23.550, -46.633), "SE": (-10.947, -37.073), "TO": (-10.184, -48.333),
}

# Séries do SGS/Banco Central utilizadas na integração via API
SERIES_BCB = {
    4189: "Selic (% a.a.)",
    21082: "Inadimplência SFN (%)",
    20539: "Saldo da carteira de crédito (R$ milhões)",
}

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
      h1, h2, h3 {color: #0B3D91;}
      div[data-testid="stMetric"] {background: #F7F9FC; border: 1px solid #E3E8F0;
            border-radius: 10px; padding: 12px 14px;}
      div[data-testid="stMetricLabel"] p {font-size: 0.85rem; color: #4A5568;}
      .caixa-texto {background: #F7F9FC; border-left: 4px solid #0B3D91; border-radius: 6px;
            padding: 14px 18px; margin: 6px 0 14px 0; line-height: 1.55;}
      .rodape {color: #6C757D; font-size: 0.8rem; margin-top: 2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Formatação (padrão brasileiro)
# ---------------------------------------------------------------------------

def _br(valor: float, casas: int = 2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor: float) -> str:
    """Valor monetário compacto: R$ 1,23 bi / R$ 4,56 mi / R$ 7,89 mil."""
    absoluto = abs(valor)
    if absoluto >= 1e9:
        return f"R$ {_br(valor / 1e9)} bi"
    if absoluto >= 1e6:
        return f"R$ {_br(valor / 1e6)} mi"
    if absoluto >= 1e3:
        return f"R$ {_br(valor / 1e3)} mil"
    return f"R$ {_br(valor)}"


def pct(valor: float, casas: int = 2) -> str:
    return f"{_br(valor, casas)}%"


def num(valor: float, casas: int = 0) -> str:
    return _br(valor, casas)


def caixa(texto: str) -> None:
    st.markdown(f"<div class='caixa-texto'>{texto}</div>", unsafe_allow_html=True)


ROTULOS = {
    "valor_credito": "Valor do crédito", "volume_mi": "Volume (R$ mi)", "volume": "Volume (R$)",
    "taxa_juros": "Taxa de juros (%)", "inadimplencia_percentual": "Inadimplência (%)", "inad": "Inadimplência (%)",
    "risco_credito": "Risco", "modalidade_credito": "Modalidade", "setor_economico": "Setor", "regiao": "Região",
    "participacao": "Participação (%)", "periodo": "Período", "ano": "Ano", "mes_nome": "Mês", "faixa_juros": "Faixa de juros",
    "operacoes": "Operações", "valor": "Valor", "uf": "UF", "juros": "Juros (%)",
}


def estilizar(fig: go.Figure, altura: int = 420, legenda: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=altura,
        margin=dict(l=10, r=10, t=50, b=10),
        font=dict(family="Segoe UI, Arial", size=13, color="#2D3748"),
        title_font=dict(size=16, color=AZUL),
        legend=dict(orientation="h", yanchor="top", y=-0.14, xanchor="left", x=0, title_text=""),
        showlegend=legenda,
        separators=",.",
    )
    for trace in fig.data:
        modelo = getattr(trace, "hovertemplate", None)
        if modelo:
            for tecnico, rotulo in ROTULOS.items():
                modelo = modelo.replace(f"{tecnico}=", f"{rotulo}=")
            trace.hovertemplate = modelo
    if not fig.layout.title.text:
        fig.update_layout(title_text="", margin=dict(t=20))
    if legenda:
        fig.update_layout(margin=dict(b=60))
    return fig


def forca_correlacao(r: float) -> str:
    a = abs(r)
    if a < 0.1:
        return "desprezível"
    if a < 0.3:
        return "fraca"
    if a < 0.5:
        return "moderada"
    if a < 0.7:
        return "forte"
    return "muito forte"


# ---------------------------------------------------------------------------
# Carga, limpeza e engenharia de atributos
# ---------------------------------------------------------------------------

def tratar_dados(bruto: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Limpeza, validação e criação de atributos. Retorna (df, relatório)."""
    df = bruto.copy()
    rel = {"linhas_originais": len(df)}

    # 1. Padronização dos nomes de colunas
    df.columns = (
        df.columns.str.replace("\ufeff", "", regex=False)
        .str.strip().str.lower().str.replace(" ", "_")
    )
    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Colunas obrigatórias ausentes: {', '.join(faltantes)}")

    # 2. Tipos e padronização de texto
    for col in ["regiao", "uf", "modalidade_credito", "risco_credito", "setor_economico"]:
        df[col] = df[col].astype(str).str.strip()
    df["uf"] = df["uf"].str.upper()
    df["risco_credito"] = df["risco_credito"].str.capitalize().replace({"Medio": "Médio"})

    numericas = ["ano", "mes", "valor_credito", "taxa_juros", "inadimplencia_percentual",
                 "quantidade_clientes", "renda_media", "prazo_medio_pagamento"]
    for col in numericas:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    sem_data = df["data"].isna() & df["ano"].notna() & df["mes"].notna()
    df.loc[sem_data, "data"] = pd.to_datetime(
        dict(year=df.loc[sem_data, "ano"], month=df.loc[sem_data, "mes"], day=1)
    )

    # 3. Nulos e duplicados
    rel["valores_nulos"] = int(df[COLUNAS_OBRIGATORIAS].isna().sum().sum())
    df = df.dropna(subset=COLUNAS_OBRIGATORIAS)
    rel["duplicados_removidos"] = int(df.duplicated().sum())
    df = df.drop_duplicates()

    # 4. Regras de consistência (valores impossíveis)
    invalidos = (
        (df["valor_credito"] <= 0) | (df["quantidade_clientes"] <= 0)
        | (~df["inadimplencia_percentual"].between(0, 100)) | (df["taxa_juros"] < 0)
        | (~df["mes"].between(1, 12)) | (df["renda_media"] <= 0) | (df["prazo_medio_pagamento"] <= 0)
    )
    rel["registros_invalidos"] = int(invalidos.sum())
    df = df[~invalidos].copy()

    # 5. Outliers (regra do IQR) — apenas sinalizados, não removidos
    q1, q3 = df["valor_credito"].quantile([0.25, 0.75])
    iqr = q3 - q1
    df["outlier_valor"] = ~df["valor_credito"].between(q1 - 1.5 * iqr, q3 + 1.5 * iqr)
    rel["outliers_sinalizados"] = int(df["outlier_valor"].sum())

    # 6. Engenharia de atributos
    df["ano"] = df["ano"].astype(int)
    df["mes"] = df["mes"].astype(int)
    df["quantidade_clientes"] = df["quantidade_clientes"].astype(int)
    df["periodo"] = df["data"].dt.to_period("M").dt.to_timestamp()
    df["mes_nome"] = df["mes"].map(MESES)
    df["trimestre"] = df["data"].dt.quarter
    df["ano_trimestre"] = df["ano"].astype(str) + "-T" + df["trimestre"].astype(str)
    df["valor_milhoes"] = df["valor_credito"] / 1e6
    df["ticket_medio_cliente"] = df["valor_credito"] / df["quantidade_clientes"]
    df["valor_em_atraso"] = df["valor_credito"] * df["inadimplencia_percentual"] / 100
    df["comprometimento_renda"] = df["ticket_medio_cliente"] / (df["renda_media"] * df["prazo_medio_pagamento"] / 30)
    df["faixa_juros"] = pd.cut(
        df["taxa_juros"], bins=[0, 20, 40, 60, 80, np.inf],
        labels=["Até 20%", "20–40%", "40–60%", "60–80%", "Acima de 80%"], include_lowest=True,
    )
    df["faixa_renda"] = pd.qcut(df["renda_media"], 4, labels=["Q1 (menor)", "Q2", "Q3", "Q4 (maior)"])
    df["faixa_prazo"] = pd.cut(
        df["prazo_medio_pagamento"], bins=[0, 60, 120, 180, np.inf],
        labels=["Até 60 meses", "61–120 meses", "121–180 meses", "Acima de 180 meses"], include_lowest=True,
    )
    df["risco_credito"] = pd.Categorical(df["risco_credito"], categories=ORDEM_RISCO, ordered=True)
    df["risco_alto"] = (df["risco_credito"] == "Alto").astype(int)

    rel["linhas_finais"] = len(df)
    rel["periodo"] = f"{df['data'].min():%m/%Y} a {df['data'].max():%m/%Y}"
    return df.sort_values("data").reset_index(drop=True), rel


@st.cache_data(show_spinner="Carregando e tratando a base de dados...")
def carregar_base(conteudo: bytes | None = None) -> tuple[pd.DataFrame, dict]:
    if conteudo is None:
        bruto = pd.read_csv(CSV_PADRAO, encoding="utf-8-sig")
    else:
        try:
            bruto = pd.read_csv(io.BytesIO(conteudo), encoding="utf-8-sig")
        except UnicodeDecodeError:
            bruto = pd.read_csv(io.BytesIO(conteudo), encoding="latin-1")
        if bruto.shape[1] == 1:  # arquivo separado por ponto e vírgula
            bruto = pd.read_csv(io.BytesIO(conteudo), encoding="utf-8-sig", sep=";", decimal=",")
    return tratar_dados(bruto)


@st.cache_resource(show_spinner="Preparando banco SQLite...")
def preparar_banco() -> str:
    if not DB_PATH.exists():
        df_original = pd.read_csv(CSV_PADRAO, encoding="utf-8-sig")
        criar_banco(df_original)
    return str(DB_PATH)


@st.cache_data(ttl=6 * 3600, show_spinner="Consultando a API do Banco Central...")
def buscar_series_bcb(data_inicial: str, data_final: str) -> tuple[pd.DataFrame, list[str]]:
    """Consome a API SGS do Banco Central (Requests) e retorna as séries mensais."""
    frames, erros = [], []
    for codigo, nome in SERIES_BCB.items():
        url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
               f"?formato=json&dataInicial={data_inicial}&dataFinal={data_final}")
        try:
            resposta = requests.get(url, timeout=15, headers={"Accept": "application/json"})
            resposta.raise_for_status()
            serie = pd.DataFrame(resposta.json())
            serie["data"] = pd.to_datetime(serie["data"], dayfirst=True)
            serie["valor"] = pd.to_numeric(serie["valor"], errors="coerce")
            serie["periodo"] = serie["data"].dt.to_period("M").dt.to_timestamp()
            serie = serie.groupby("periodo", as_index=False)["valor"].mean()
            serie["serie"] = nome
            serie["codigo_sgs"] = codigo
            frames.append(serie)
        except Exception as erro:  # noqa: BLE001
            erros.append(f"Série {codigo} ({nome}): {erro.__class__.__name__}")
    dados = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return dados, erros


# ---------------------------------------------------------------------------
# Sidebar: fonte de dados e filtros
# ---------------------------------------------------------------------------

preparar_banco()

with st.sidebar:
    st.markdown("### Sistema Financeiro e Crédito")
    st.caption("Projeto G1 · Análise e Visualização de Dados com Python")

    with st.expander("Fonte de dados", expanded=False):
        arquivo = st.file_uploader(
            "Enviar outro CSV com a mesma estrutura", type=["csv"],
            help="Opcional. Se nenhum arquivo for enviado, a base oficial do projeto é utilizada.",
        )

try:
    df, relatorio = carregar_base(arquivo.getvalue() if arquivo else None)
    fonte = arquivo.name if arquivo else CSV_PADRAO.name
except Exception as erro:  # noqa: BLE001
    st.sidebar.error(f"Arquivo inválido: {erro}. Usando a base padrão.")
    df, relatorio = carregar_base(None)
    fonte = CSV_PADRAO.name

FILTROS = ["f_anos", "f_meses", "f_regioes", "f_ufs", "f_modalidades", "f_riscos", "f_setores"]


def limpar_filtros() -> None:
    for chave in FILTROS:
        st.session_state.pop(chave, None)


with st.sidebar:
    st.markdown("#### Filtros")
    ano_min, ano_max = int(df["ano"].min()), int(df["ano"].max())
    anos_sel = st.slider("Ano", ano_min, ano_max, (ano_min, ano_max), key="f_anos")
    meses_sel = st.multiselect("Mês", list(MESES), format_func=lambda m: MESES[m],
                               placeholder="Todos", key="f_meses")
    regioes_disp = [r for r in ORDEM_REGIAO if r in df["regiao"].unique()] + \
                   sorted(set(df["regiao"].unique()) - set(ORDEM_REGIAO))
    regioes_sel = st.multiselect("Região", regioes_disp, placeholder="Todas", key="f_regioes")
    ufs_disp = sorted(df.loc[df["regiao"].isin(regioes_sel) if regioes_sel else slice(None), "uf"].unique())
    ufs_sel = st.multiselect("Estado (UF)", ufs_disp, placeholder="Todos", key="f_ufs")
    modalidades_sel = st.multiselect("Modalidade de crédito", sorted(df["modalidade_credito"].unique()),
                                     placeholder="Todas", key="f_modalidades")
    riscos_sel = st.multiselect("Risco de crédito", ORDEM_RISCO, placeholder="Todos", key="f_riscos")
    setores_sel = st.multiselect("Setor econômico", sorted(df["setor_economico"].unique()),
                                 placeholder="Todos", key="f_setores")
    st.button("Limpar filtros", on_click=limpar_filtros, use_container_width=True)

mascara = df["ano"].between(*anos_sel)
if meses_sel:
    mascara &= df["mes"].isin(meses_sel)
if regioes_sel:
    mascara &= df["regiao"].isin(regioes_sel)
if ufs_sel:
    mascara &= df["uf"].isin(ufs_sel)
if modalidades_sel:
    mascara &= df["modalidade_credito"].isin(modalidades_sel)
if riscos_sel:
    mascara &= df["risco_credito"].isin(riscos_sel)
if setores_sel:
    mascara &= df["setor_economico"].isin(setores_sel)
dff = df[mascara].copy()

with st.sidebar:
    st.caption(f"Registros selecionados: **{num(len(dff))}** de {num(len(df))}")
    st.caption(f"Fonte: {fonte}")


def exigir_dados() -> None:
    if dff.empty:
        st.warning("Nenhum registro atende aos filtros selecionados. Ajuste os filtros na barra lateral.")
        st.stop()


# ---------------------------------------------------------------------------
# Cálculos reutilizados
# ---------------------------------------------------------------------------

def calcular_kpis(d: pd.DataFrame) -> dict:
    por_modalidade = d.groupby("modalidade_credito", observed=True).agg(
        volume=("valor_credito", "sum"), clientes=("quantidade_clientes", "sum"), operacoes=("uf", "size"))
    por_regiao = d.groupby("regiao")["valor_credito"].sum()
    return {
        "volume": d["valor_credito"].sum(),
        "juros": d["taxa_juros"].mean(),
        "inad": d["inadimplencia_percentual"].mean(),
        "inad_ponderada": np.average(d["inadimplencia_percentual"], weights=d["valor_credito"]),
        "modalidade_top": por_modalidade["volume"].idxmax(),
        "modalidade_top_share": por_modalidade["volume"].max() / por_modalidade["volume"].sum() * 100,
        "modalidade_mais_clientes": por_modalidade["clientes"].idxmax(),
        "regiao_top": por_regiao.idxmax(),
        "regiao_top_share": por_regiao.max() / por_regiao.sum() * 100,
        "prazo": d["prazo_medio_pagamento"].mean(),
        "clientes": d["quantidade_clientes"].sum(),
        "atraso": d["valor_em_atraso"].sum(),
        "ticket": d["valor_credito"].sum() / d["quantidade_clientes"].sum(),
        "pct_alto": d["risco_alto"].mean() * 100,
        "renda": d["renda_media"].mean(),
    }


def variacao_anual(d: pd.DataFrame) -> dict | None:
    """Compara o último ano da seleção com o ano anterior (KPIs dinâmicos)."""
    anos = sorted(d["ano"].unique())
    if len(anos) < 2:
        return None
    atual, anterior = d[d["ano"] == anos[-1]], d[d["ano"] == anos[-2]]
    return {
        "ano": anos[-1], "ano_ant": anos[-2],
        "volume": (atual["valor_credito"].sum() / anterior["valor_credito"].sum() - 1) * 100,
        "juros": atual["taxa_juros"].mean() - anterior["taxa_juros"].mean(),
        "inad": atual["inadimplencia_percentual"].mean() - anterior["inadimplencia_percentual"].mean(),
        "prazo": atual["prazo_medio_pagamento"].mean() - anterior["prazo_medio_pagamento"].mean(),
        "clientes": (atual["quantidade_clientes"].sum() / anterior["quantidade_clientes"].sum() - 1) * 100,
    }


def serie_mensal(d: pd.DataFrame) -> pd.DataFrame:
    m = d.groupby("periodo").agg(
        volume=("valor_credito", "sum"), juros=("taxa_juros", "mean"),
        inad=("inadimplencia_percentual", "mean"), clientes=("quantidade_clientes", "sum"),
        atraso=("valor_em_atraso", "sum"),
    ).reset_index()
    return m


def indice_hhi(participacoes_pct: pd.Series) -> float:
    """Índice Herfindahl-Hirschman (0–10.000) da concentração do crédito."""
    return float((participacoes_pct ** 2).sum())


METRICAS = {
    "Volume de crédito": ("valor_credito", "sum", "R$"),
    "Taxa média de juros (%)": ("taxa_juros", "mean", "%"),
    "Inadimplência média (%)": ("inadimplencia_percentual", "mean", "%"),
    "Clientes atendidos": ("quantidade_clientes", "sum", "n"),
    "Valor estimado em atraso": ("valor_em_atraso", "sum", "R$"),
}

# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

def pagina_visao_geral() -> None:
    st.title("Sistema Financeiro e Crédito no Brasil")
    st.markdown("##### Análise de concessão de crédito, juros, inadimplência e risco · 2015 a 2024")

    with st.expander("Descrição do problema e perguntas orientadoras", expanded=True):
        c1, c2 = st.columns([1.15, 1])
        c1.markdown(
            """
            O crédito é um dos principais canais de transmissão da política econômica: ele influencia
            consumo, investimento, endividamento das famílias e o crescimento da atividade. Ao mesmo
            tempo, a expansão do crédito sem controle de risco eleva a **inadimplência** e pressiona o
            custo do dinheiro (**juros**).

            Este painel analisa uma base com **operações de crédito por estado, modalidade e setor**
            entre 2015 e 2024 para identificar onde o crédito se concentra, como evoluiu, quais
            segmentos apresentam maior risco e se existe relação entre juros e inadimplência.
            """
        )
        c2.markdown(
            """
            **Perguntas orientadoras**
            1. Quais regiões apresentam maior volume de crédito?
            2. Quais setores possuem maior inadimplência?
            3. Houve crescimento do crédito ao longo do tempo?
            4. Existe relação entre juros e inadimplência?
            5. Quais modalidades apresentam maior risco?
            6. Como o comportamento financeiro evoluiu?
            7. Quais estados possuem maior concentração bancária?
            """
        )

    exigir_dados()
    k = calcular_kpis(dff)
    v = variacao_anual(dff)
    sufixo = f" vs {v['ano_ant']}" if v else ""

    st.subheader("Indicadores-chave (KPIs)")
    c = st.columns(3)
    c[0].metric("Volume total de crédito", brl(k["volume"]),
                delta=f"{_br(v['volume'])}% em {v['ano']}{sufixo}" if v else None, border=True,
                help="Soma do valor concedido no período filtrado. A variação compara o último ano selecionado com o anterior.")
    c[1].metric("Taxa média de juros", pct(k["juros"]),
                delta=f"{_br(v['juros'])} p.p.{sufixo}" if v else None, delta_color="inverse", border=True,
                help="Média simples da taxa de juros (% a.a.) das operações.")
    c[2].metric("Índice médio de inadimplência", pct(k["inad"]),
                delta=f"{_br(v['inad'])} p.p.{sufixo}" if v else None, delta_color="inverse", border=True,
                help=f"Média simples. Ponderada pelo volume: {pct(k['inad_ponderada'])}.")
    c = st.columns(3)
    c[0].metric("Modalidade mais utilizada", k["modalidade_top"],
                delta=f"{_br(k['modalidade_top_share'], 1)}% do volume", delta_color="off", delta_arrow="off", border=True,
                help=f"Ranking por volume concedido. Por número de clientes: {k['modalidade_mais_clientes']}.")
    c[1].metric("Região com maior crédito", k["regiao_top"],
                delta=f"{_br(k['regiao_top_share'], 1)}% do volume", delta_color="off", delta_arrow="off", border=True)
    c[2].metric("Prazo médio de pagamento", f"{_br(k['prazo'], 1)} meses",
                delta=f"{_br(v['prazo'], 1)} meses{sufixo}" if v else None, delta_color="off", delta_arrow="off", border=True)
    c = st.columns(4)
    c[0].metric("Clientes atendidos", num(k["clientes"]), border=True)
    c[1].metric("Valor estimado em atraso", brl(k["atraso"]), border=True,
                help="Valor do crédito × percentual de inadimplência de cada operação.")
    c[2].metric("Ticket médio por cliente", brl(k["ticket"]), border=True)
    c[3].metric("Operações de risco alto", pct(k["pct_alto"], 1), border=True)

    st.subheader("Evolução do volume de crédito")
    mensal = serie_mensal(dff)
    mensal["media_movel"] = mensal["volume"].rolling(12, min_periods=3).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mensal["periodo"], y=mensal["volume"] / 1e6, name="Volume mensal",
                             mode="lines", line=dict(color="#9DB4D8", width=1.5)))
    fig.add_trace(go.Scatter(x=mensal["periodo"], y=mensal["media_movel"] / 1e6, name="Média móvel 12 meses",
                             mode="lines", line=dict(color=AZUL, width=3)))
    fig.update_yaxes(title="R$ milhões")
    st.plotly_chart(estilizar(fig, 380), key="vg_linha")

    c1, c2 = st.columns(2)
    reg = dff.groupby("regiao", as_index=False)["valor_credito"].sum().sort_values("valor_credito")
    reg["volume_mi"] = reg["valor_credito"] / 1e6
    fig = px.bar(reg, x="volume_mi", y="regiao", orientation="h", color="regiao",
                 color_discrete_map=CORES_REGIAO, title="Volume de crédito por região",
                 text=reg["valor_credito"].map(brl))
    fig.update_layout(xaxis_title="R$ milhões", yaxis_title=None)
    c1.plotly_chart(estilizar(fig, 360, legenda=False), key="vg_regiao")

    mod = dff.groupby("modalidade_credito", as_index=False)["valor_credito"].sum().sort_values("valor_credito")
    mod["volume_mi"] = mod["valor_credito"] / 1e6
    fig = px.bar(mod, x="volume_mi", y="modalidade_credito", orientation="h",
                 title="Volume de crédito por modalidade", text=mod["valor_credito"].map(brl),
                 color_discrete_sequence=[AZUL])
    fig.update_layout(xaxis_title="R$ milhões", yaxis_title=None)
    c2.plotly_chart(estilizar(fig, 360, legenda=False), key="vg_modalidade")

    st.subheader("Leitura dos indicadores")
    anual = dff.groupby("ano")["valor_credito"].sum()
    crescimento = (anual.iloc[-1] / anual.iloc[0] - 1) * 100 if len(anual) > 1 else 0
    caixa(
        f"No recorte selecionado foram concedidos <b>{brl(k['volume'])}</b> em crédito para "
        f"<b>{num(k['clientes'])}</b> clientes. A região <b>{k['regiao_top']}</b> lidera o volume "
        f"({_br(k['regiao_top_share'], 1)}% do total) e a modalidade com maior participação é "
        f"<b>{k['modalidade_top']}</b>. A taxa média de juros é de <b>{pct(k['juros'])}</b> e a "
        f"inadimplência média de <b>{pct(k['inad'])}</b>, o que representa cerca de "
        f"<b>{brl(k['atraso'])}</b> em valores com atraso estimado. "
        + (f"Entre {anual.index[0]} e {anual.index[-1]} o volume anual variou <b>{_br(crescimento)}%</b>." if len(anual) > 1 else "")
    )
    with st.expander("Tratamento aplicado à base"):
        st.markdown(
            f"""
            - Linhas originais: **{num(relatorio['linhas_originais'])}** · linhas após tratamento: **{num(relatorio['linhas_finais'])}**
            - Valores nulos encontrados: **{relatorio['valores_nulos']}** · duplicados removidos: **{relatorio['duplicados_removidos']}** · registros inválidos removidos: **{relatorio['registros_invalidos']}**
            - Outliers de valor sinalizados (regra IQR, mantidos na base): **{relatorio['outliers_sinalizados']}**
            - Período coberto: **{relatorio['periodo']}**
            - Atributos criados: período mensal, trimestre, nome do mês, valor em milhões, ticket médio por cliente,
              valor estimado em atraso, comprometimento de renda, faixas de juros, renda e prazo, indicador de risco alto.
            """
        )


def pagina_temporal() -> None:
    st.title("Evolução Temporal")
    st.caption("Séries mensais, crescimento anual, sazonalidade e tendência.")
    exigir_dados()

    escolha = st.radio("Indicador", list(METRICAS), horizontal=True, key="tmp_metrica")
    coluna, agregacao, unidade = METRICAS[escolha]
    divisor = 1e6 if unidade == "R$" else 1
    rotulo_eixo = "R$ milhões" if unidade == "R$" else ("%" if unidade == "%" else "Quantidade")

    comparar = st.toggle("Comparar por região", value=False)
    if comparar:
        serie = dff.groupby(["periodo", "regiao"], as_index=False)[coluna].agg(agregacao)
        serie[coluna] = serie[coluna] / divisor
        fig = px.line(serie, x="periodo", y=coluna, color="regiao", color_discrete_map=CORES_REGIAO,
                      title=f"{escolha} por região — série mensal")
    else:
        serie = dff.groupby("periodo", as_index=False)[coluna].agg(agregacao)
        serie[coluna] = serie[coluna] / divisor
        serie["mm12"] = serie[coluna].rolling(12, min_periods=3).mean()
        x_num = np.arange(len(serie))
        coef = np.polyfit(x_num, serie[coluna], 1) if len(serie) > 2 else (0, serie[coluna].mean())
        serie["tendencia"] = np.polyval(coef, x_num)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=serie["periodo"], y=serie[coluna], name="Mensal",
                                 line=dict(color="#9DB4D8", width=1.5)))
        fig.add_trace(go.Scatter(x=serie["periodo"], y=serie["mm12"], name="Média móvel 12m",
                                 line=dict(color=AZUL, width=3)))
        fig.add_trace(go.Scatter(x=serie["periodo"], y=serie["tendencia"], name="Tendência linear",
                                 line=dict(color="#D1495B", width=2, dash="dash")))
        fig.update_layout(title=f"{escolha} — série mensal")
    fig.update_yaxes(title=rotulo_eixo)
    fig.update_xaxes(title=None)
    st.plotly_chart(estilizar(fig, 420), key="tmp_linha")

    c1, c2 = st.columns(2)
    anual = dff.groupby("ano", as_index=False)[coluna].agg(agregacao)
    anual["valor"] = anual[coluna] / divisor
    anual["var"] = anual[coluna].pct_change() * 100 if agregacao == "sum" else anual[coluna].diff()
    texto_var = anual["var"].map(lambda x: "" if pd.isna(x) else (f"{x:+.1f}%" if agregacao == "sum" else f"{x:+.2f} p.p.")
                                 .replace(".", ","))
    fig = px.bar(anual, x="ano", y="valor", text=texto_var, title=f"{escolha} por ano (variação anual)",
                 color_discrete_sequence=[AZUL])
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_title=rotulo_eixo, xaxis_title=None, xaxis=dict(dtick=1))
    c1.plotly_chart(estilizar(fig, 380, legenda=False), key="tmp_anual")

    saz = dff.groupby("mes", as_index=False)[coluna].agg(agregacao)
    saz[coluna] = saz[coluna] / divisor / (dff["ano"].nunique() if agregacao == "sum" else 1)
    saz["mes_nome"] = saz["mes"].map(MESES)
    fig = px.bar(saz, x="mes_nome", y=coluna, title="Sazonalidade — média por mês do ano",
                 color_discrete_sequence=["#2E86AB"])
    fig.add_hline(y=saz[coluna].mean(), line_dash="dot", line_color="#D1495B",
                  annotation_text="média", annotation_position="top left")
    fig.update_layout(yaxis_title=rotulo_eixo, xaxis_title=None)
    c2.plotly_chart(estilizar(fig, 380, legenda=False), key="tmp_saz")

    st.subheader("Heatmap mensal")
    matriz = dff.pivot_table(index="ano", columns="mes", values=coluna, aggfunc=agregacao) / divisor
    matriz.columns = [MESES[m] for m in matriz.columns]
    fig = px.imshow(matriz, text_auto=".1f", aspect="auto", color_continuous_scale="Blues",
                    labels=dict(x="Mês", y="Ano", color=rotulo_eixo),
                    title=f"{escolha} — ano × mês")
    fig.update_yaxes(dtick=1)
    st.plotly_chart(estilizar(fig, 460, legenda=False), key="tmp_heat")

    # Interpretação
    mensal = dff.groupby("periodo")[coluna].agg(agregacao) / divisor
    anual_s = anual.set_index("ano")["valor"]
    texto = []
    if len(anual_s) > 1:
        if agregacao == "sum":
            n = len(anual_s) - 1
            cagr = ((anual_s.iloc[-1] / anual_s.iloc[0]) ** (1 / n) - 1) * 100
            texto.append(f"Entre {anual_s.index[0]} e {anual_s.index[-1]}, o indicador passou de "
                         f"<b>{_br(anual_s.iloc[0])}</b> para <b>{_br(anual_s.iloc[-1])}</b> ({rotulo_eixo}), "
                         f"crescimento médio anual composto (CAGR) de <b>{_br(cagr)}%</b>.")
        else:
            texto.append(f"Entre {anual_s.index[0]} e {anual_s.index[-1]}, a média passou de "
                         f"<b>{_br(anual_s.iloc[0])}</b> para <b>{_br(anual_s.iloc[-1])}</b> "
                         f"({_br(anual_s.iloc[-1] - anual_s.iloc[0])} p.p.).")
        texto.append(f"O maior valor anual ocorreu em <b>{anual_s.idxmax()}</b> e o menor em <b>{anual_s.idxmin()}</b>.")
    if len(mensal) > 2:
        inclinacao = np.polyfit(np.arange(len(mensal)), mensal.values, 1)[0] * 12
        cv = mensal.std() / mensal.mean() * 100 if mensal.mean() else 0
        texto.append(f"A tendência linear indica variação de <b>{_br(inclinacao)}</b> {rotulo_eixo} por ano; "
                     f"o coeficiente de variação mensal é de <b>{_br(cv, 1)}%</b>, "
                     + ("o que indica série estável, sem tendência estrutural relevante."
                        if abs(inclinacao) < 0.02 * abs(mensal.mean()) else "indicando movimento direcional no período."))
        texto.append(f"Na sazonalidade, o mês com maior média é <b>{saz.loc[saz[coluna].idxmax(), 'mes_nome']}</b> "
                     f"e o de menor média é <b>{saz.loc[saz[coluna].idxmin(), 'mes_nome']}</b>.")
    caixa(" ".join(texto))


def pagina_regional() -> None:
    st.title("Análise Regional e Concentração")
    st.caption("Comparação entre regiões, ranking de estados, mapa interativo e regiões críticas.")
    exigir_dados()
    media_nac = dff["inadimplencia_percentual"].mean()

    reg = dff.groupby("regiao").agg(
        volume=("valor_credito", "sum"), inad=("inadimplencia_percentual", "mean"),
        juros=("taxa_juros", "mean"), operacoes=("uf", "size"), clientes=("quantidade_clientes", "sum"),
        renda=("renda_media", "mean"),
    ).reset_index()
    reg["participacao"] = reg["volume"] / reg["volume"].sum() * 100
    reg["volume_por_operacao"] = reg["volume"] / reg["operacoes"]
    reg["volume_mi"] = reg["volume"] / 1e6

    c1, c2 = st.columns(2)
    fig = px.bar(reg.sort_values("volume", ascending=False), x="regiao", y="volume_mi", color="regiao",
                 color_discrete_map=CORES_REGIAO, title="Volume de crédito por região",
                 text=reg.sort_values("volume", ascending=False)["participacao"].map(lambda x: f"{_br(x, 1)}%"))
    fig.update_layout(yaxis_title="R$ milhões", xaxis_title=None)
    c1.plotly_chart(estilizar(fig, 380, legenda=False), key="rg_volume")

    fig = px.bar(reg.sort_values("inad", ascending=False), x="regiao", y="inad", color="regiao",
                 color_discrete_map=CORES_REGIAO, title="Inadimplência média por região",
                 text=reg.sort_values("inad", ascending=False)["inad"].map(lambda x: pct(x)))
    fig.add_hline(y=media_nac, line_dash="dot", line_color="#D1495B",
                  annotation_text=f"média {pct(media_nac)}", annotation_position="top right")
    fig.update_layout(yaxis_title="%", xaxis_title=None, yaxis_range=[0, reg["inad"].max() * 1.2])
    c2.plotly_chart(estilizar(fig, 380, legenda=False), key="rg_inad")

    st.subheader("Concentração do crédito por estado")
    uf = dff.groupby(["uf", "regiao"]).agg(
        volume=("valor_credito", "sum"), inad=("inadimplencia_percentual", "mean"),
        juros=("taxa_juros", "mean"), clientes=("quantidade_clientes", "sum"),
        operacoes=("mes", "size"), pct_alto=("risco_alto", "mean"), atraso=("valor_em_atraso", "sum"),
    ).reset_index()
    uf["participacao"] = uf["volume"] / uf["volume"].sum() * 100
    uf = uf.sort_values("volume", ascending=False)
    uf["volume_mi"] = uf["volume"] / 1e6
    hhi = indice_hhi(uf["participacao"])
    top3 = uf["participacao"].head(3).sum()
    nivel = "baixa" if hhi < 1500 else ("moderada" if hhi < 2500 else "alta")

    m = st.columns(4)
    m[0].metric("Estado com maior volume", uf.iloc[0]["uf"], f"{_br(uf.iloc[0]['participacao'], 1)}% do total",
                delta_color="off", delta_arrow="off", border=True)
    m[1].metric("Participação dos 3 maiores (CR3)", pct(top3, 1), border=True)
    m[2].metric("Índice HHI", num(hhi), f"concentração {nivel}", delta_color="off", delta_arrow="off", border=True,
                help="Herfindahl-Hirschman: soma dos quadrados das participações. <1.500 baixa; 1.500–2.500 moderada; >2.500 alta.")
    m[3].metric("Estados na seleção", num(uf["uf"].nunique()), border=True)

    c1, c2 = st.columns([1.1, 1])
    fig = px.bar(uf, x="uf", y="volume_mi", color="regiao", color_discrete_map=CORES_REGIAO,
                 title="Ranking de estados por volume de crédito",
                 hover_data={"participacao": ":.2f", "inad": ":.2f", "operacoes": True},
                 labels={"volume_mi": "Volume (R$ mi)", "participacao": "Participação (%)",
                         "inad": "Inadimplência (%)", "operacoes": "Operações", "uf": "UF", "regiao": "Região"})
    fig.update_layout(yaxis_title="R$ milhões", xaxis_title=None)
    c1.plotly_chart(estilizar(fig, 430), key="rg_uf")

    mapa = uf.copy()
    mapa["lat"] = mapa["uf"].map(lambda u: COORD_UF.get(u, (np.nan, np.nan))[0])
    mapa["lon"] = mapa["uf"].map(lambda u: COORD_UF.get(u, (np.nan, np.nan))[1])
    mapa = mapa.dropna(subset=["lat"])
    mapa["volume_fmt"] = mapa["volume"].map(brl)
    fig = px.scatter_geo(
        mapa, lat="lat", lon="lon", size="volume", color="inad", hover_name="uf",
        hover_data={"volume_fmt": True, "inad": ":.2f", "juros": ":.2f", "lat": False, "lon": False, "volume": False},
        color_continuous_scale="RdYlGn_r", size_max=38, title="Mapa — volume (tamanho) e inadimplência (cor)",
        labels={"inad": "Inadimplência (%)", "volume_fmt": "Volume", "juros": "Juros (%)"},
    )
    fig.update_geos(scope="south america", fitbounds="locations", showcountries=True,
                    countrycolor="#BBBBBB", showland=True, landcolor="#F4F6F8", showocean=True, oceancolor="#E8F1FA")
    c2.plotly_chart(estilizar(fig, 430, legenda=False), key="rg_mapa")

    st.subheader("Estados críticos")
    st.caption("Escore de criticidade = média dos z-scores de inadimplência, juros e participação de operações de risco alto.")
    crit = uf.copy()
    for col in ["inad", "juros", "pct_alto"]:
        desvio = crit[col].std(ddof=0)
        crit[f"z_{col}"] = (crit[col] - crit[col].mean()) / desvio if desvio else 0
    crit["escore"] = crit[["z_inad", "z_juros", "z_pct_alto"]].mean(axis=1)
    crit["situacao"] = np.where(crit["escore"] > 0.5, "Crítico",
                                np.where(crit["escore"] > 0, "Atenção", "Adequado"))
    crit = crit.sort_values("escore", ascending=False)
    tabela = crit[["uf", "regiao", "inad", "juros", "pct_alto", "atraso", "participacao", "escore", "situacao"]].copy()
    tabela["pct_alto"] *= 100
    st.dataframe(
        tabela, hide_index=True,
        column_config={
            "uf": "UF", "regiao": "Região",
            "inad": st.column_config.NumberColumn("Inadimplência (%)", format="%.2f"),
            "juros": st.column_config.NumberColumn("Juros (%)", format="%.2f"),
            "pct_alto": st.column_config.NumberColumn("Risco alto (%)", format="%.1f"),
            "atraso": st.column_config.NumberColumn("Valor em atraso (R$)", format="localized"),
            "participacao": st.column_config.ProgressColumn("Participação no volume", format="%.2f%%",
                                                            min_value=0, max_value=float(tabela["participacao"].max())),
            "escore": st.column_config.NumberColumn("Escore", format="%.2f"),
            "situacao": "Situação",
        },
    )

    reg_top = reg.sort_values("volume", ascending=False).iloc[0]
    reg_inad = reg.sort_values("inad", ascending=False).iloc[0]
    criticos = crit.loc[crit["situacao"] == "Crítico", "uf"].tolist()
    caixa(
        f"A região <b>{reg_top['regiao']}</b> concentra <b>{_br(reg_top['participacao'], 1)}%</b> do volume de crédito. "
        f"Parte dessa liderança decorre do maior número de operações registradas na região "
        f"({num(reg_top['operacoes'])}); o valor médio por operação varia pouco entre regiões "
        f"(de {brl(reg['volume_por_operacao'].min())} a {brl(reg['volume_por_operacao'].max())}). "
        f"A maior inadimplência média está no <b>{reg_inad['regiao']}</b> ({pct(reg_inad['inad'])}), contra média geral de "
        f"{pct(media_nac)}. No recorte por estado, <b>{uf.iloc[0]['uf']}</b> lidera o volume e os três maiores estados somam "
        f"{pct(top3, 1)} do crédito; o HHI de {num(hhi)} indica concentração <b>{nivel}</b>. "
        + (f"Estados classificados como críticos: <b>{', '.join(criticos)}</b>." if criticos
           else "Nenhum estado ultrapassou o limite de criticidade definido.")
    )


def pagina_modalidades() -> None:
    st.title("Modalidades, Setores e Risco de Crédito")
    st.caption("Comparação entre modalidades, análise setorial e evolução do perfil de risco.")
    exigir_dados()

    mod = dff.groupby("modalidade_credito").agg(
        volume=("valor_credito", "sum"), clientes=("quantidade_clientes", "sum"),
        inad=("inadimplencia_percentual", "mean"), juros=("taxa_juros", "mean"),
        pct_alto=("risco_alto", "mean"), prazo=("prazo_medio_pagamento", "mean"),
    ).reset_index()
    mod["pct_alto"] *= 100
    mod["volume_mi"] = mod["volume"] / 1e6

    c1, c2 = st.columns(2)
    dados = mod.sort_values("volume", ascending=False)
    fig = px.bar(dados, x="modalidade_credito", y="volume_mi", title="Volume de crédito por modalidade",
                 text=dados["volume"].map(brl), color_discrete_sequence=[AZUL])
    fig.update_layout(yaxis_title="R$ milhões", xaxis_title=None)
    c1.plotly_chart(estilizar(fig, 380, legenda=False), key="md_volume")

    dados = mod.sort_values("inad", ascending=False)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=dados["modalidade_credito"], y=dados["inad"], name="Inadimplência média (%)",
                         marker_color="#D1495B", text=dados["inad"].map(pct)), secondary_y=False)
    fig.add_trace(go.Scatter(x=dados["modalidade_credito"], y=dados["pct_alto"], name="Operações de risco alto (%)",
                             mode="lines+markers", line=dict(color=AZUL, width=3)), secondary_y=True)
    fig.update_yaxes(title_text="Inadimplência (%)", secondary_y=False, range=[0, dados["inad"].max() * 1.25])
    fig.update_yaxes(title_text="Risco alto (%)", secondary_y=True, range=[0, 100])
    fig.update_layout(title="Risco por modalidade")
    c2.plotly_chart(estilizar(fig, 380), key="md_risco")

    st.subheader("Evolução do risco de crédito")
    risco = dff.groupby(["ano", "risco_credito"], observed=True)["valor_credito"].sum().reset_index()
    risco["participacao"] = risco["valor_credito"] / risco.groupby("ano")["valor_credito"].transform("sum") * 100
    c1, c2 = st.columns(2)
    fig = px.area(risco, x="ano", y="participacao", color="risco_credito", color_discrete_map=CORES_RISCO,
                  category_orders={"risco_credito": ORDEM_RISCO}, title="Participação do volume por nível de risco (%)")
    fig.update_layout(yaxis_title="% do volume", xaxis_title=None, xaxis=dict(dtick=1))
    c1.plotly_chart(estilizar(fig, 380), key="md_area")

    inad_risco = dff.groupby(["ano", "risco_credito"], observed=True)["inadimplencia_percentual"].mean().reset_index()
    fig = px.line(inad_risco, x="ano", y="inadimplencia_percentual", color="risco_credito", markers=True,
                  color_discrete_map=CORES_RISCO, category_orders={"risco_credito": ORDEM_RISCO},
                  title="Inadimplência média por nível de risco")
    fig.update_layout(yaxis_title="%", xaxis_title=None, xaxis=dict(dtick=1))
    c2.plotly_chart(estilizar(fig, 380), key="md_linha_risco")

    st.subheader("Análise por setor econômico")
    setor = dff.groupby("setor_economico").agg(
        inad=("inadimplencia_percentual", "mean"), atraso=("valor_em_atraso", "sum"),
        volume=("valor_credito", "sum"), juros=("taxa_juros", "mean"),
    ).reset_index().sort_values("inad", ascending=False)
    c1, c2 = st.columns(2)
    fig = px.bar(setor, x="setor_economico", y="inad", text=setor["inad"].map(pct),
                 title="Inadimplência média por setor", color="setor_economico", color_discrete_sequence=PALETA)
    fig.update_layout(yaxis_title="%", xaxis_title=None, yaxis_range=[0, setor["inad"].max() * 1.2])
    c1.plotly_chart(estilizar(fig, 360, legenda=False), key="st_inad")

    matriz = dff.pivot_table(index="setor_economico", columns="modalidade_credito",
                             values="inadimplencia_percentual", aggfunc="mean")
    fig = px.imshow(matriz, text_auto=".2f", color_continuous_scale="Reds", aspect="auto",
                    title="Inadimplência média (%) — setor × modalidade",
                    labels=dict(x="Modalidade", y="Setor", color="%"))
    c2.plotly_chart(estilizar(fig, 360, legenda=False), key="st_heat")

    st.subheader("Distribuição da inadimplência (Seaborn)")
    fig_mpl, ax = plt.subplots(figsize=(11, 4.2))
    sns.boxplot(data=dff, x="modalidade_credito", y="inadimplencia_percentual", hue="risco_credito",
                hue_order=ORDEM_RISCO, palette=CORES_RISCO, ax=ax, fliersize=2, linewidth=1)
    ax.set_xlabel("")
    ax.set_ylabel("Inadimplência (%)")
    ax.set_title("Inadimplência por modalidade e nível de risco", color=AZUL, fontsize=12, loc="left")
    sns.move_legend(ax, "upper center", bbox_to_anchor=(0.5, -0.1), ncol=3, title="Risco de crédito", frameon=False)
    sns.despine()
    fig_mpl.tight_layout()
    st.pyplot(fig_mpl)
    plt.close(fig_mpl)

    top_vol = mod.sort_values("volume", ascending=False).iloc[0]
    top_inad = mod.sort_values("inad", ascending=False).iloc[0]
    top_alto = mod.sort_values("pct_alto", ascending=False).iloc[0]
    amplitude = mod["inad"].max() - mod["inad"].min()
    setor_top, setor_low = setor.iloc[0], setor.iloc[-1]
    ini = risco[risco["ano"] == risco["ano"].min()].set_index("risco_credito")["participacao"]
    fim = risco[risco["ano"] == risco["ano"].max()].set_index("risco_credito")["participacao"]
    var_alto = fim.get("Alto", 0) - ini.get("Alto", 0)
    caixa(
        f"<b>{top_vol['modalidade_credito']}</b> é a modalidade com maior volume ({brl(top_vol['volume'])}). "
        f"A maior inadimplência média está em <b>{top_inad['modalidade_credito']}</b> ({pct(top_inad['inad'])}) e a maior "
        f"proporção de operações classificadas como risco alto em <b>{top_alto['modalidade_credito']}</b> "
        f"({_br(top_alto['pct_alto'], 1)}%). A diferença entre a modalidade mais e a menos inadimplente é de "
        f"{_br(amplitude)} p.p., o que indica risco relativamente homogêneo entre produtos. "
        f"Entre os setores, <b>{setor_top['setor_economico']}</b> tem a maior inadimplência ({pct(setor_top['inad'])}) e "
        f"<b>{setor_low['setor_economico']}</b> a menor ({pct(setor_low['inad'])}). "
        f"A participação do risco alto no volume variou <b>{_br(var_alto, 1)} p.p.</b> entre o primeiro e o último ano da seleção."
    )


def pagina_correlacao() -> None:
    st.title("Juros × Inadimplência")
    st.caption("Correlação estatística entre custo do crédito, inadimplência e demais variáveis financeiras.")
    exigir_dados()

    c1, c2 = st.columns([1, 1])
    nivel = c1.radio("Nível de análise", ["Operações individuais", "Médias mensais"], horizontal=True)
    cor = c2.radio("Colorir por", ["risco_credito", "modalidade_credito", "regiao"], horizontal=True,
                   format_func={"risco_credito": "Risco", "modalidade_credito": "Modalidade", "regiao": "Região"}.get)

    if nivel == "Médias mensais":
        base = dff.groupby("periodo").agg(taxa_juros=("taxa_juros", "mean"),
                                          inadimplencia_percentual=("inadimplencia_percentual", "mean")).reset_index()
        base[cor] = "Média mensal"
    else:
        base = dff

    x, y = base["taxa_juros"].to_numpy(), base["inadimplencia_percentual"].to_numpy()
    if len(base) < 3:
        st.info("São necessários ao menos 3 pontos para calcular a correlação.")
        return
    r, p_r = stats.pearsonr(x, y)
    rho, p_rho = stats.spearmanr(x, y)
    coef = np.polyfit(x, y, 1)

    m = st.columns(4)
    m[0].metric("Correlação de Pearson (r)", _br(r, 3), forca_correlacao(r), delta_color="off", delta_arrow="off", border=True)
    m[1].metric("p-valor (Pearson)", f"{p_r:.4f}".replace(".", ","),
                "significativo a 5%" if p_r < 0.05 else "não significativo", delta_color="off", delta_arrow="off", border=True)
    m[2].metric("Correlação de Spearman (ρ)", _br(rho, 3), forca_correlacao(rho), delta_color="off", delta_arrow="off", border=True)
    m[3].metric("R² da reta", _br(r ** 2, 4), border=True,
                help="Proporção da variação da inadimplência explicada linearmente pelos juros.")

    fig = px.scatter(base, x="taxa_juros", y="inadimplencia_percentual", color=cor, opacity=0.55,
                     color_discrete_map=CORES_RISCO if cor == "risco_credito" else (CORES_REGIAO if cor == "regiao" else None),
                     color_discrete_sequence=PALETA, title="Dispersão: taxa de juros × inadimplência",
                     labels={"taxa_juros": "Taxa de juros (% a.a.)", "inadimplencia_percentual": "Inadimplência (%)"})
    xs = np.linspace(x.min(), x.max(), 50)
    fig.add_trace(go.Scatter(x=xs, y=np.polyval(coef, xs), mode="lines", name="Reta de regressão",
                             line=dict(color="#111111", width=3, dash="dash")))
    st.plotly_chart(estilizar(fig, 460), key="cr_scatter")

    c1, c2 = st.columns(2)
    faixa = dff.groupby("faixa_juros", observed=True).agg(
        inad=("inadimplencia_percentual", "mean"), operacoes=("uf", "size")).reset_index()
    fig = px.bar(faixa, x="faixa_juros", y="inad", text=faixa["inad"].map(pct),
                 title="Inadimplência média por faixa de juros", color_discrete_sequence=["#D1495B"],
                 hover_data={"operacoes": True})
    fig.update_layout(yaxis_title="%", xaxis_title="Faixa de juros", yaxis_range=[0, faixa["inad"].max() * 1.2])
    c1.plotly_chart(estilizar(fig, 400, legenda=False), key="cr_faixa")

    variaveis = {
        "taxa_juros": "Juros", "inadimplencia_percentual": "Inadimplência", "valor_credito": "Valor",
        "quantidade_clientes": "Clientes", "renda_media": "Renda", "prazo_medio_pagamento": "Prazo",
        "ticket_medio_cliente": "Ticket médio",
    }
    corr = dff[list(variaveis)].rename(columns=variaveis).corr()
    fig_mpl, ax = plt.subplots(figsize=(6.4, 5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1, center=0, square=True,
                linewidths=0.5, cbar_kws={"shrink": 0.8}, ax=ax, annot_kws={"size": 8})
    ax.set_title("Matriz de correlação (Pearson)", color=AZUL, fontsize=12, loc="left")
    fig_mpl.tight_layout()
    c2.pyplot(fig_mpl)
    plt.close(fig_mpl)

    corr_sem_diag = corr.where(~np.eye(len(corr), dtype=bool)).abs().stack()
    par = corr_sem_diag.idxmax()
    caixa(
        f"A correlação de Pearson entre taxa de juros e inadimplência é <b>{_br(r, 3)}</b> (relação "
        f"<b>{forca_correlacao(r)}</b>, p-valor {f'{p_r:.4f}'.replace('.', ',')}), e a de Spearman é {_br(rho, 3)}. "
        f"O R² de {_br(r ** 2, 4)} mostra que os juros explicam uma parcela "
        f"{'mínima' if r ** 2 < 0.05 else 'relevante'} da variação da inadimplência. "
        f"A inclinação da reta indica que cada 1 p.p. adicional de juros está associado a "
        f"{_br(coef[0], 4)} p.p. de inadimplência. "
        + ("Na base analisada não há evidência de que juros mais altos estejam associados a maior inadimplência; "
           "o risco parece depender de outros fatores não observados (perfil do tomador, garantias, ciclo econômico). "
           if abs(r) < 0.1 else "Há indícios de associação entre as variáveis, que devem ser investigados com controles adicionais. ")
        + f"Na matriz de correlação, o par com maior associação absoluta é <b>{par[0]} × {par[1]}</b> "
          f"({_br(corr.loc[par[0], par[1]], 2)})."
    )


def pagina_bcb() -> None:
    st.title("Indicadores Reais do Banco Central (API)")
    st.caption("Integração de múltiplas fontes: API SGS/BCB (Requests) + CSV do projeto + banco SQLite.")
    exigir_dados()

    st.markdown(
        "As séries oficiais do **Sistema Gerenciador de Séries Temporais (SGS)** do Banco Central são consultadas "
        "em tempo real e comparadas com os indicadores da base simulada. Os dados obtidos são gravados na tabela "
        "`indicadores_bcb` do banco SQLite, permitindo uso posterior mesmo sem conexão."
    )
    ini = dff["data"].min().strftime("%d/%m/%Y")
    fim = dff["data"].max().strftime("%d/%m/%Y")
    if st.button("Atualizar dados da API", type="primary"):
        buscar_series_bcb.clear()

    dados, erros = buscar_series_bcb(ini, fim)
    origem = "API do Banco Central (tempo real)"
    if not dados.empty:
        salvar_tabela(dados.assign(periodo=dados["periodo"].dt.strftime("%Y-%m-%d"),
                                   atualizado_em=datetime.now().strftime("%Y-%m-%d %H:%M")), "indicadores_bcb")
    else:
        try:
            dados = consultar("SELECT * FROM indicadores_bcb")
            dados["periodo"] = pd.to_datetime(dados["periodo"])
            origem = "cache local do banco SQLite (API indisponível no momento)"
        except Exception:  # noqa: BLE001
            dados = pd.DataFrame()
    if erros:
        with st.expander("Avisos da consulta à API"):
            for e in erros:
                st.write("- " + e)
    if dados.empty:
        st.warning("Não foi possível obter as séries do Banco Central agora e não há cache local. "
                   "Verifique a conexão e clique em 'Atualizar dados da API'.")
        return
    st.success(f"Fonte dos indicadores oficiais: {origem}.")

    pivot = dados.pivot_table(index="periodo", columns="serie", values="valor").reset_index()
    sim = serie_mensal(dff).rename(columns={"juros": "juros_sim", "inad": "inad_sim", "volume": "volume_sim"})
    comb = sim.merge(pivot, on="periodo", how="inner")

    nome_selic, nome_inad, nome_saldo = SERIES_BCB[4189], SERIES_BCB[21082], SERIES_BCB[20539]
    ult = pivot.dropna(how="all", subset=[c for c in pivot.columns if c != "periodo"]).iloc[-1]
    m = st.columns(3)
    if nome_selic in pivot:
        m[0].metric(f"Selic — {ult['periodo']:%m/%Y}", pct(ult[nome_selic]), border=True)
    if nome_inad in pivot:
        m[1].metric(f"Inadimplência SFN — {ult['periodo']:%m/%Y}", pct(ult[nome_inad]), border=True)
    if nome_saldo in pivot:
        m[2].metric(f"Saldo da carteira — {ult['periodo']:%m/%Y}", brl(ult[nome_saldo] * 1e6), border=True)

    c1, c2 = st.columns(2)
    if nome_selic in comb:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=comb["periodo"], y=comb[nome_selic], name="Selic real (BCB)",
                                 line=dict(color=AZUL, width=3)), secondary_y=False)
        fig.add_trace(go.Scatter(x=comb["periodo"], y=comb["juros_sim"], name="Juros médio da base",
                                 line=dict(color="#F2A541", width=1.5)), secondary_y=True)
        fig.update_yaxes(title_text="Selic (% a.a.)", secondary_y=False)
        fig.update_yaxes(title_text="Juros da base (%)", secondary_y=True)
        fig.update_layout(title="Selic oficial × juros médio da base")
        c1.plotly_chart(estilizar(fig, 400), key="bcb_selic")
    if nome_inad in comb:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=comb["periodo"], y=comb[nome_inad], name="Inadimplência SFN (BCB)",
                                 line=dict(color="#D1495B", width=3)), secondary_y=False)
        fig.add_trace(go.Scatter(x=comb["periodo"], y=comb["inad_sim"], name="Inadimplência da base",
                                 line=dict(color="#6C757D", width=1.5)), secondary_y=True)
        fig.update_yaxes(title_text="SFN (%)", secondary_y=False)
        fig.update_yaxes(title_text="Base (%)", secondary_y=True)
        fig.update_layout(title="Inadimplência oficial × inadimplência da base")
        c2.plotly_chart(estilizar(fig, 400), key="bcb_inad")

    textos = []
    if nome_selic in comb and len(comb) > 3:
        r1 = comb[[nome_selic, "juros_sim"]].corr().iloc[0, 1]
        textos.append(f"A Selic variou entre {pct(comb[nome_selic].min())} e {pct(comb[nome_selic].max())} no período; "
                      f"a correlação com os juros médios da base é {_br(r1, 3)} ({forca_correlacao(r1)}).")
    if nome_inad in comb and len(comb) > 3:
        r2 = comb[[nome_inad, "inad_sim"]].corr().iloc[0, 1]
        textos.append(f"A inadimplência oficial do SFN oscilou entre {pct(comb[nome_inad].min())} e "
                      f"{pct(comb[nome_inad].max())}, patamar bem inferior ao da base simulada (média {pct(dff['inadimplencia_percentual'].mean())}); "
                      f"a correlação entre as duas séries é {_br(r2, 3)} ({forca_correlacao(r2)}).")
    textos.append("Como a base do projeto é simulada, a comparação serve para contextualizar os resultados com o "
                  "cenário macroeconômico real e evidenciar que os níveis da simulação não reproduzem o ciclo de juros observado.")
    caixa(" ".join(textos))
    with st.expander("Dados obtidos da API"):
        st.dataframe(pivot, hide_index=True)


def pagina_exploracao() -> None:
    st.title("Tabela Dinâmica e Exploração dos Dados")
    st.caption("Monte cruzamentos personalizados e exporte os resultados.")
    exigir_dados()

    dimensoes = {
        "Ano": "ano", "Mês": "mes_nome", "Trimestre": "ano_trimestre", "Região": "regiao", "UF": "uf",
        "Modalidade": "modalidade_credito", "Risco": "risco_credito", "Setor": "setor_economico",
        "Faixa de juros": "faixa_juros", "Faixa de renda": "faixa_renda", "Faixa de prazo": "faixa_prazo",
    }
    medidas = {
        "Valor do crédito": "valor_credito", "Taxa de juros": "taxa_juros",
        "Inadimplência (%)": "inadimplencia_percentual", "Clientes": "quantidade_clientes",
        "Renda média": "renda_media", "Prazo médio": "prazo_medio_pagamento",
        "Valor em atraso": "valor_em_atraso", "Ticket médio por cliente": "ticket_medio_cliente",
    }
    agregacoes = {"Soma": "sum", "Média": "mean", "Mediana": "median", "Máximo": "max", "Mínimo": "min", "Contagem": "count"}

    c = st.columns(4)
    linhas = c[0].selectbox("Linhas", list(dimensoes), index=3)
    colunas = c[1].selectbox("Colunas", ["(nenhuma)"] + list(dimensoes), index=7)
    medida = c[2].selectbox("Medida", list(medidas), index=0)
    agg = c[3].selectbox("Agregação", list(agregacoes), index=0 if medida in ("Valor do crédito", "Clientes", "Valor em atraso") else 1)

    if colunas != "(nenhuma)" and colunas == linhas:
        st.info("Escolha dimensões diferentes para linhas e colunas.")
        return
    tabela = pd.pivot_table(
        dff, index=dimensoes[linhas], columns=None if colunas == "(nenhuma)" else dimensoes[colunas],
        values=medidas[medida], aggfunc=agregacoes[agg], margins=True, margins_name="Total", observed=True,
    )
    if isinstance(tabela, pd.Series):
        tabela = tabela.to_frame(medida)
    if dimensoes[linhas] == "mes_nome":
        ordem = [MESES[i] for i in range(1, 13) if MESES[i] in tabela.index] + ["Total"]
        tabela = tabela.reindex(ordem)
    casas = 0 if medidas[medida] in ("valor_credito", "quantidade_clientes", "valor_em_atraso") or agg == "Contagem" else 2
    estilo = tabela.style.format(lambda v: _br(v, casas) if pd.notna(v) else "-")
    if len(tabela) > 1:
        corpo = tabela.drop(index="Total", errors="ignore")
        corpo = corpo.drop(columns="Total", errors="ignore") if isinstance(corpo, pd.DataFrame) else corpo
        estilo = estilo.background_gradient(cmap="Blues", subset=pd.IndexSlice[corpo.index, corpo.columns])
    st.dataframe(estilo)
    st.download_button("Baixar tabela dinâmica (CSV)", tabela.to_csv(sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="tabela_dinamica.csv", mime="text/csv")

    st.subheader("Dados filtrados")
    colunas_exibir = ["data", "regiao", "uf", "modalidade_credito", "setor_economico", "risco_credito",
                      "valor_credito", "taxa_juros", "inadimplencia_percentual", "quantidade_clientes",
                      "renda_media", "prazo_medio_pagamento", "ticket_medio_cliente", "valor_em_atraso"]
    st.dataframe(
        dff[colunas_exibir], hide_index=True, height=360,
        column_config={
            "data": st.column_config.DateColumn("Data", format="MM/YYYY"),
            "valor_credito": st.column_config.NumberColumn("Valor (R$)", format="localized"),
            "taxa_juros": st.column_config.NumberColumn("Juros (%)", format="%.2f"),
            "inadimplencia_percentual": st.column_config.NumberColumn("Inadimpl. (%)", format="%.2f"),
            "ticket_medio_cliente": st.column_config.NumberColumn("Ticket médio (R$)", format="localized"),
            "valor_em_atraso": st.column_config.NumberColumn("Em atraso (R$)", format="localized"),
        },
    )
    st.download_button("Baixar dados filtrados (CSV)",
                       dff[colunas_exibir].to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="dados_filtrados.csv", mime="text/csv")
    with st.expander("Estatísticas descritivas"):
        st.dataframe(dff[["valor_credito", "taxa_juros", "inadimplencia_percentual", "quantidade_clientes",
                          "renda_media", "prazo_medio_pagamento"]].describe().T.round(2))


def pagina_banco() -> None:
    st.title("Banco de Dados")
    st.caption("Persistência relacional da base e consultas SQL.")

    engine = get_engine()
    objetos = listar_tabelas(engine)
    c1, c2 = st.columns([1, 1.4])
    with c1:
        st.markdown("**Modelo relacional (esquema estrela)**")
        st.code(
            "dim_regiao (id_regiao, regiao)\n"
            "dim_uf (id_uf, uf, id_regiao → dim_regiao)\n"
            "dim_modalidade (id_modalidade, modalidade)\n"
            "dim_setor (id_setor, setor)\n"
            "dim_risco (id_risco, risco, ordem)\n"
            "fato_credito (id_operacao, data, ano, mes,\n"
            "   id_uf, id_modalidade, id_setor, id_risco,\n"
            "   valor_credito, taxa_juros, inadimplencia_percentual,\n"
            "   quantidade_clientes, renda_media, prazo_medio_pagamento)\n"
            "vw_credito_completo (view com todos os JOINs)",
            language="text",
        )
    with c2:
        contagens = []
        for nome in objetos:
            try:
                n = consultar(f"SELECT COUNT(*) AS n FROM {nome}")["n"].iloc[0]
            except Exception:  # noqa: BLE001
                n = None
            contagens.append({"Objeto": nome, "Registros": n})
        st.markdown("**Objetos no banco** `database/sistema_financeiro.db`")
        st.dataframe(pd.DataFrame(contagens), hide_index=True)

    st.subheader("Consultas SQL")
    st.caption("As consultas são executadas sobre a base completa armazenada no banco (independem dos filtros).")
    nome = st.selectbox("Consulta", list(CONSULTAS))
    sql = CONSULTAS[nome]
    st.code(sql.strip(), language="sql")
    resultado = consultar(sql)
    st.dataframe(resultado, hide_index=True)
    numericas = resultado.select_dtypes("number").columns.tolist()
    if len(numericas) and len(resultado) <= 40:
        fig = px.bar(resultado, x=resultado.columns[0], y=numericas[0], title=f"{nome} — {numericas[0]}",
                     color_discrete_sequence=[AZUL])
        st.plotly_chart(estilizar(fig, 360, legenda=False), key="db_chart")

    st.subheader("Persistir recorte atual")
    if st.button("Gravar dados filtrados na tabela 'base_filtrada'"):
        exigir_dados()
        salvar = dff.drop(columns=["periodo"]).copy()
        salvar["data"] = salvar["data"].dt.strftime("%Y-%m-%d")
        for col in ["faixa_juros", "faixa_renda", "faixa_prazo", "risco_credito"]:
            salvar[col] = salvar[col].astype(str)
        salvar_tabela(salvar, "base_filtrada")
        st.success(f"{num(len(salvar))} registros gravados na tabela 'base_filtrada'.")


def pagina_conclusao() -> None:
    st.title("Conclusão")
    st.caption("Síntese dos resultados para o recorte selecionado.")
    exigir_dados()

    k = calcular_kpis(dff)
    reg = dff.groupby("regiao")["valor_credito"].sum().sort_values(ascending=False)
    setor = dff.groupby("setor_economico")["inadimplencia_percentual"].mean().sort_values(ascending=False)
    mod = dff.groupby("modalidade_credito").agg(inad=("inadimplencia_percentual", "mean"),
                                                alto=("risco_alto", "mean")).sort_values("inad", ascending=False)
    anual = dff.groupby("ano")["valor_credito"].sum()
    r, p = (stats.pearsonr(dff["taxa_juros"], dff["inadimplencia_percentual"]) if len(dff) > 2 else (0, 1))
    uf = dff.groupby("uf")["valor_credito"].sum()
    part_uf = (uf / uf.sum() * 100).sort_values(ascending=False)
    hhi = indice_hhi(part_uf)
    cresc = (anual.iloc[-1] / anual.iloc[0] - 1) * 100 if len(anual) > 1 else 0
    juros_ano = dff.groupby("ano")["taxa_juros"].mean()
    inad_ano = dff.groupby("ano")["inadimplencia_percentual"].mean()

    respostas = [
        ("Quais regiões apresentam maior volume de crédito?",
         f"{reg.index[0]} ({brl(reg.iloc[0])}, {_br(reg.iloc[0] / reg.sum() * 100, 1)}% do total), seguida por "
         f"{reg.index[1] if len(reg) > 1 else '-'}. O resultado acompanha o número de operações registradas por região."),
        ("Quais setores possuem maior inadimplência?",
         f"{setor.index[0]} ({pct(setor.iloc[0])}); o menor índice é de {setor.index[-1]} ({pct(setor.iloc[-1])}). "
         f"A diferença entre setores é de {_br(setor.iloc[0] - setor.iloc[-1])} p.p."),
        ("Houve crescimento do crédito ao longo do tempo?",
         f"O volume anual variou {_br(cresc)}% entre {anual.index[0]} e {anual.index[-1]}, com pico em {anual.idxmax()} "
         f"e mínimo em {anual.idxmin()}. O comportamento é de estabilidade, sem tendência forte de expansão."
         if len(anual) > 1 else "Selecione mais de um ano para avaliar o crescimento."),
        ("Existe relação entre juros e inadimplência?",
         f"A correlação de Pearson é {_br(r, 3)} ({forca_correlacao(r)}; p-valor {f'{p:.3f}'.replace('.', ',')}). "
         + ("Não há relação linear relevante na base." if abs(r) < 0.1 else "Há associação que merece aprofundamento.")),
        ("Quais modalidades apresentam maior risco?",
         f"{mod.index[0]} lidera a inadimplência média ({pct(mod['inad'].iloc[0])}); a maior proporção de operações de "
         f"risco alto está em {mod['alto'].idxmax()} ({_br(mod['alto'].max() * 100, 1)}%)."),
        ("Como o comportamento financeiro evoluiu?",
         f"A taxa média de juros foi de {pct(juros_ano.iloc[0])} em {juros_ano.index[0]} para {pct(juros_ano.iloc[-1])} em "
         f"{juros_ano.index[-1]}, e a inadimplência de {pct(inad_ano.iloc[0])} para {pct(inad_ano.iloc[-1])}. "
         f"Os indicadores oscilam em torno de médias estáveis."),
        ("Quais estados possuem maior concentração bancária?",
         f"{', '.join(part_uf.index[:3])} concentram {_br(part_uf.iloc[:3].sum(), 1)}% do crédito "
         f"(HHI = {num(hhi)}, concentração {'baixa' if hhi < 1500 else 'moderada' if hhi < 2500 else 'alta'})."),
    ]
    for pergunta, resposta in respostas:
        st.markdown(f"**{pergunta}**")
        st.markdown(f"<div class='caixa-texto'>{resposta}</div>", unsafe_allow_html=True)

    st.subheader("Recomendações")
    st.markdown(
        f"""
        1. **Monitorar regiões e estados críticos** identificados na análise regional, priorizando políticas de
           cobrança e renegociação onde a inadimplência supera a média ({pct(k['inad'])}).
        2. **Revisar a precificação**: como juros e inadimplência não apresentam relação linear clara, a taxa cobrada
           não está refletindo o risco — recomenda-se incorporar variáveis de perfil do tomador e garantias.
        3. **Diversificar a carteira** entre modalidades e setores, evitando concentração em segmentos com maior
           proporção de risco alto.
        4. **Acompanhar indicadores macroeconômicos** (Selic e inadimplência do SFN) via API do Banco Central para
           antecipar ciclos de aperto monetário.
        """
    )
    st.subheader("Limitações")
    st.markdown(
        "A base utilizada é **simulada** e apresenta distribuição praticamente uniforme das variáveis; por isso as "
        "diferenças entre grupos são pequenas e as correlações próximas de zero. As conclusões demonstram o método "
        "analítico e devem ser validadas com dados reais (SCR/BCB, IF.data) antes de embasar decisões."
    )


# ---------------------------------------------------------------------------
# Navegação (dashboard multipágina)
# ---------------------------------------------------------------------------

paginas = {
    "Painel": [
        st.Page(pagina_visao_geral, title="Visão Geral", icon=":material/dashboard:", url_path="visao-geral", default=True),
        st.Page(pagina_temporal, title="Evolução Temporal", icon=":material/timeline:", url_path="evolucao-temporal"),
        st.Page(pagina_regional, title="Análise Regional", icon=":material/map:", url_path="analise-regional"),
        st.Page(pagina_modalidades, title="Modalidades, Setores e Risco", icon=":material/category:", url_path="modalidades-risco"),
        st.Page(pagina_correlacao, title="Juros × Inadimplência", icon=":material/scatter_plot:", url_path="juros-inadimplencia"),
    ],
    "Dados e Integrações": [
        st.Page(pagina_bcb, title="Indicadores BCB (API)", icon=":material/cloud_download:", url_path="indicadores-bcb"),
        st.Page(pagina_exploracao, title="Tabela Dinâmica", icon=":material/table_chart:", url_path="tabela-dinamica"),
        st.Page(pagina_banco, title="Banco de Dados", icon=":material/database:", url_path="banco-de-dados"),
    ],
    "Resultados": [
        st.Page(pagina_conclusao, title="Conclusão", icon=":material/task_alt:", url_path="conclusao"),
    ],
}

pg = st.navigation(paginas)
pg.run()

st.markdown(
    "<div class='rodape'>Projeto G1 — Linguagem de Programação: Análise e Visualização de Dados com Python · "
    "Rafael Murayama Barcelos · Dados: base simulada do sistema financeiro brasileiro (2015–2024) e API SGS/BCB.</div>",
    unsafe_allow_html=True,
)
