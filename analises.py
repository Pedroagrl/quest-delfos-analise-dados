import sqlite3
from pathlib import Path

import pandas as pd


# Arquivo do banco SQLite na mesma pasta deste script.
PASTA_PROJETO = Path(__file__).resolve().parent
DB_PATH = PASTA_PROJETO / "delfos.db"


# Consulta SQL obrigatória 1:
# geração total e yield específico por usina em julho/2026.

QUERY_GERACAO_YIELD = """
SELECT
    sf.solar_field_id,
    sf.name,
    sf.capacity_kwp,
    ROUND(SUM(ed.energy_kwh), 1) AS generation_kwh,
    ROUND(SUM(ed.energy_kwh) / sf.capacity_kwp, 2) AS specific_yield_kwh_kwp
FROM solar_field AS sf
LEFT JOIN energy_daily AS ed
    ON ed.solar_field_id = sf.solar_field_id
   AND ed.date >= '2026-07-01'
   AND ed.date < '2026-08-01'
GROUP BY sf.solar_field_id, sf.name, sf.capacity_kwp
ORDER BY sf.solar_field_id;
"""


# Consulta SQL obrigatória 2:
# quantidade de dias registrados por usina em julho/2026.
QUERY_DIAS_REGISTRADOS = """
SELECT
    sf.solar_field_id,
    sf.name,
    COUNT(ed.date) AS registered_days
FROM solar_field AS sf
LEFT JOIN energy_daily AS ed
    ON ed.solar_field_id = sf.solar_field_id
   AND ed.date >= '2026-07-01'
   AND ed.date < '2026-08-01'
GROUP BY sf.solar_field_id, sf.name
ORDER BY sf.solar_field_id;
"""


# Dados diários usados pelo Pandas para encontrar datas ausentes.
QUERY_DADOS_DIARIOS = """
SELECT
    solar_field_id,
    date,
    energy_kwh
FROM energy_daily
WHERE date >= '2026-07-01'
  AND date < '2026-08-01'
ORDER BY solar_field_id, date;
"""


if not DB_PATH.exists():
    raise FileNotFoundError(
        f"Não encontrei o arquivo {DB_PATH.resolve()}. "
        "Confirme se delfos.db está na mesma pasta de analises.py."
    )


# Executa as consultas diretamente no SQLite.
with sqlite3.connect(DB_PATH) as con:
    resultado_geracao = con.execute(QUERY_GERACAO_YIELD).fetchall()
    resultado_dias = con.execute(QUERY_DIAS_REGISTRADOS).fetchall()
    df_diario = pd.read_sql_query(QUERY_DADOS_DIARIOS, con)


# Exibe o resultado da primeira consulta SQL.
print("\nGeração e yield registrados na Delfos - julho/2026")
print("-" * 100)

for solar_field_id, nome, capacidade, geracao, yield_especifico in resultado_geracao:
    print(
        f"{solar_field_id} | {nome:20} | "
        f"{capacidade:10,.2f} kWp | "
        f"{geracao:10,.1f} kWh | "
        f"{yield_especifico:6.2f} kWh/kWp"
    )


# Exibe o resultado da segunda consulta SQL.
print("\nDias de julho registrados na Delfos")
print("-" * 55)

for solar_field_id, nome, total_dias in resultado_dias:
    print(f"{solar_field_id} | {nome:20} | {total_dias} dias")


# Converte a coluna de texto para uma data que o Pandas entende.
df_diario["date"] = pd.to_datetime(df_diario["date"])

# Cria o calendário completo de julho para comparar contra cada usina.
calendario_julho = pd.DataFrame(
    {
        "date": pd.date_range("2026-07-01", "2026-07-31")
    }
)


# Localiza automaticamente datas ausentes por usina.
print("\nDatas ausentes no banco")
print("-" * 55)

for solar_field_id in df_diario["solar_field_id"].unique():
    datas_usina = df_diario[
        df_diario["solar_field_id"] == solar_field_id
    ]

    comparacao = calendario_julho.merge(
        datas_usina[["date"]],
        on="date",
        how="left",
        indicator=True
    )

    datas_faltantes = comparacao.loc[
        comparacao["_merge"] == "left_only",
        "date"
    ]

    if datas_faltantes.empty:
        print(f"{solar_field_id}: nenhuma data ausente")
    else:
        datas_formatadas = datas_faltantes.dt.strftime("%d/%m/%Y").tolist()
        print(f"{solar_field_id}: {', '.join(datas_formatadas)}")

# CSVs baixados do portal e salvos na mesma pasta deste script.
PASTA_DADOS_PORTAL = PASTA_PROJETO / "dados_portal"

arquivos_portal = sorted(
    PASTA_DADOS_PORTAL.glob("SF-*_monthly_2026-07_*.csv")
)

if len(arquivos_portal) != 5:
    raise ValueError(
        f"Esperava 5 CSVs do portal, mas encontrei {len(arquivos_portal)}."
    )

ids_esperados = {linha[0] for linha in resultado_geracao}
ids_arquivos = [arquivo.name.split("_", 1)[0] for arquivo in arquivos_portal]
if set(ids_arquivos) != ids_esperados or len(set(ids_arquivos)) != 5:
    raise ValueError(f"CSVs diários esperados para {sorted(ids_esperados)}; encontrados: {ids_arquivos}.")

# Confere a identidade da usina e todos os 31 dias antes de somar os CSVs.
datas_julho = pd.date_range("2026-07-01", "2026-07-31")
tabelas_portal = []
for arquivo in arquivos_portal:
    tabela = pd.read_csv(arquivo)
    id_arquivo = arquivo.name.split("_", 1)[0]
    colunas_necessarias = {"solar_field_id", "period", "energy_kwh"}
    if not colunas_necessarias.issubset(tabela.columns):
        raise ValueError(f"{arquivo.name}: faltam colunas {sorted(colunas_necessarias - set(tabela.columns))}.")
    if set(tabela["solar_field_id"]) != {id_arquivo}:
        raise ValueError(f"{arquivo.name}: solar_field_id não corresponde a {id_arquivo} em todas as linhas.")
    datas = pd.to_datetime(tabela["period"], errors="coerce")
    if len(datas) != 31 or datas.isna().any() or datas.nunique() != 31 or not datas.isin(datas_julho).all():
        raise ValueError(f"{arquivo.name}: datas de julho incompletas, duplicadas ou fora do mês.")
    energia = pd.to_numeric(tabela["energy_kwh"], errors="coerce")
    if energia.isna().any() or (energia < 0).any():
        raise ValueError(f"{arquivo.name}: energy_kwh vazio, inválido ou negativo.")
    tabela["period"] = datas
    tabela["energy_kwh"] = energia
    tabelas_portal.append(tabela)

df_portal_diario = pd.concat(tabelas_portal, ignore_index=True)

# Agrupa os dados diários para obter o total mensal por usina.
portal_mensal = (
    df_portal_diario
    .groupby("solar_field_id", as_index=False)
    .agg(
        energia_portal_kwh=("energy_kwh", "sum"),
        dias_portal=("period", "nunique")
    )
)

print("\nResumo mensal coletado do portal")
print("-" * 65)
print(portal_mensal.to_string(index=False))

# Transforma os resultados das consultas SQL em DataFrames.
df_delfos_mensal = pd.DataFrame(
    resultado_geracao,
    columns=[
        "solar_field_id",
        "nome_usina",
        "capacidade_delfos_kwp",
        "energia_delfos_kwh",
        "yield_delfos_kwh_kwp"
    ]
)

df_dias_delfos = pd.DataFrame(
    resultado_dias,
    columns=[
        "solar_field_id",
        "nome_usina",
        "dias_delfos"
    ]
)

# Adiciona a quantidade de dias registrados à tabela mensal da Delfos.
df_delfos_mensal = df_delfos_mensal.merge(
    df_dias_delfos[["solar_field_id", "dias_delfos"]],
    on="solar_field_id",
    how="left"
)

# Une a tabela da Delfos com os totais calculados a partir dos CSVs do portal.
conciliacao = df_delfos_mensal.merge(
    portal_mensal,
    on="solar_field_id",
    how="outer",
    validate="one_to_one"
)

# Calcula a diferença. Valor negativo significa que a Delfos registrou menos.
conciliacao["diferenca_kwh"] = (
    conciliacao["energia_delfos_kwh"]
    - conciliacao["energia_portal_kwh"]
)

conciliacao["diferenca_percentual"] = (
    conciliacao["diferenca_kwh"]
    / conciliacao["energia_portal_kwh"]
    * 100
).round(2)

# Classifica a situação de cada usina.
conciliacao["situacao"] = conciliacao["diferenca_kwh"].apply(
    lambda diferenca: "Concilia"
    if abs(diferenca) < 0.05
    else "Diverge"
)

# Arredonda valores para facilitar a leitura.
conciliacao["diferenca_kwh"] = conciliacao["diferenca_kwh"].round(1)

print("\nConciliação: Delfos vs portal")
print("-" * 115)

colunas_exibidas = [
    "solar_field_id",
    "nome_usina",
    "energia_delfos_kwh",
    "energia_portal_kwh",
    "diferenca_kwh",
    "diferenca_percentual",
    "dias_delfos",
    "dias_portal",
    "situacao"
]

print(conciliacao[colunas_exibidas].to_string(index=False))

# Confere os inversores das cinco usinas no portal.
arquivos_inversores = sorted(
    PASTA_DADOS_PORTAL.glob("SF-*_inverters_monthly*.csv")
)

if len(arquivos_inversores) != 5:
    raise ValueError(
        f"Esperava 5 CSVs de inversores, mas encontrei {len(arquivos_inversores)}."
    )

ids_inversores = [arquivo.name.split("_", 1)[0] for arquivo in arquivos_inversores]
if set(ids_inversores) != ids_esperados or len(set(ids_inversores)) != 5:
    raise ValueError(f"CSVs de inversores esperados para {sorted(ids_esperados)}; encontrados: {ids_inversores}.")

tabelas_inversores = []
for arquivo in arquivos_inversores:
    tabela = pd.read_csv(arquivo)
    id_arquivo = arquivo.name.split("_", 1)[0]
    colunas_necessarias = {"solar_field_id", "device_id", "capacity_kwp", "month", "energy_kwh"}
    if not colunas_necessarias.issubset(tabela.columns):
        raise ValueError(f"{arquivo.name}: faltam colunas {sorted(colunas_necessarias - set(tabela.columns))}.")
    if set(tabela["solar_field_id"]) != {id_arquivo}:
        raise ValueError(f"{arquivo.name}: solar_field_id não corresponde a {id_arquivo} em todas as linhas.")
    if not tabela["month"].eq("2026-07").any():
        raise ValueError(f"{arquivo.name}: não há dados de julho/2026.")
    if tabela[["device_id", "capacity_kwp", "energy_kwh"]].isna().any().any():
        raise ValueError(f"{arquivo.name}: dados de inversores incompletos.")
    tabelas_inversores.append(tabela)

df_inversores = pd.concat(tabelas_inversores, ignore_index=True)

inversores_julho = df_inversores[
    df_inversores["month"] == "2026-07"
].copy()

if inversores_julho.duplicated(
    ["solar_field_id", "device_id"]
).any():
    raise ValueError("Há inversores duplicados nos CSVs de julho.")

resumo_inversores = (
    inversores_julho
    .groupby("solar_field_id", as_index=False)
    .agg(
        qtd_inversores=("device_id", "nunique"),
        capacidade_inversores_kwp=("capacity_kwp", "sum"),
        energia_inversores_kwh=("energy_kwh", "sum")
    )
)

validacao_inversores = conciliacao.merge(
    resumo_inversores,
    on="solar_field_id",
    how="left",
    validate="one_to_one"
)

validacao_inversores["diferenca_capacidade_kwp"] = (
    validacao_inversores["capacidade_inversores_kwp"]
    - validacao_inversores["capacidade_delfos_kwp"]
).round(2)

validacao_inversores["diferenca_energia_portal_kwh"] = (
    validacao_inversores["energia_inversores_kwh"]
    - validacao_inversores["energia_portal_kwh"]
).round(1)

print("\nValidação dos inversores - julho/2026")
print("-" * 110)

colunas = [
    "solar_field_id",
    "nome_usina",
    "qtd_inversores",
    "capacidade_inversores_kwp",
    "capacidade_delfos_kwp",
    "diferenca_capacidade_kwp",
    "energia_inversores_kwh",
    "diferenca_energia_portal_kwh"
]

print(validacao_inversores[colunas].to_string(index=False))

# Compara os registros diários da SF-005 entre portal e Delfos.
portal_sf005 = (
    df_portal_diario.loc[
        df_portal_diario["solar_field_id"] == "SF-005",
        ["solar_field_id", "period", "energy_kwh"]
    ]
    .rename(columns={
        "period": "date",
        "energy_kwh": "energia_portal_kwh"
    })
)

delfos_sf005 = (
    df_diario.loc[
        df_diario["solar_field_id"] == "SF-005",
        ["solar_field_id", "date", "energy_kwh"]
    ]
    .rename(columns={
        "energy_kwh": "energia_delfos_kwh"
    })
)

comparacao_sf005 = portal_sf005.merge(
    delfos_sf005,
    on=["solar_field_id", "date"],
    how="left",
    indicator=True,
    validate="one_to_one"
)

dias_ausentes = comparacao_sf005[
    comparacao_sf005["_merge"] == "left_only"
]

dias_presentes = comparacao_sf005[
    comparacao_sf005["_merge"] == "both"
].copy()

dias_presentes["diferenca_kwh"] = (
    dias_presentes["energia_portal_kwh"]
    - dias_presentes["energia_delfos_kwh"]
).round(1)

print("\nInvestigação diária da SF-005")
print("-" * 65)

for _, linha in dias_ausentes.iterrows():
    print(
        f"Sem registro na Delfos: {linha['date']:%d/%m/%Y} | "
        f"Portal: {linha['energia_portal_kwh']:,.1f} kWh"
    )

print(
    f"Maior diferença nos {len(dias_presentes)} dias presentes: "
    f"{dias_presentes['diferenca_kwh'].abs().max():,.1f} kWh"
)

print(
    f"Energia dos dias ausentes: "
    f"{dias_ausentes['energia_portal_kwh'].sum():,.1f} kWh"
)

# Verifica se a diferença diária da SF-001 é exatamente a geração do INV-05.
arquivo_inversor_diario = PASTA_DADOS_PORTAL / "SF-001_inverters_daily.csv"
if not arquivo_inversor_diario.exists():
    raise FileNotFoundError(f"Falta o CSV diário necessário para investigar a SF-001: {arquivo_inversor_diario}")

inversores_diarios = pd.read_csv(arquivo_inversor_diario)
colunas_necessarias = {"solar_field_id", "device_id", "capacity_kwp", "period", "energy_kwh"}
if not colunas_necessarias.issubset(inversores_diarios.columns):
    raise ValueError(f"{arquivo_inversor_diario.name}: faltam colunas {sorted(colunas_necessarias - set(inversores_diarios.columns))}.")

inversor_05 = inversores_diarios.loc[
    (inversores_diarios["solar_field_id"] == "SF-001")
    & (inversores_diarios["device_id"] == "SF-001-INV-05")
    & (inversores_diarios["period"].between("2026-07-01", "2026-07-31"))
].copy()
inversor_05["date"] = pd.to_datetime(inversor_05["period"], errors="coerce")
inversor_05["energy_kwh"] = pd.to_numeric(inversor_05["energy_kwh"], errors="coerce")
if (
    len(inversor_05) != 31
    or inversor_05["date"].isna().any()
    or inversor_05["date"].nunique() != 31
    or not inversor_05["date"].isin(datas_julho).all()
    or inversor_05["energy_kwh"].isna().any()
    or (inversor_05["energy_kwh"] < 0).any()
    or inversor_05["capacity_kwp"].nunique() != 1
):
    raise ValueError("SF-001-INV-05: dados diários de julho incompletos ou inválidos.")

capacidade_faltante = validacao_inversores.loc[
    validacao_inversores["solar_field_id"] == "SF-001", "diferenca_capacidade_kwp"
].iloc[0]
if abs(float(inversor_05["capacity_kwp"].iloc[0]) - capacidade_faltante) > 0.005:
    raise ValueError("SF-001: a capacidade do Inversor 05 não coincide com a diferença de capacidade da usina.")

portal_sf001 = df_portal_diario.loc[
    df_portal_diario["solar_field_id"] == "SF-001",
    ["period", "energy_kwh"],
].rename(columns={"period": "date", "energy_kwh": "portal_kwh"})
delfos_sf001 = df_diario.loc[
    df_diario["solar_field_id"] == "SF-001",
    ["date", "energy_kwh"],
].rename(columns={"energy_kwh": "delfos_kwh"})
comparacao_sf001 = (
    portal_sf001
    .merge(delfos_sf001, on="date", how="outer", validate="one_to_one", indicator=True)
    .merge(
        inversor_05[["date", "energy_kwh"]].rename(columns={"energy_kwh": "inversor_05_kwh"}),
        on="date",
        how="outer",
        validate="one_to_one",
    )
)
if len(comparacao_sf001) != 31 or not comparacao_sf001["_merge"].eq("both").all() or comparacao_sf001.isna().any().any():
    raise ValueError("SF-001: faltam datas para comparar portal, Delfos e Inversor 05.")

comparacao_sf001["residuo_kwh"] = (
    comparacao_sf001["portal_kwh"]
    - comparacao_sf001["delfos_kwh"]
    - comparacao_sf001["inversor_05_kwh"]
).round(1)
maior_residuo = comparacao_sf001["residuo_kwh"].abs().max()
if maior_residuo > 0:
    raise ValueError(f"SF-001: a diferença diária não coincide com o Inversor 05; maior resíduo: {maior_residuo:,.1f} kWh.")

print("\nInvestigação diária da SF-001")
print("-" * 65)
print(
    f"SF-001-INV-05: {len(comparacao_sf001)} dias | "
    f"capacidade: {inversor_05['capacity_kwp'].iloc[0]:,.2f} kWp | "
    f"energia: {inversor_05['energy_kwh'].sum():,.1f} kWh"
)
print(f"Maior resíduo diário: {maior_residuo:,.1f} kWh")

# Investiga uma queda real de geração na SF-003 sem classificá-la como erro do banco.
arquivo_sf003_diario = PASTA_DADOS_PORTAL / "SF-003_inverters_daily.csv"
if not arquivo_sf003_diario.exists():
    raise FileNotFoundError(f"Falta o CSV diário da SF-003: {arquivo_sf003_diario}")

df_sf003_inversores = pd.read_csv(arquivo_sf003_diario)
colunas_necessarias = {"solar_field_id", "device_id", "period", "energy_kwh"}
if not colunas_necessarias.issubset(df_sf003_inversores.columns):
    raise ValueError(
        f"{arquivo_sf003_diario.name}: faltam colunas "
        f"{sorted(colunas_necessarias - set(df_sf003_inversores.columns))}."
    )

df_sf003_inversores["date"] = pd.to_datetime(
    df_sf003_inversores["period"], errors="coerce"
)
inversor_03 = df_sf003_inversores.loc[
    (df_sf003_inversores["solar_field_id"] == "SF-003")
    & (df_sf003_inversores["device_id"] == "SF-003-INV-03")
    & df_sf003_inversores["date"].isin(datas_julho)
].copy()
inversor_03["energy_kwh"] = pd.to_numeric(
    inversor_03["energy_kwh"], errors="coerce"
)
if (
    len(inversor_03) != 31
    or inversor_03["date"].nunique() != 31
    or inversor_03["energy_kwh"].isna().any()
    or (inversor_03["energy_kwh"] < 0).any()
):
    raise ValueError("SF-003-INV-03: dados diários de julho incompletos ou inválidos.")

energia_mensal_inv03 = inversores_julho.loc[
    (inversores_julho["solar_field_id"] == "SF-003")
    & (inversores_julho["device_id"] == "SF-003-INV-03"),
    "energy_kwh",
]
if len(energia_mensal_inv03) != 1 or abs(
    inversor_03["energy_kwh"].sum() - energia_mensal_inv03.iloc[0]
) > 0.05:
    raise ValueError("SF-003-INV-03: a soma diária não coincide com o CSV mensal.")

datas_zero = (
    inversor_03.loc[inversor_03["energy_kwh"].eq(0), "date"]
    .sort_values()
    .reset_index(drop=True)
)
resumo_sf003 = conciliacao.loc[conciliacao["solar_field_id"] == "SF-003"].iloc[0]

print("\nInvestigação operacional da SF-003 - julho/2026")
print("-" * 65)
print(f"SF-003-INV-03: {len(datas_zero)} dias com geração registrada de 0,0 kWh")
if not datas_zero.empty:
    grupos = datas_zero.diff().dt.days.ne(1).cumsum()
    sequencias = datas_zero.groupby(grupos).agg(["min", "max", "count"])
    maior_sequencia = sequencias.sort_values("count", ascending=False).iloc[0]
    print(
        f"Maior sequência: {maior_sequencia['count']} dias consecutivos, "
        f"de {maior_sequencia['min']:%d/%m/%Y} a {maior_sequencia['max']:%d/%m/%Y}"
    )
print(
    f"Total da usina: portal {resumo_sf003['energia_portal_kwh']:,.1f} kWh | "
    f"banco {resumo_sf003['energia_delfos_kwh']:,.1f} kWh | "
    f"diferença {resumo_sf003['diferenca_kwh']:,.1f} kWh"
)
if resumo_sf003["situacao"] == "Concilia":
    print("Conclusão: o achado do inversor não é uma divergência entre portal e banco.")
