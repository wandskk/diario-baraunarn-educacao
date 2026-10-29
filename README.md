# Diário Oficial de Baraúna/RN — publicações de educação

Coleta das edições do Diário Oficial dos Municípios (FEMURN, entidade 324) que contêm matérias de educação, de 2010 até hoje.

- `raspar.py`: indexa (busca por palavras-chave, ano a ano) e baixa 1 PDF por edição. Fila retomável.
- `PLANO_RASPAGEM.md`: levantamento do site e plano.
- `saida/`: `indice.csv`, `indice.db`, logs e `edicoes_pdf/<ano>/`.

Uso: `python raspar.py indexar`, `python raspar.py baixar`, `python raspar.py relatorio`.
