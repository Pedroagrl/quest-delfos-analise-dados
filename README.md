## Executar a análise

Requer Python 3 e `pandas`:

```bash
python -m pip install pandas
python analises.py
```

Execute o comando na raiz deste repositório. O script lê `delfos.db` e os CSVs em `dados_portal/`, executa as duas consultas SQL diretamente no SQLite e apresenta a conciliação e as investigações complementares.

O portal do teste é a fonte de referência para os valores de geração. O banco `delfos.db` representa os registros a conciliar.
