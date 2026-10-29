# Diário Oficial de Baraúna/RN — publicações de educação

Coleta das edições do Diário Oficial dos Municípios (FEMURN, entidade 324) que contêm matérias de educação, de 2010 até hoje.

- `raspar.py`: indexa (busca por palavras-chave, ano a ano) e baixa 1 PDF por edição. Fila retomável.
- `PLANO_RASPAGEM.md`: levantamento do site e plano.
- `saida/`: `indice.csv`, `indice.db`, logs e `edicoes_pdf/<ano>/`.

Uso: `python raspar.py indexar`, `python raspar.py baixar`, `python raspar.py relatorio`.

## Site de busca (GitHub Pages)
`docs/index.html` + `docs/dados.json`: busca por título, filtros por tipo, ano e órgão. Cada documento abre o PDF da edição direto no site oficial. Para atualizar: `python raspar.py indexar`, depois `python gerar_site.py`.
Os PDFs baixados ficam só locais (`saida/edicoes_pdf/` e `saida/por_tipo/`, fora do git).

## Nome dos PDFs
`AAAA-MM-DD_ed-NNNN_<documentos>.pdf`, por exemplo `2023-12-27_ed-3188_portaria-419-2023.pdf`. Quando a edição tem vários documentos de educação, o nome lista até 3 (`portaria-370-2023+decreto-12-2023+2-mais`). Em `saida/por_tipo/<tipo>/<ano>/` o nome lista só os documentos daquele tipo. Depois de reindexar: `python raspar.py renomear`, `organizar` e `relatorio`.
