"""Classifica cada matéria: trata de educação de fato (1) ou só menciona o tema (0).

Usa o texto da matéria (python raspar.py textos). Critérios, em ordem:
  1. emissor: o cabeçalho da matéria é da Secretaria/Conselho de Educação;
  2. cabeça: título + ementa (começo do texto) já traz termo forte de educação;
  3. corpo: vários termos fortes distintos, ou densidade alta de termos de educação.
Uso: python raspar.py classificar   (ou python relevancia.py [--tudo] [--amostra N])
"""
import argparse, os, re, sqlite3, sys, unicodedata
from raspar import SAIDA

def norm(s):
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()

# Termos que, sozinhos, indicam assunto de educação (não só menção).
FORTES = [
    "secretaria municipal da educacao", "secretaria municipal de educacao", "secretario municipal da educacao",
    "secretaria de educacao", "conselho municipal de educacao", "conselho do fundeb", "fundeb", "pnae", "pnate", "pdde",
    "merenda", "alimentacao escolar", "transporte escolar", "escola municipal", "escolas municipais", "unidade escolar",
    "unidades escolares", "rede municipal de ensino", "rede publica de ensino", "magisterio", "professor", "professora",
    "profissionais da educacao", "educacao infantil", "ensino fundamental", "creche", "alfabetizacao",
    "calendario escolar", "ano letivo", "matricula escolar", "plano municipal de educacao", "gestao escolar",
    "material didatico", "livro didatico", "sigeduc", "ideb", "saeb", "diretor escolar", "diretora de creche", "coordenador pedagogico", "orientacao pedagogica",
    "fardamento escolar", "uniforme escolar", "material escolar", "jornada pedagogica", "supervisao pedagogica", "supervisor pedagogico", "formacao continuada", "carreira do magisterio",
]
# Termos fracos: aparecem muito em matérias de outros assuntos.
FRACOS = ["educacao", "escola", "escolar", "ensino", "aluno", "estudante", "pedagogic", "estudantil"]
EMISSOR = re.compile(r"secretari[ao] municipal (da|de) educacao|secretari[ao] (da|de) educacao|conselho municipal de educacao|conselho (do|de) fundeb|"
                     r"conselho de alimentacao escolar|\bcae\b")


def contar(termos, t):
    return sum(len(re.findall(r"\b" + re.escape(x), t)) for x in termos)


def limpar(texto):
    """Tira o resíduo da tag <div id="materia"> do começo do texto."""
    return re.sub(r'^id="materia"[^>]*>\s*', "", texto)


def avaliar(titulo, texto):
    t = norm(limpar(texto))
    palavras = max(len(t.split()), 1)
    # cabeçalho: logo depois do título, antes do corpo (cerca de 400 caracteres)
    cab = t[:600]
    cabeca = norm(titulo) + " " + t[:1500]
    distintos = sum(1 for x in FORTES if re.search(r"\b" + re.escape(x), t))
    fortes = contar(FORTES, t)
    fracos = contar(FRACOS, t)
    dens = (fortes * 2 + fracos) * 1000 / palavras
    if EMISSOR.search(cab):
        return 1, "emitida pela área de educação"
    if any(re.search(r"\b" + re.escape(x), cabeca) for x in FORTES) or \
       re.search(r"\b(educacao|escolar|escola|pedagogic\w*|alunos?|estudantes?)\b", norm(titulo) + " " + t[:700]):
        return 1, "tema na ementa/título"
    if distintos >= 4:
        return 1, f"{distintos} termos específicos no corpo"
    if dens >= 12 and fortes >= 3:
        return 1, "densidade alta de termos de educação"
    return 0, "só menciona"


def classificar(c, tudo=False, amostra=0):
    """Classifica as matérias com texto disponível (textos.db) que ainda não têm relevância."""
    from raspar import db_textos
    t = db_textos()
    filtro = "" if tudo else "WHERE relevante IS NULL"
    pend = [r for r in c.execute(f"SELECT cod,titulo FROM materias {filtro}")]
    n = 0
    for cod, tit in pend:
        row = t.execute("SELECT texto FROM textos WHERE cod=?", (cod,)).fetchone()
        if not row:
            continue
        r, motivo = avaliar(tit, row[0])
        c.execute("UPDATE materias SET relevante=?,motivo=? WHERE cod=?", (r, motivo, cod))
        n += 1
    c.commit()
    print("classificadas agora:", n)
    for r, k in c.execute("SELECT relevante,COUNT(*) FROM materias GROUP BY 1"):
        print({1: "educação de fato", 0: "só menciona", None: "sem classificação"}[r], k)
    for m, k in c.execute("SELECT motivo,COUNT(*) FROM materias GROUP BY 1 ORDER BY 2 DESC"):
        print(" -", m, k)
    if amostra:
        for r in (1, 0):
            print("\n=== amostra", "RELEVANTES" if r else "SÓ MENÇÃO")
            for cod, tit, mot in c.execute("SELECT cod,titulo,motivo FROM materias WHERE relevante=? ORDER BY random() LIMIT ?", (r, amostra)):
                print(f"{cod} | {mot} | {tit[:90]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--amostra", type=int, default=0)
    ap.add_argument("--tudo", action="store_true", help="reclassifica também o que já tem relevância")
    a = ap.parse_args()
    from raspar import db
    classificar(db(), a.tudo, a.amostra)


if __name__ == "__main__":
    main()
