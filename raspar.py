"""Raspagem do Diário Oficial de Baraúna/RN (FEMURN, entidade 324): só educação, só PDF das edições.

Uso:
  python raspar.py indexar [--anos 2010-2026]   # busca por palavras-chave, ano a ano, grava no SQLite
  python raspar.py baixar  [--anos 2010-2026]   # baixa 1 PDF por edição (fila retomável)
  python raspar.py renomear                     # padroniza nomes dos PDFs já baixados
  python raspar.py relatorio                    # contagens + exporta indice.csv
"""
import argparse, csv, datetime as dt, html, os, re, sqlite3, sys, time
import urllib.parse, urllib.request

BASE = "https://www.diariomunicipal.com.br/femurn"
ENTIDADE = "324"
INICIO = 2010
PAUSA = 1.0
UA = "Mozilla/5.0 (coleta de publicacoes oficiais publicas; contato do solicitante)"
PALAVRAS = ["educação", "escola", "escolar", "FUNDEB", "professor", "magistério", "ensino",
            "creche", "merenda", "pedagógico", "Secretaria Municipal da Educação",
            "Conselho Municipal de Educação", "PNAE", "PNATE", "alfabetização", "estudante", "aluno"]
RAIZ = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(RAIZ, "saida")


def get(url, tentativas=5):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read(), r.headers
        except Exception as e:
            espera = 2 ** i * 2
            print(f"  erro {e!r}; nova tentativa em {espera}s", flush=True)
            time.sleep(espera)
    raise RuntimeError("falhou: " + url)


def busca(texto, ini, fim, pag):
    p = {"busca_avancada[texto]": texto, "busca_avancada[titulo]": "", "busca_avancada[entidade]": ENTIDADE,
         "busca_avancada[orgao]": "", "busca_avancada[dataInicio]": ini, "busca_avancada[dataFim]": fim,
         "busca_avancada[ordenacao]": "antiga", "busca_avancada[Enviar]": "", "busca_avancada[pagina]": str(pag)}
    corpo, _ = get(f"{BASE}/pesquisar?" + urllib.parse.urlencode(p))
    h = corpo.decode("utf-8", "replace")
    m = re.search(r"de <strong>([\d.]+)</strong>", h)
    total = int(m.group(1).replace(".", "")) if m else 0
    itens = []
    for card in re.findall(r'<li class="materia-card">(.*?)</li>', h, re.S):
        cod = re.search(r"<code>(\w+)</code>", card)
        tit = re.search(r'materia-card__titulo">\s*<a[^>]*>(.*?)</a>', card, re.S)
        data = re.search(r"<dt>Circula[^<]*</dt>\s*<dd>(.*?)</dd>", card, re.S)
        ed = re.search(r"<dt>Edi[^<]*</dt>\s*<dd>\s*(\S*)\s*</dd>", card, re.S)
        org = re.search(r'materia-card__orgao">(.*?)</span>', card, re.S)
        if not (cod and data):
            continue
        itens.append(dict(cod=cod.group(1), titulo=html.unescape(tit.group(1)).strip() if tit else "",
                          data=data.group(1).strip(), edicao=(ed.group(1) if ed else ""),
                          orgao=html.unescape(org.group(1)).strip() if org else "",
                          pdf='/download/edicao/' in card))
    return total, itens


def db():
    os.makedirs(SAIDA, exist_ok=True)
    c = sqlite3.connect(os.path.join(SAIDA, "indice.db"))
    c.executescript("""
    CREATE TABLE IF NOT EXISTS materias(cod TEXT PRIMARY KEY, titulo TEXT, data TEXT, data_iso TEXT, edicao TEXT,
        orgao TEXT, tem_pdf INTEGER, palavras TEXT);
    CREATE TABLE IF NOT EXISTS buscas_feitas(ano INTEGER, palavra TEXT, total INTEGER, PRIMARY KEY(ano,palavra));
    CREATE TABLE IF NOT EXISTS edicoes(edicao TEXT, data_iso TEXT, cod_ref TEXT, arquivo TEXT, status TEXT, erro TEXT,
        PRIMARY KEY(edicao,data_iso));
    """)
    return c


def anos(arg):
    a, _, b = arg.partition("-")
    return range(int(a), int(b or a) + 1)


def indexar(c, faixa):
    hoje = dt.date.today()
    for ano in faixa:
        ini = f"{ano}-01-01"
        fim = min(dt.date(ano, 12, 31), hoje).isoformat()
        for palavra in PALAVRAS:
            if c.execute("SELECT 1 FROM buscas_feitas WHERE ano=? AND palavra=?", (ano, palavra)).fetchone():
                continue
            pag, total, lidos = 1, 0, 0
            while True:
                total, itens = busca(palavra, ini, fim, pag)
                for it in itens:
                    d = it["data"]
                    iso = f"{d[6:]}-{d[3:5]}-{d[:2]}"
                    r = c.execute("SELECT palavras FROM materias WHERE cod=?", (it["cod"],)).fetchone()
                    if r:
                        ps = set(filter(None, r[0].split("|"))) | {palavra}
                        c.execute("UPDATE materias SET palavras=? WHERE cod=?", ("|".join(sorted(ps)), it["cod"]))
                    else:
                        c.execute("INSERT INTO materias VALUES(?,?,?,?,?,?,?,?)",
                                  (it["cod"], it["titulo"], d, iso, it["edicao"], it["orgao"], int(it["pdf"]), palavra))
                lidos += len(itens)
                if not itens or lidos >= total:
                    break
                pag += 1
                time.sleep(PAUSA)
            c.execute("INSERT OR REPLACE INTO buscas_feitas VALUES(?,?,?)", (ano, palavra, total))
            c.commit()
            print(f"{ano} '{palavra}': {total} (lidos {lidos})", flush=True)
            time.sleep(PAUSA)
    n = c.execute("SELECT COUNT(*) FROM materias").fetchone()[0]
    print("matérias de educação no índice:", n)


def nome_pdf(ed, iso):
    """AAAA-MM-DD_edicao-NNNN.pdf: ordena por data e dá para buscar por data ou nº da edição."""
    return f"{iso}_edicao-{(ed or 'sn').zfill(4)}.pdf"


def renomear(c):
    for ed, iso, arq in c.execute("SELECT edicao,data_iso,arquivo FROM edicoes WHERE status='ok'").fetchall():
        novo = os.path.join(os.path.dirname(arq), nome_pdf(ed, iso))
        if arq != novo and os.path.exists(arq):
            os.rename(arq, novo)
            c.execute("UPDATE edicoes SET arquivo=? WHERE edicao=? AND data_iso=?", (novo, ed, iso))
            print("renomeado:", os.path.basename(arq), "->", os.path.basename(novo))
    c.commit()


def baixar(c, faixa):
    # 1 PDF por edição; usa o código de uma matéria da edição como referência
    c.execute("""INSERT OR IGNORE INTO edicoes(edicao,data_iso,cod_ref,status)
                 SELECT edicao,data_iso,MIN(cod),'pendente' FROM materias WHERE tem_pdf=1 GROUP BY edicao,data_iso""")
    c.commit()
    lim = f"{faixa[0]}-01-01", f"{faixa[-1]}-12-31"
    fila = c.execute("SELECT edicao,data_iso,cod_ref FROM edicoes WHERE status!='ok' AND data_iso BETWEEN ? AND ? "
                     "ORDER BY data_iso", lim).fetchall()
    print("edições na fila:", len(fila), flush=True)
    for i, (ed, iso, cod) in enumerate(fila, 1):
        pasta = os.path.join(SAIDA, "edicoes_pdf", iso[:4])
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, nome_pdf(ed, iso))
        try:
            corpo, h = get(f"{BASE}/download/edicao/{cod}")
            if not corpo.startswith(b"%PDF"):
                raise ValueError("resposta não é PDF (" + h.get("Content-Type", "?") + ")")
            with open(arq, "wb") as f:
                f.write(corpo)
            c.execute("UPDATE edicoes SET arquivo=?,status='ok',erro=NULL WHERE edicao=? AND data_iso=?", (arq, ed, iso))
            print(f"[{i}/{len(fila)}] ok {os.path.basename(arq)} ({len(corpo)//1024} KB)", flush=True)
        except Exception as e:
            c.execute("UPDATE edicoes SET status='erro',erro=? WHERE edicao=? AND data_iso=?", (str(e), ed, iso))
            print(f"[{i}/{len(fila)}] ERRO {ed} {iso}: {e}", flush=True)
        c.commit()
        time.sleep(PAUSA)


def relatorio(c):
    print("matérias por ano:")
    for ano, n in c.execute("SELECT substr(data_iso,1,4),COUNT(*) FROM materias GROUP BY 1 ORDER BY 1"):
        print(" ", ano, n)
    print("edições:", c.execute("SELECT status,COUNT(*) FROM edicoes GROUP BY status").fetchall())
    caminho = os.path.join(SAIDA, "indice.csv")
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["cod", "data", "edicao", "titulo", "orgao", "palavras", "pdf_edicao"])
        for r in c.execute("""SELECT m.cod,m.data,m.edicao,m.titulo,m.orgao,m.palavras,COALESCE(e.arquivo,'')
                              FROM materias m LEFT JOIN edicoes e ON e.edicao=m.edicao AND e.data_iso=m.data_iso
                              ORDER BY m.data_iso,m.cod"""):
            w.writerow(r)
    print("exportado:", caminho)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["indexar", "baixar", "renomear", "relatorio"])
    ap.add_argument("--anos", default=f"{INICIO}-{dt.date.today().year}")
    a = ap.parse_args()
    con = db()
    faixa = list(anos(a.anos))
    {"indexar": lambda: indexar(con, faixa), "baixar": lambda: baixar(con, faixa), "renomear": lambda: renomear(con), "relatorio": lambda: relatorio(con)}[a.cmd]()
