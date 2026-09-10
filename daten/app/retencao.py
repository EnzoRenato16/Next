"""Descarte automatico de biometria — LGPD Art. 14.

    python -m app.retencao          # mostra o que venceu e apaga
    python -m app.retencao --ver    # so mostra, nao apaga

Biometria de crianca e adolescente nao pode ficar guardada para sempre, e
"apagar quando o aluno sai da escola" nao acontece sozinho: ninguem lembra de
avisar o sistema que alguem saiu. Entao sao dois relogios, e o primeiro que
vencer apaga:

  RETENCAO_DIAS      prazo do consentimento, contado do cadastro. Vencer aqui
                     significa que a autorizacao expirou; para voltar, tem que
                     recadastrar com autorizacao nova.
  INATIVIDADE_DIAS   contado da ultima vez que a pessoa foi reconhecida. E o
                     unico jeito automatico de perceber que alguem saiu: quem
                     saiu da escola para de ser visto.

O que "apagar" significa aqui, e por que sao dois lugares:
  - a linha em students (SQLite), e
  - as amostras dela em data/embeddings.npz.
Apagar so o primeiro deixaria o rosto reconhecivel, que e exatamente o dado
que a lei manda descartar. Por isso o expurgo mora neste modulo e nao no db.py.

O que NAO e apagado: a presenca ja registrada em attendance. Isso e registro
escolar (fulano esteve na aula tal), nao biometria, e some com ele o historico
que a escola precisa manter.

Roda sozinho no startup da API (app/main.py). Tambem da para agendar:
    0 3 * * *  cd ~/eduvision && .venv/bin/python -m app.retencao
"""

import sys

import numpy as np

from . import config, db


def expurgar(simular: bool = False) -> list:
    """Apaga (ou so lista, se simular) todo mundo que passou do prazo.

    Devolve a lista de vencidos, cada um com o motivo.
    """
    vencidos = db.expired_students()
    if not vencidos or simular:
        return vencidos

    ids = {v["student_id"] for v in vencidos}
    _remover_embeddings(ids)

    for v in vencidos:
        db.delete_student(v["student_id"])
        # Fica no log de seguranca: descarte de dado sensivel e o tipo de coisa
        # que a escola precisa conseguir provar que fez.
        db.log_security_event(
            "biometria_descartada",
            f"{v['name']} ({v['student_id']}) — {v['motivo']}",
            0.0,
        )
    return vencidos


def _remover_embeddings(ids: set) -> int:
    """Reescreve data/embeddings.npz sem as pessoas informadas.

    Devolve quantas amostras sairam. Sem arquivo, nao ha o que fazer.
    """
    if not config.EMBEDDINGS_PATH.exists():
        return 0

    dados = np.load(config.EMBEDDINGS_PATH, allow_pickle=True)
    todos_ids = np.array(dados["ids"], dtype=object)
    manter = np.array([i not in ids for i in todos_ids], dtype=bool)
    removidas = int((~manter).sum())
    if not removidas:
        return 0

    np.savez(
        config.EMBEDDINGS_PATH,
        embeddings=dados["embeddings"][manter].astype(np.float32),
        ids=todos_ids[manter],
        names=np.array(dados["names"], dtype=object)[manter],
    )
    return removidas


def main() -> int:
    simular = "--ver" in sys.argv

    db.init_db()
    pessoas = db.students_status()

    print(f"Prazo de consentimento: {config.RETENCAO_DIAS} dias")
    print(f"Prazo de inatividade  : {config.INATIVIDADE_DIAS} dias")
    print()

    if not pessoas:
        print("Nenhum cadastro.")
        return 0

    for p in pessoas:
        if p["expira_em"] <= 0:
            estado = f"VENCIDO ({p['motivo']})"
        elif p["expira_em"] <= 30:
            estado = f"vence em {p['expira_em']:.0f} dias"
        else:
            estado = f"ok, {p['expira_em']:.0f} dias"
        print(f"  {p['name']:<24} {estado}")

    vencidos = expurgar(simular=simular)
    print()
    if not vencidos:
        print("Nada a descartar.")
    elif simular:
        print(f"{len(vencidos)} venceu(ram). Rode sem --ver para apagar.")
    else:
        print(f"{len(vencidos)} biometria(s) descartada(s):")
        for v in vencidos:
            print(f"  - {v['name']} ({v['motivo']})")
        print("Embeddings e cadastro removidos. Presenca registrada foi mantida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
