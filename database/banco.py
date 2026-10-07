"""
Camada de persistência do projeto (SQLAlchemy + SQLite).

Responsabilidades:
- criar o banco SQLite a partir do CSV tratado;
- aplicar uma modelagem relacional simples (tabelas dimensão + tabela fato);
- disponibilizar consultas SQL prontas para o dashboard;
- armazenar os dados obtidos via API do Banco Central (integração de fontes).

Execução direta (gera/atualiza o banco):
    python database/banco.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "sistema_financeiro.db"
CSV_PATH = BASE_DIR / "dados" / "simulacao_sistema_financeiro_brasil.csv"

# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

def get_engine(db_path: Path = DB_PATH):
    """Retorna um engine SQLAlchemy para o SQLite.

    Se o SQLAlchemy não estiver instalado, usa a conexão nativa sqlite3
    (o pandas aceita os dois objetos em read_sql / to_sql).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from sqlalchemy import create_engine

        return create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    except ImportError:  # pragma: no cover - fallback para ambientes sem SQLAlchemy
        import sqlite3

        return sqlite3.connect(db_path, check_same_thread=False)


def _executar_sql(engine, comandos: str) -> None:
    """Executa um bloco de comandos SQL separados por ';'."""
    instrucoes = [c.strip() for c in comandos.split(";") if c.strip()]
    if hasattr(engine, "begin"):  # SQLAlchemy Engine
        with engine.begin() as conn:
            for instrucao in instrucoes:
                conn.exec_driver_sql(instrucao)
    else:  # sqlite3.Connection
        cur = engine.cursor()
        for instrucao in instrucoes:
            cur.execute(instrucao)
        engine.commit()


def listar_tabelas(engine) -> list[str]:
    consulta = "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"
    return pd.read_sql(consulta, engine)["name"].tolist()


# ---------------------------------------------------------------------------
# Modelagem relacional
# ---------------------------------------------------------------------------

DDL = """
DROP VIEW  IF EXISTS vw_credito_completo;
DROP TABLE IF EXISTS fato_credito;
DROP TABLE IF EXISTS dim_uf;
DROP TABLE IF EXISTS dim_regiao;
DROP TABLE IF EXISTS dim_modalidade;
DROP TABLE IF EXISTS dim_setor;
DROP TABLE IF EXISTS dim_risco;

CREATE TABLE dim_regiao (
    id_regiao   INTEGER PRIMARY KEY,
    regiao      TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_uf (
    id_uf       INTEGER PRIMARY KEY,
    uf          TEXT NOT NULL UNIQUE,
    id_regiao   INTEGER NOT NULL REFERENCES dim_regiao(id_regiao)
);

CREATE TABLE dim_modalidade (
    id_modalidade INTEGER PRIMARY KEY,
    modalidade    TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_setor (
    id_setor    INTEGER PRIMARY KEY,
    setor       TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_risco (
    id_risco    INTEGER PRIMARY KEY,
    risco       TEXT NOT NULL UNIQUE,
    ordem       INTEGER NOT NULL
);

CREATE TABLE fato_credito (
    id_operacao              INTEGER PRIMARY KEY,
    data                     TEXT    NOT NULL,
    ano                      INTEGER NOT NULL,
    mes                      INTEGER NOT NULL,
    id_uf                    INTEGER NOT NULL REFERENCES dim_uf(id_uf),
    id_modalidade            INTEGER NOT NULL REFERENCES dim_modalidade(id_modalidade),
    id_setor                 INTEGER NOT NULL REFERENCES dim_setor(id_setor),
    id_risco                 INTEGER NOT NULL REFERENCES dim_risco(id_risco),
    valor_credito            REAL    NOT NULL,
    taxa_juros               REAL    NOT NULL,
    inadimplencia_percentual REAL    NOT NULL,
    quantidade_clientes      INTEGER NOT NULL,
    renda_media              REAL    NOT NULL,
    prazo_medio_pagamento    REAL    NOT NULL
);

CREATE INDEX idx_fato_ano        ON fato_credito(ano);
CREATE INDEX idx_fato_uf         ON fato_credito(id_uf);
CREATE INDEX idx_fato_modalidade ON fato_credito(id_modalidade);

CREATE VIEW vw_credito_completo AS
SELECT f.id_operacao, f.data, f.ano, f.mes,
       r.regiao, u.uf, m.modalidade, s.setor, k.risco,
       f.valor_credito, f.taxa_juros, f.inadimplencia_percentual,
       f.quantidade_clientes, f.renda_media, f.prazo_medio_pagamento
FROM fato_credito f
JOIN dim_uf         u ON u.id_uf = f.id_uf
JOIN dim_regiao     r ON r.id_regiao = u.id_regiao
JOIN dim_modalidade m ON m.id_modalidade = f.id_modalidade
JOIN dim_setor      s ON s.id_setor = f.id_setor
JOIN dim_risco      k ON k.id_risco = f.id_risco
"""

ORDEM_RISCO = {"Baixo": 1, "Médio": 2, "Alto": 3}


def _dimensao(serie: pd.Series, nome_coluna: str, nome_id: str) -> pd.DataFrame:
    valores = sorted(serie.dropna().unique())
    return pd.DataFrame({nome_id: range(1, len(valores) + 1), nome_coluna: valores})


def criar_banco(df: pd.DataFrame | None = None, db_path: Path = DB_PATH) -> Path:
    """Cria o banco relacional a partir do DataFrame (ou do CSV original)."""
    if df is None:
        df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")

    df = df.copy()
    df["data"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m-%d")

    engine = get_engine(db_path)
    _executar_sql(engine, DDL)

    dim_regiao = _dimensao(df["regiao"], "regiao", "id_regiao")
    dim_uf = (
        df[["uf", "regiao"]].drop_duplicates().sort_values("uf").reset_index(drop=True)
        .merge(dim_regiao, on="regiao")
    )
    dim_uf.insert(0, "id_uf", range(1, len(dim_uf) + 1))
    dim_uf = dim_uf[["id_uf", "uf", "id_regiao"]]
    dim_modalidade = _dimensao(df["modalidade_credito"], "modalidade", "id_modalidade")
    dim_setor = _dimensao(df["setor_economico"], "setor", "id_setor")
    dim_risco = pd.DataFrame(
        {"id_risco": [1, 2, 3], "risco": list(ORDEM_RISCO), "ordem": list(ORDEM_RISCO.values())}
    )

    fato = (
        df.merge(dim_uf[["id_uf", "uf"]], on="uf")
        .merge(dim_modalidade, left_on="modalidade_credito", right_on="modalidade")
        .merge(dim_setor, left_on="setor_economico", right_on="setor")
        .merge(dim_risco[["id_risco", "risco"]], left_on="risco_credito", right_on="risco")
    )
    fato = fato[
        [
            "data", "ano", "mes", "id_uf", "id_modalidade", "id_setor", "id_risco",
            "valor_credito", "taxa_juros", "inadimplencia_percentual",
            "quantidade_clientes", "renda_media", "prazo_medio_pagamento",
        ]
    ].sort_values(["data", "id_uf"]).reset_index(drop=True)
    fato.insert(0, "id_operacao", range(1, len(fato) + 1))

    for nome, tabela in [
        ("dim_regiao", dim_regiao),
        ("dim_uf", dim_uf),
        ("dim_modalidade", dim_modalidade),
        ("dim_setor", dim_setor),
        ("dim_risco", dim_risco),
        ("fato_credito", fato),
    ]:
        tabela.to_sql(nome, engine, if_exists="append", index=False)

    return db_path


def salvar_tabela(df: pd.DataFrame, nome: str, db_path: Path = DB_PATH) -> None:
    """Grava (substituindo) uma tabela auxiliar, ex.: dados da API do BCB."""
    engine = get_engine(db_path)
    df.to_sql(nome, engine, if_exists="replace", index=False)


# ---------------------------------------------------------------------------
# Consultas SQL prontas (usadas no dashboard e no notebook)
# ---------------------------------------------------------------------------

CONSULTAS: dict[str, str] = {
    "Volume de crédito por região": """
        SELECT regiao,
               ROUND(SUM(valor_credito) / 1e6, 2)      AS volume_milhoes,
               ROUND(AVG(inadimplencia_percentual), 2) AS inadimplencia_media,
               ROUND(AVG(taxa_juros), 2)               AS juros_medio,
               COUNT(*)                                AS operacoes
        FROM vw_credito_completo
        GROUP BY regiao
        ORDER BY volume_milhoes DESC
    """,
    "Ranking de estados (concentração do crédito)": """
        SELECT uf, regiao,
               ROUND(SUM(valor_credito) / 1e6, 2) AS volume_milhoes,
               ROUND(100.0 * SUM(valor_credito) /
                     (SELECT SUM(valor_credito) FROM fato_credito), 2) AS participacao_pct
        FROM vw_credito_completo
        GROUP BY uf, regiao
        ORDER BY volume_milhoes DESC
    """,
    "Inadimplência por setor econômico": """
        SELECT setor,
               ROUND(AVG(inadimplencia_percentual), 2) AS inadimplencia_media,
               ROUND(SUM(valor_credito * inadimplencia_percentual / 100) / 1e6, 2) AS valor_em_atraso_milhoes
        FROM vw_credito_completo
        GROUP BY setor
        ORDER BY inadimplencia_media DESC
    """,
    "Risco por modalidade": """
        SELECT modalidade,
               ROUND(AVG(inadimplencia_percentual), 2) AS inadimplencia_media,
               ROUND(AVG(taxa_juros), 2)               AS juros_medio,
               ROUND(100.0 * SUM(CASE WHEN risco = 'Alto' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_risco_alto
        FROM vw_credito_completo
        GROUP BY modalidade
        ORDER BY inadimplencia_media DESC
    """,
    "Evolução anual do crédito": """
        SELECT ano,
               ROUND(SUM(valor_credito) / 1e6, 2)      AS volume_milhoes,
               ROUND(AVG(taxa_juros), 2)               AS juros_medio,
               ROUND(AVG(inadimplencia_percentual), 2) AS inadimplencia_media,
               SUM(quantidade_clientes)                AS clientes
        FROM fato_credito
        GROUP BY ano
        ORDER BY ano
    """,
    "Estados críticos (inadimplência acima da média nacional)": """
        SELECT uf, regiao,
               ROUND(AVG(inadimplencia_percentual), 2) AS inadimplencia_media,
               ROUND(AVG(taxa_juros), 2)               AS juros_medio
        FROM vw_credito_completo
        GROUP BY uf, regiao
        HAVING AVG(inadimplencia_percentual) >
               (SELECT AVG(inadimplencia_percentual) FROM fato_credito)
        ORDER BY inadimplencia_media DESC
    """,
}


def consultar(sql: str, db_path: Path = DB_PATH) -> pd.DataFrame:
    engine = get_engine(db_path)
    return pd.read_sql(sql, engine)


if __name__ == "__main__":
    caminho = criar_banco()
    eng = get_engine(caminho)
    print(f"Banco criado em: {caminho}")
    print("Objetos:", ", ".join(listar_tabelas(eng)))
    print(consultar(CONSULTAS["Volume de crédito por região"]))
