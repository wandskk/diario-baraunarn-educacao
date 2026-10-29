# Plano: raspagem do Diário Oficial de Baraúna/RN (entidade 324, FEMURN)

## O que descobri (testado em 29/10/2026)
- Não há API nem JS escondido: a pesquisa é HTML renderizado no servidor (GET). Basta requisição HTTP simples, sem navegador.
- robots.txt sem nenhuma restrição.
- Busca: `/femurn/pesquisar?busca_avancada[texto|entidade|orgao|dataInicio|dataFim|ordenacao|pagina]`, 25 matérias por página, mostra o total ("1.333 matérias").
- Cada matéria tem: título, órgão, data de circulação, nº da edição, código (ex.: 57A85E51) e 3 links:
  - `/femurn/materia/<COD>` (página da matéria, texto completo)
  - `/femurn/download/materia/<COD>` (HTML da matéria)
  - `/femurn/download/edicao/<COD>` (PDF da edição inteira, assinado)
- Publicações começam em **01/02/2010**. Antes de 2010: 0.
- Volume por ano (todas as matérias): 2010: 270 | 2011: 437 | 2012: 409 | 2013: 516 | 2014: 993 | 2015: 218 | 2016: 226 | 2017: 725 | 2018: 857 | 2019: 1.271 | 2020: 1.129 | 2021: 1.718 | 2022: 1.905 | 2023: 2.282 | 2024: 1.728 | 2025: 1.846 | 2026 (até 29/10): 1.333. Total ≈ 17.800.
- Educação (busca por texto "educação", sem diferenciar acento): 2013: 49 | 2014: 166 | 2015: 15 | 2016: 57 | 2017: 148 | 2018: 222 | 2019: 279 | 2020: 163 | 2021: 220 | 2022: 306 | 2023: 308 | 2024: 285 | 2025: 375 | 2026: 297. Estimativa total ≈ 3.000+ (2010-2012 ainda a medir).

## Limitações encontradas
- Intervalo grande demais devolve vazio ou total truncado (2013-2026 → "10.001"): consultar **mês a mês**.
- Data final no futuro devolve vazio: usar no máximo a data de hoje.
- O filtro por órgão "Secretaria Municipal da Educação" (14601) retorna 0, então a SME não publica com esse órgão. O recorte de educação precisa ser por **palavra-chave** no texto, não por órgão.

## Como identificar "educação"
1. Passada ampla: buscar por palavras-chave mês a mês e unir os resultados por código (sem duplicar): educação, escola, escolar, FUNDEB, professor, magistério, ensino, creche, merenda, alimentação escolar, transporte escolar, pedagógic, SME, Secretaria Municipal da Educação, Conselho Municipal de Educação, PNAE, PNATE.
2. Depois de baixar o texto, classificar cada matéria (palavras no título/corpo) com um campo `tema_educacao` e `motivo`, para você poder revisar o que entrou por engano.
3. Opção de guardar TUDO (17.800 matérias, são só HTML) e apenas marcar as de educação. Recomendo: o custo é baixo e evita refazer depois.

## Fluxo (fila, retomável)
1. **Indexar**: para cada mês de 2010-02 até hoje, paginar a busca (25 por página), registrar código, título, data, edição, órgão, links em um SQLite (`indice.db`). Pausa de 1-2 s entre requisições, User-Agent identificado, retry com backoff.
2. **Fila de downloads**: tabela com status (pendente/baixado/erro). Baixa o HTML de cada matéria; se falhar, tenta de novo depois. Pode parar e continuar de onde parou.
3. **PDF da edição**: um PDF por edição (não por matéria), então baixar uma vez por nº de edição. Só para as edições que contêm matéria de educação (≈ centenas de PDFs, não milhares).
4. **Classificar** educação e tipo (Lei, Decreto, Portaria, Edital, Contrato, Resolução, Outros) pelo título.
5. **Relatório**: contagem por ano e tipo, lista de erros, conferência do total do site vs. baixado.

## Estrutura de pastas
```
diario-baraúna/
  indice.db                 (SQLite com tudo e o status da fila)
  indice.csv                (exportação para abrir no Excel)
  educacao/
    2010/ ... 2026/
      lei/  decreto/  portaria/  edital/  contrato/  outros/
        2025-03-14_ed3500_<COD>_portaria-123.html
  todas/                    (opcional: todas as matérias, mesma estrutura por ano)
  edicoes_pdf/
    2025/edicao-3500-2025-03-14.pdf
  logs/
```

## Tecnologia sugerida
Python (requests + BeautifulSoup + sqlite3), um script único com comandos `indexar`, `baixar`, `classificar`, `relatorio`. Estimativa: indexação ~700 páginas (~20 min), download das ~3.000 matérias de educação ~1-2 h; tudo ~18 mil matérias ~6-8 h em segundo plano.

## Pontos a confirmar
- Só Baraúna (entidade 324) ou outros municípios do FEMURN também?
- Quer só educação ou guardar tudo e marcar educação?
- PDFs das edições: só das que têm educação, ou todas (≈ 3.900 edições)?
- Formato: HTML da matéria + PDF; quer também texto puro/JSON para pesquisa?
