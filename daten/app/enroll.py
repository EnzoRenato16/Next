"""Cadastro (enrollment) dos membros do grupo — Passo 10 do roteiro.

Como usar:
  1. Crie uma subpasta por pessoa em data/faces/ com 2+ fotos de rosto:
        data/faces/enzo/1.jpg
        data/faces/enzo/2.jpg
        data/faces/luan/1.jpg
     (o nome da pasta vira o student_id; use RM se quiser)
  2. Rode:
        python -m app.enroll
     Isso gera data/embeddings.npz e popula a tabela students.

Boa pratica do roteiro: capture mais de uma amostra autorizada por pessoa;
nao salve fotos desnecessarias.

O cadastro tem PRAZO (LGPD Art. 14): vence pelo consentimento
(config.RETENCAO_DIAS) ou por inatividade (config.INATIVIDADE_DIAS), e some
sozinho quando vence. Veja app/retencao.py.
"""

import sys

import numpy as np
import cv2

from . import config, db
from .recognizer import FaceEngine

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> int:
    db.init_db()
    engine = FaceEngine()

    config.FACES_DIR.mkdir(parents=True, exist_ok=True)
    people = [p for p in sorted(config.FACES_DIR.iterdir()) if p.is_dir()]
    if not people:
        print(f"Nenhuma pasta de pessoa em {config.FACES_DIR}.")
        print("Crie data/faces/<nome>/ com fotos e rode de novo.")
        return 1

    embeddings, ids, names = [], [], []
    for person in people:
        student_id = person.name
        # Nome bonito = pasta capitalizada; ajuste manualmente se quiser.
        name = student_id.replace("_", " ").title()
        photos = [f for f in sorted(person.iterdir()) if f.suffix.lower() in IMG_EXT]
        if not photos:
            print(f"[pular] {student_id}: sem fotos.")
            continue

        count = 0
        for photo in photos:
            img = cv2.imread(str(photo))
            if img is None:
                print(f"  [erro] nao abriu {photo.name}")
                continue
            # Cadastro roda em resolucao CHEIA: foto parada nao tem pressa, e
            # landmark melhor gera embedding melhor. O frame-skip e a reducao
            # de largura sao otimizacao de video ao vivo, nao de cadastro.
            faces = engine.detect(img, full_res=True)
            if len(faces) == 0:
                print(f"  [aviso] nenhum rosto em {photo.name}")
                continue
            # Usa o rosto de maior area (col 2,3 = largura,altura no formato YuNet).
            biggest = max(faces, key=lambda f: f[2] * f[3])
            feat = engine.embedding(img, biggest)
            embeddings.append(feat)
            ids.append(student_id)
            names.append(name)
            count += 1
        print(f"[ok] {name} ({student_id}): {count} amostra(s)")
        if count:
            db.upsert_student(student_id, name, config.GROUP_ID)

    if not embeddings:
        print("Nenhum embedding gerado. Verifique as fotos (rosto visivel).")
        return 1

    np.savez(
        config.EMBEDDINGS_PATH,
        embeddings=np.array(embeddings, dtype=np.float32),
        ids=np.array(ids, dtype=object),
        names=np.array(names, dtype=object),
    )
    print(f"\nCadastro salvo em {config.EMBEDDINGS_PATH} "
          f"({len(embeddings)} amostras de {len(set(ids))} pessoa(s)).")
    print(f"Prazo de consentimento: {config.RETENCAO_DIAS} dias. "
          f"Some sozinho apos {config.INATIVIDADE_DIAS} dias sem ser visto.")
    print("Conferir a qualquer momento: python -m app.retencao --ver")
    return 0


if __name__ == "__main__":
    sys.exit(main())
