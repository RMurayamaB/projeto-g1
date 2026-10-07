# Sistema Financeiro e Crédito no Brasil (2015–2024)

**Projeto G1 — Tema 28** · Linguagem de Programação: Análise e Visualização de Dados com Python
**Aluno:** Rafael Murayama Barcelos

Projeto completo de análise e visualização de dados sobre concessão de crédito, juros, inadimplência e risco no Brasil,
com notebook analítico, banco de dados relacional, integração com a API do Banco Central e dashboard interativo multipágina.

| Entrega | Link |
|---|---|
| Repositório GitHub | `https://github.com/RMurayamaB/projeto-g1` |
| Página do projeto (GitHub Pages) | `https://rmurayamab.github.io/projeto-g1/` |
| Dashboard (Streamlit Community Cloud) | `https://projeto-g1.streamlit.app/` |
| Notebook | [`notebooks/analise_sistema_financeiro.ipynb`](notebooks/analise_sistema_financeiro.ipynb) |
| Código do dashboard | [`app.py`](app.py) |
| Base de dados | [`dados/simulacao_sistema_financeiro_brasil.csv`](dados/simulacao_sistema_financeiro_brasil.csv) |

---

## 1. Problema e perguntas orientadoras

1. Quais regiões apresentam maior volume de crédito?
2. Quais setores possuem maior inadimplência?
3. Houve crescimento do crédito ao longo do tempo?
4. Existe relação entre juros e inadimplência?
5. Quais modalidades financeiras apresentam maior risco?
6. Como o comportamento financeiro evoluiu?
7. Quais estados possuem maior concentração bancária?

## 2. Estrutura do projeto

```
projeto-g1/
├── app.py                      # Dashboard Streamlit (multipágina)
├── requirements.txt            # Dependências
├── README.md
├── index.html                  # Página de apresentação (GitHub Pages)
├── .streamlit/config.toml      # Tema do dashboard
├── dados/
│   └── simulacao_sistema_financeiro_brasil.csv
├── database/
│   ├── __init__.py
│   ├── banco.py                # SQLAlchemy: modelagem, carga e consultas SQL
│   └── sistema_financeiro.db   # Banco SQLite gerado
├── notebooks/
│   └── analise_sistema_financeiro.ipynb
└── imagens/                    # Gráficos exportados pelo notebook + prévias do dashboard
```

## 3. Tecnologias

| Obrigatórias | Complementares |
|---|---|
| Python, Pandas, Matplotlib, Seaborn, Streamlit, GitHub | Plotly, NumPy, SciPy, SQLAlchemy, SQLite, Requests |

## 4. Funcionalidades

**Intermediárias:** filtros múltiplos (ano, mês, região, estado dependente da região, modalidade, risco e setor), KPIs
dinâmicos com variação anual, gráficos interativos, análise temporal, tratamento avançado de dados, upload de CSV,
dashboard organizado em seções, visualizações comparativas e análise geográfica (mapa por UF).

**Avançadas:**

| Funcionalidade | Onde |
|---|---|
| Dashboard multipágina | `st.navigation` com 9 páginas em `app.py` |
| Consumo de API (Requests) | Página *Indicadores BCB*: Selic (SGS 4189), inadimplência do SFN (21082) e saldo da carteira (20539) |
| Persistência em banco (SQLAlchemy + SQLite) | `database/banco.py` e página *Banco de Dados SQL* |
| Modelagem relacional | Esquema estrela: `dim_regiao`, `dim_uf`, `dim_modalidade`, `dim_setor`, `dim_risco`, `fato_credito`, view `vw_credito_completo` |
| Correlação estatística | Pearson, Spearman, p-valor, R² e matriz de correlação |
| Séries temporais avançadas | Média móvel 12m, tendência linear, CAGR, variação anual, sazonalidade |
| Integração de múltiplas fontes | API do BCB + CSV + banco SQLite (cache da API) |

## 5. Páginas do dashboard

| Página | Conteúdo |
|---|---|
| Visão Geral | Título, descrição do problema, 10 KPIs, linha temporal, barras por região e modalidade, leitura dos indicadores |
| Evolução Temporal | Série mensal com média móvel e tendência, barras anuais com variação, sazonalidade, heatmap mensal |
| Análise Regional | Barras por região, ranking de UFs, HHI e CR3, mapa interativo, tabela de estados críticos |
| Modalidades, Setores e Risco | Barras por modalidade, evolução do risco, inadimplência por setor, heatmap setor × modalidade, boxplot Seaborn |
| Juros × Inadimplência | Dispersão com regressão, Pearson/Spearman, faixas de juros, matriz de correlação (Seaborn) |
| Indicadores BCB (API) | Selic e inadimplência reais × base simulada |
| Tabela Dinâmica | Pivot configurável, dados filtrados, estatísticas descritivas e download CSV |
| Banco de Dados SQL | Modelo relacional, consultas SQL prontas, gravação do recorte filtrado |
| Conclusão Executiva | Respostas às 7 perguntas, recomendações e limitações (texto gerado conforme os filtros) |

## 6. Como executar localmente

```bash
git clone https://github.com/SEU-USUARIO/projeto-g1.git
cd projeto-g1
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

python database/banco.py      # (opcional) recria o banco SQLite
streamlit run app.py          # abre o dashboard em http://localhost:8501
```

Para o notebook: `pip install jupyter` e abra `notebooks/analise_sistema_financeiro.ipynb`.

## 8. Principais resultados

- **Regiões:** o Sudeste concentra 36,3% do volume (≈ R$ 8,1 bi), efeito do maior número de operações; o valor médio por registro é semelhante entre regiões.
- **Setores:** Comércio tem a maior inadimplência média (10,97%); Serviços, a menor (10,40%).
- **Crescimento:** volume anual estável (≈ R$ 2,2–2,3 bi), CAGR de 0,28% a.a.; queda em 2020 e pico em 2021.
- **Juros × inadimplência:** Pearson r = -0,008 (p = 0,59) — sem relação significativa.
- **Modalidades:** Imobiliário com maior inadimplência média (10,78%); Veículos com maior proporção de risco alto (35,0%).
- **Concentração:** RJ lidera com 11,2%; HHI = 617 (baixa concentração). Estados críticos: PR, CE e ES.

## 9. Limitações

A base é **simulada** e apresenta distribuições praticamente uniformes; por isso as diferenças entre grupos são pequenas
e as correlações próximas de zero. As conclusões demonstram o método analítico e devem ser validadas com dados reais
(SCR/BCB, IF.data) antes de embasar decisões.
