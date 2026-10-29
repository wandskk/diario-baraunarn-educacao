"""Gera docs/dados.json (índice do site) a partir de saida/indice.db."""
import json, os, re, sqlite3
from raspar import SAIDA, tipo_de

ROTULOS = {"leis": "Lei", "decretos": "Decreto", "portarias": "Portaria", "editais": "Edital",
           "contratos_licitacoes": "Contrato / Licitação", "outros": "Outros"}


def main():
    c = sqlite3.connect(os.path.join(SAIDA, "indice.db"))
    docs = []
    for cod, tit, iso, ed, org, pal in c.execute(
            "SELECT cod,titulo,data_iso,edicao,orgao,palavras FROM materias ORDER BY data_iso DESC, cod"):
        t = tipo_de(tit)
        docs.append({"c": cod, "t": re.sub(r"\s+", " ", tit).strip(), "d": iso, "e": ed, "o": org, "p": pal,
                     "k": t})
    saida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "dados.json")
    os.makedirs(os.path.dirname(saida), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        json.dump({"gerado": __import__("datetime").date.today().isoformat(), "tipos": ROTULOS, "docs": docs},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(len(docs), "documentos ->", saida, os.path.getsize(saida) // 1024, "KB")


if __name__ == "__main__":
    main()
