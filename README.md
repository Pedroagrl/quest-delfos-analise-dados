# Quest Delfos — análise de dados

Projeto de Pedro Artur para o teste técnico de estágio em Análise de Dados e Automação.

O relatório de julho de 2026 está em [`relatorio_delfos_julho_2026.html`](relatorio_delfos_julho_2026.html). Na Vercel, esse arquivo é exibido na página inicial. O repositório também contém o script de análise, o banco SQLite fornecido para o teste e os CSVs coletados do portal para reprodução dos resultados. O site publicado exibe somente o HTML do relatório.

## Executar a análise

Requer Python 3 e `pandas`:

```bash
python -m pip install pandas
python analises.py
```

Execute o comando na raiz deste repositório. O script lê `delfos.db` e os CSVs em `dados_portal/`, executa as duas consultas SQL diretamente no SQLite e apresenta a conciliação e as investigações complementares.

O portal do teste é a fonte de referência para os valores de geração. O banco `delfos.db` representa os registros a conciliar.
