"""Raspagem do Diário Oficial de Baraúna/RN (FEMURN, entidade 324): só educação, só PDF das edições.

Uso:
  python raspar.py indexar [--anos 2010-2026]   # busca por palavras-chave, ano a ano, grava no SQLite
  python raspar.py baixar  [--anos 2010-2026]   # baixa 1 PDF por edição (fila retomável)
  python raspar.py renomear                     # padroniza nomes dos PDFs já baixados
  python raspar.py organizar                    # copia os PDFs para por_tipo/<leis|decretos|portarias|editais|...>/<ano>/
  python raspar.py relatorio                    # contagens + exporta indice.csv
"""
import argparse, csv, datetime as dt, html, os, re, sqlite3, sys, time
import unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.diariomunicipal.com.br/femurn"
ENTIDADE = "324"
INICIO = 2010
PAUSA = 1.0
UA = "Mozilla/5.0 (coleta de publicacoes oficiais publicas; contato do solicitante)"
PALAVRAS = ["educação", "escola", "escolar", "FUNDEB", "professor", "magistério", "ensino",
            "creche", "merenda", "pedagógico", "Secretaria Municipal da Educação",
            "Conselho Municipal de Educação", "PNAE", "PNATE", "alfabetização", "estudante", "aluno"]
RAIZ = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.environ.get("DIARIO_SAIDA") or os.path.join(RAIZ, "saida")


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


def chave_ed(ed):
    return ed.zfill(4) if ed else "sem-numero"


def nome_pdf(ed, iso, rot=""):
    """AAAA-MM-DD_ed-NNNN_<documentos>.pdf: ordena por data, acha por nº da edição e diz o que há dentro."""
    return f"{iso}_ed-{chave_ed(ed)}" + (f"_{rot}" if rot else "") + ".pdf"


# pasta -> padrão no título; vence o termo que aparece primeiro (ex.: "TERMO DE CONTRATO ... Lei 14.133" é contrato)
TIPOS = [("leis", r"\blei(?:s)?\b"), ("decretos", r"\bdecreto"), ("portarias", r"\bportaria"),
         ("editais", r"\bedital|\beditais"),
         ("contratos_licitacoes", r"\bcontrato|\baditivo|\blicita|\bdispensa|\bpreg[aã]o|\bhomologa|\badjudica|"
                                  r"\bchamada p[uú]blica|\btomada de pre|\bconcorr[eê]ncia|\binexigibilidade")]


ORDEM_TIPOS = ["leis", "decretos", "portarias", "editais", "contratos_licitacoes", "outros"]
ROT = {}  # (edicao, data_iso) -> [(tipo, rótulo)], carregado do índice por carregar_rotulos()


def slug(t, n=40):
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:n].rsplit("-", 1)[0] if len(t) > n and "-" in t[:n] else t[:n].strip("-")


def rotulo(titulo):
    """Título -> rótulo curto, ex.: 'PORTARIA Nº 419, DE 26 DE DEZEMBRO DE 2023.' -> 'portaria-419-2023'."""
    t = re.sub(r"^\s*\d+\s*[º°ª]\s*", "", titulo.strip())
    m = re.search(r"\d+", t)
    pref = slug(re.sub(r"[\s\-–—.]*\bn[º°o]?\.?\s*$", "", t[:m.start()], flags=re.I) if m else t, 36)
    if not pref:
        return slug(t, 40) or "documento"
    num = m.group(0) if m else ""
    ano = ""
    if m:
        a = re.search(r"/\s*(\d{4})\b", t[m.start():]) or re.search(r"(?:19|20)\d{2}(?!.*(?:19|20)\d{2})", t)
        ano = (a.group(1) if a and a.groups() else a.group(0)) if a else ""
    if num == ano:
        num = ""
    return "-".join(p for p in (pref, num, ano if ano != num else "") if p)


def juntar(rotulos, limite=110):
    """Até 3 rótulos (leis/decretos/portarias primeiro) + '+N-mais'; respeita o limite de tamanho do nome."""
    vistos = []
    for r in rotulos:
        if r not in vistos:
            vistos.append(r)
    usados = vistos[:3]
    while True:
        resto = len(vistos) - len(usados)
        s = "+".join(usados) + (f"+{resto}-mais" if resto else "")
        if len(s) <= limite or len(usados) <= 1:
            return s[:limite].strip("-+")
        usados = usados[:-1]


def carregar_rotulos(c):
    ROT.clear()
    for tit, ed, iso in c.execute("SELECT titulo,edicao,data_iso FROM materias ORDER BY data_iso,cod"):
        ROT.setdefault((ed, iso), []).append((tipo_de(tit), rotulo(tit)))
    for k, v in ROT.items():
        v.sort(key=lambda x: ORDEM_TIPOS.index(x[0]))


def caminho(ed, iso):
    return os.path.join(SAIDA, "edicoes_pdf", iso[:4], nome_pdf(ed, iso, juntar([r for _, r in ROT.get((ed, iso), [])])))


def tipo_de(titulo):
    t = titulo.lower()
    achados = [(m.start(), nome) for nome, pad in TIPOS if (m := re.search(pad, t))]
    return min(achados)[1] if achados else "outros"


def organizar(c):
    """Liga (link físico) o PDF de cada edição para por_tipo/<tipo>/<ano>/ (uma entrada por tipo presente na edição).
    A pasta edicoes_pdf/ segue como cópia mestre; o git deduplica o conteúdo idêntico."""
    import shutil
    n = 0
    raiz = os.path.join(SAIDA, "por_tipo")
    if os.path.isdir(raiz):
        shutil.rmtree(raiz)  # só tem links para edicoes_pdf/; os arquivos mestre não são tocados
    for ed, iso in c.execute("SELECT edicao,data_iso FROM edicoes WHERE status='ok'").fetchall():
        arq = caminho(ed, iso)
        if not os.path.exists(arq):
            continue
        por_tipo = {}
        for tipo, r in ROT.get((ed, iso), []):
            por_tipo.setdefault(tipo, []).append(r)
        for tipo, rs in por_tipo.items():
            dest = os.path.join(raiz, tipo, iso[:4])
            os.makedirs(dest, exist_ok=True)
            novo = os.path.join(dest, nome_pdf(ed, iso, juntar(rs)))
            if not os.path.exists(novo):
                try:
                    os.link(arq, novo)  # link físico: mesmo arquivo, sem ocupar espaço de novo
                except OSError:
                    shutil.copy2(arq, novo)
                n += 1
    print("cópias criadas:", n)
    for pasta in sorted(os.listdir(os.path.join(SAIDA, "por_tipo"))):
        total = sum(len(f) for _, _, f in os.walk(os.path.join(SAIDA, "por_tipo", pasta)))
        print(f"  {pasta}: {total} PDFs")


def renomear(c):
    """Põe nos PDFs o nome atual (data, edição e documentos) e guarda o caminho relativo a saida/."""
    import glob
    for ed, iso in c.execute("SELECT edicao,data_iso FROM edicoes WHERE status='ok'").fetchall():
        novo = caminho(ed, iso)
        pasta, k = os.path.dirname(novo), chave_ed(ed)
        candidatos = (glob.glob(os.path.join(glob.escape(pasta), f"{iso}_ed-{k}_*.pdf")) +
                      [os.path.join(pasta, n) for n in (f"{iso}_ed-{k}.pdf", f"{iso}_edicao-{k}.pdf",
                                                        f"{iso}_edicao-00sn.pdf", f"edicao-{ed}-{iso}.pdf")])
        for antigo in candidatos:
            if os.path.exists(antigo) and antigo != novo and not os.path.exists(novo):
                os.rename(antigo, novo)
                print("renomeado:", os.path.basename(antigo), "->", os.path.basename(novo))
        c.execute("UPDATE edicoes SET arquivo=? WHERE edicao=? AND data_iso=?",
                  (os.path.relpath(novo, SAIDA).replace(os.sep, "/"), ed, iso))
    c.commit()


def baixar(c, faixa, paralelo=4):
    # 1 PDF por edição; usa o código de uma matéria da edição como referência
    c.execute("""INSERT OR IGNORE INTO edicoes(edicao,data_iso,cod_ref,status)
                 SELECT edicao,data_iso,MIN(cod),'pendente' FROM materias WHERE tem_pdf=1 GROUP BY edicao,data_iso""")
    c.commit()
    lim = f"{faixa[0]}-01-01", f"{faixa[-1]}-12-31"
    fila = c.execute("SELECT edicao,data_iso,cod_ref FROM edicoes WHERE status!='ok' AND data_iso BETWEEN ? AND ? "
                     "ORDER BY data_iso", lim).fetchall()
    print(f"edições na fila: {len(fila)} (simultâneos: {paralelo})", flush=True)

    def um(item):
        ed, iso, cod = item
        arq = caminho(ed, iso)
        os.makedirs(os.path.dirname(arq), exist_ok=True)
        try:
            corpo, h = get(f"{BASE}/download/edicao/{cod}")
            if not corpo.startswith(b"%PDF"):
                raise ValueError("resposta não é PDF (" + h.get("Content-Type", "?") + ")")
            with open(arq + ".parte", "wb") as f:
                f.write(corpo)
            os.replace(arq + ".parte", arq)  # só aparece com o nome final quando está completo
            time.sleep(PAUSA)
            return item, arq, len(corpo), None
        except Exception as e:
            return item, arq, 0, str(e)

    with ThreadPoolExecutor(max_workers=paralelo) as ex:
        for i, (item, arq, tam, erro) in enumerate(ex.map(um, fila), 1):
            ed, iso, _ = item
            if erro:
                c.execute("UPDATE edicoes SET status='erro',erro=? WHERE edicao=? AND data_iso=?", (erro, ed, iso))
                print(f"[{i}/{len(fila)}] ERRO {ed} {iso}: {erro}", flush=True)
            else:
                c.execute("UPDATE edicoes SET arquivo=?,status='ok',erro=NULL WHERE edicao=? AND data_iso=?",
                          (os.path.relpath(arq, SAIDA).replace(os.sep, "/"), ed, iso))
                print(f"[{i}/{len(fila)}] ok {os.path.basename(arq)} ({tam//1024} KB)", flush=True)
            c.commit()


def relatorio(c):
    print("matérias por ano:")
    for ano, n in c.execute("SELECT substr(data_iso,1,4),COUNT(*) FROM materias GROUP BY 1 ORDER BY 1"):
        print(" ", ano, n)
    print("edições:", c.execute("SELECT status,COUNT(*) FROM edicoes GROUP BY status").fetchall())
    caminho = os.path.join(SAIDA, "indice.csv")
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["cod", "data", "edicao", "tipo", "titulo", "orgao", "palavras", "pdf_edicao"])
        for r in c.execute("""SELECT m.cod,m.data,m.edicao,m.titulo,m.orgao,m.palavras,COALESCE(e.arquivo,'')
                              FROM materias m LEFT JOIN edicoes e ON e.edicao=m.edicao AND e.data_iso=m.data_iso
                              ORDER BY m.data_iso,m.cod"""):
            w.writerow([r[0], r[1], r[2], tipo_de(r[3]), *r[3:]])
    print("exportado:", caminho)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["indexar", "baixar", "renomear", "organizar", "relatorio"])
    ap.add_argument("--anos", default=f"{INICIO}-{dt.date.today().year}")
    ap.add_argument("--paralelo", type=int, default=4, help="downloads simultâneos (baixar)")
    a = ap.parse_args()
    con = db()
    carregar_rotulos(con)
    faixa = list(anos(a.anos))
    {"indexar": lambda: indexar(con, faixa), "baixar": lambda: baixar(con, faixa, a.paralelo), "renomear": lambda: renomear(con), "organizar": lambda: organizar(con), "relatorio": lambda: relatorio(con)}[a.cmd]()
