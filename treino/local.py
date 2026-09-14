# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Treina a rede de queda juntando a base publica com amostras da SUA camera.

Por que juntar em vez de trocar: um modelo so do seu quarto acerta tudo no seu
quarto e ninguem sabe o que faz na escola — e um modelo so da base publica ja
nos mostrou o que faz num angulo que nunca viu. Os dois juntos cobrem o que
cada um nao cobre.

  1. Grave na Sala: escolha o rotulo, "Gravar amostra", faca a acao, pare.
     Vale a pena: ~10 quedas, ~10 corridas, e uns 10 minutos de normal.
  2. python3 treino/local.py            (mede e mostra, nao aplica nada)
  3. python3 treino/local.py --aplicar  (reescreve os pesos no auditix-sala.html)

As amostras ficam em treino/local/, fora do git: sao dados da casa de alguem.
"""
import argparse, json, os, re, sys
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import extrair as E
import treinar as T

AMOSTRAS = os.path.join(AQUI, "local", "amostras.jsonl")
SALA = os.path.join(os.path.dirname(AQUI), "auditix-sala.html")
QUEDA = {"queda"}          # o resto e tudo exemplo de "nao e queda"
MINIMO_AMOSTRAS = 8        # igual ao QUEDA_AMOSTRAS do auditix-sala.html
MIN_CLIPES = 5             # por classe, antes de deixar aplicar na Sala


def ler_amostras():
    """jsonl -> lista de (rotulo, sessao, janelas de 12 atributos)."""
    if not os.path.exists(AMOSTRAS):
        return []
    fora = []
    descartados = [0]
    for linha in open(AMOSTRAS, encoding="utf-8"):
        linha = linha.strip()
        if not linha:
            continue
        d = json.loads(linha)
        # os quadros vem intercalados por corpo; cada corpo e um clipe
        porcorpo = {}
        for q in d["quadros"]:
            porcorpo.setdefault(q["corpo"], []).append(q)
        # UM rotulo positivo vale para UMA pessoa. Se havia mais gente na sala
        # durante a gravacao de uma queda, cada corpo virava um clipe rotulado
        # "queda" — inclusive quem estava sentado do outro lado. Isso ensina
        # coisa errada E estraga a medicao, porque o rotulo do teste tambem fica
        # errado. Num rotulo negativo o problema nao existe: ninguem ali caiu,
        # entao todos os corpos sao exemplos validos de "nao e queda".
        if d["rotulo"] in QUEDA and len(porcorpo) > 1:
            principal = max(porcorpo, key=lambda c: len(porcorpo[c]))
            descartados[0] += len(porcorpo) - 1
            porcorpo = {principal: porcorpo[principal]}
        for corpo, qs in porcorpo.items():
            qs.sort(key=lambda q: q["t"])
            if len(qs) < E.JANELA // 2:
                continue
            # fps REAL desta gravacao, nao o presumido
            dur = (qs[-1]["t"] - qs[0]["t"]) / 1000.0
            fps = (len(qs) - 1) / dur if dur > 0.5 else float(d.get("fps", 30))
            g = [dict(hx=q["qx"], hy=q["qy"], altura=q["altura"], eixo=q["eixo"],
                      ang=q["ang"], ombro=q["ombro"], prop=q["prop"]) for q in qs]
            jan = int(round(fps))                  # sempre ~1 segundo de tempo real
            # A Sala descarta janelas com menos de QUEDA_AMOSTRAS (8) amostras.
            # Treinar com janelas que ela nunca vai produzir ensina o modelo sobre
            # um mundo que nao existe — e o teste de porte acusa a diferenca.
            if jan < MINIMO_AMOSTRAS:
                continue
            velho = (E.FPS, E.JANELA)
            # A Sala chama caracteristicasQueda(janela, janela.length): o "fps"
            # que ela usa E o numero de amostras. Passar o fps medido aqui daria
            # um dt diferente do dela e as contas divergiriam em silencio.
            E.FPS, E.JANELA = jan, jan
            try:
                w = [E.caracteristicas(g, i, i + jan)
                     for i in range(0, max(1, len(g) - jan + 1), max(1, jan // 6))]
            finally:
                E.FPS, E.JANELA = velho
            w = [x for x in w if x is not None and np.isfinite(x).all()]
            if w:
                fora.append((d["rotulo"], f'{d["sessao"]}-{corpo}', np.array(w, np.float32)))
    if descartados[0]:
        print(f"{descartados[0]} corpo(s) acompanhante(s) descartado(s) de gravacoes de "
              f"queda: o rotulo vale para quem caiu, nao para quem estava junto.\n")
    return fora


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="reescreve os pesos dentro do auditix-sala.html")
    ap.add_argument("--ignorar", default="", metavar="ROTULOS",
                    help="rotulos a deixar de fora, separados por virgula. "
                         "'deitar' costuma ser o caso: deitado e caido tem a MESMA "
                         "pose, e ensinar que um deles nao e queda tambem ensina a "
                         "perder quedas de verdade")
    args = ap.parse_args()

    locais = ler_amostras()
    ignorar = {x.strip() for x in args.ignorar.split(",") if x.strip()}
    if ignorar:
        antes_n = len(locais)
        locais = [t for t in locais if t[0] not in ignorar]
        print(f"ignorando {', '.join(sorted(ignorar))}: "
              f"{antes_n - len(locais)} clipes fora\n")
    if not locais:
        print("nenhuma amostra local em treino/local/amostras.jsonl.")
        print("grave algumas na Sala primeiro — veja o cabecalho deste arquivo.")
        return 1
    from collections import Counter
    conta = Counter(r for r, _, _ in locais)
    print("amostras da sua camera:")
    for r, n in sorted(conta.items()):
        janelas = sum(len(w) for rr, _, w in locais if rr == r)
        print(f"  {r:<10} {n:3d} clipes, {janelas:5d} janelas")
    # Uma classe só não ensina nada: com apenas quedas, o modelo aprende
    # "o que vem desta câmera é queda", e a métrica local sai 100% porque não
    # existe um único exemplo em que ele poderia errar. Já vi isso parecer um
    # ótimo resultado nesta mesma tela.
    quedas = conta.get("queda", 0)
    outras = sum(n for r, n in conta.items() if r not in QUEDA)
    falta = []
    if quedas < MIN_CLIPES:
        falta.append(f"quedas: {quedas} de {MIN_CLIPES}")
    if outras < MIN_CLIPES:
        falta.append(f"não-quedas (normal, agachar, deitar…): {outras} de {MIN_CLIPES}")
    if falta:
        print("\nDADOS INSUFICIENTES — " + "; ".join(falta))
        print("As duas classes precisam existir, e o 'normal' é o que mais importa:")
        print("é ele que ensina o modelo a NÃO disparar. Grave também os casos")
        print("difíceis de propósito: agachar, amarrar o sapato, deitar, sentar.")
        if args.aplicar:
            print("\n--aplicar recusado. Nada foi alterado.")
            return 1
        print("Seguindo só para mostrar os números — eles não valem muito ainda.\n")

    # ---- junta com a base publica -------------------------------------------
    d = np.load(os.path.join(AQUI, "janelas.npz"), allow_pickle=True)
    X, dono, rot, grupo = (d["X"].astype(np.float64), d["dono"],
                           d["rot"].astype(np.float64), d["grupo"])
    Xs, donos, rots, grupos = [X], [dono], [rot], [grupo]
    prox, gl = len(rot), int(grupo.max()) + 1
    sessoes = {}
    for rotulo, sessao, w in locais:
        Xs.append(w.astype(np.float64))
        donos.append(np.full(len(w), prox, np.int32))
        rots.append(np.array([1.0 if rotulo in QUEDA else 0.0]))
        grupos.append(np.array([gl + sessoes.setdefault(sessao, len(sessoes))], np.int16))
        prox += 1
    X = np.concatenate(Xs); dono = np.concatenate(donos)
    rot = np.concatenate(rots); grupo = np.concatenate(grupos)
    eh_local = grupo >= gl
    print(f"\ntotal: {len(rot)} clipes ({int(eh_local.sum())} seus), {len(X)} janelas")

    # ---- teste: cenarios da base que o modelo nunca viu + METADE das suas -----
    fora_base = [i for i, g in enumerate(grupo)
                 if not eh_local[i] and d["pastas"][g] in T.__dict__.get("TESTE", ())
                 or (not eh_local[i] and str(d["pastas"][g]).endswith("_s_3_keypoints_csv"))]
    locais_idx = np.where(eh_local)[0]
    rng = np.random.default_rng(7); rng.shuffle(locais_idx)
    meio = len(locais_idx) // 2
    idxte = np.array(sorted(set(fora_base) | set(locais_idx[:meio].tolist())))
    idxtr = np.array([i for i in range(len(rot)) if i not in set(idxte.tolist())])

    remap = -np.ones(len(rot), np.int64); remap[idxtr] = np.arange(len(idxtr))
    sel = remap[dono] >= 0
    Xtr, dtr, ytr = X[sel], remap[dono[sel]], rot[idxtr]
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8
    Xtr = (Xtr - mu) / sd
    remap2 = -np.ones(len(rot), np.int64); remap2[idxte] = np.arange(len(idxte))
    selte = remap2[dono] >= 0
    Xte, dte, yte = (X[selte] - mu) / sd, remap2[dono[selte]], rot[idxte]

    rede = T.Rede(X.shape[1], np.random.default_rng(T.SEMENTE))
    rede.treinar(Xtr, dtr, ytr)
    ptr = rede.nota_clipe(Xtr, dtr, len(idxtr))
    pte = rede.nota_clipe(Xte, dte, len(idxte))
    limiar = max(np.arange(0.05, 0.96, 0.01), key=lambda t: T.medir(ytr, ptr, t)["f1"])

    # O MODELO QUE JA ESTA NO AR, medido nos MESMOS clipes. Sem esta linha,
    # "71% na sua camera" nao quer dizer melhor nem pior — e trocar um modelo
    # sem saber se melhorou e so trocar.
    antes = os.path.join(AQUI, "modelo.json")
    if os.path.exists(antes):
        v = json.load(open(antes))
        Zv = (X[selte] - np.array(v["mu"])) / np.array(v["sd"])
        zv = np.tanh(Zv @ np.array(v["W1"]) + np.array(v["b1"])) @ np.array(v["W2"]) + v["b2"]
        mxv = np.full(len(idxte), -1e30); np.maximum.at(mxv, dte, zv)
        sv = np.zeros(len(idxte)); np.add.at(sv, dte, np.exp(T.TAU * (zv - mxv[dte])))
        pv = 1/(1+np.exp(-(mxv + np.log(sv)/T.TAU)))
    else:
        pv = None

    print(f"\nAUC teste {T.auc(yte, pte):.3f}   limiar {limiar:.2f}")
    m = T.medir(yte, pte, limiar)
    print(f"  tudo junto        precisao {m['prec']:.0%}  revocacao {m['rec']:.0%}  F1 {m['f1']:.2f}")
    so_local = np.isin(idxte, locais_idx)

    def linha(nome, y, p, pv_, lim_v):
        m = T.medir(y, p, limiar)
        txt = (f"  {nome:<18} precisao {m['prec']:.0%}  revocacao {m['rec']:.0%}"
               f"   ({len(y)} clipes: {m['vp']} certos, {m['fp']} falsos, {m['fn']} perdidos)")
        if pv_ is not None:
            mv = T.medir(y, pv_, lim_v)
            txt += (f"\n  {'  (o de hoje)':<18} precisao {mv['prec']:.0%}"
                    f"  revocacao {mv['rec']:.0%}"
                    f"   ({mv['vp']} certos, {mv['fp']} falsos, {mv['fn']} perdidos)")
        return txt

    lim_v = json.load(open(antes))["limiar"] if pv is not None else 0.5
    if so_local.sum():
        print(linha("SO a sua camera", yte[so_local], pte[so_local],
                    pv[so_local] if pv is not None else None, lim_v))
    if (~so_local).sum():
        print(linha("SO a base publica", yte[~so_local], pte[~so_local],
                    pv[~so_local] if pv is not None else None, lim_v))
    print("\nSo vale trocar se a SUA CAMERA melhorar sem a base piorar.")

    saida = os.path.join(AQUI, "local", "modelo.json")
    json.dump(dict(mu=mu.tolist(), sd=sd.tolist(), W1=rede.W1.tolist(),
                   b1=rede.b1.tolist(), W2=rede.W2.tolist(), b2=float(rede.b2),
                   limiar=float(limiar), auc_teste=float(T.auc(yte, pte))),
              open(saida, "w"), indent=1)
    print(f"\npesos em {saida}")

    if not args.aplicar:
        print("nada foi alterado. rode com --aplicar para colocar na Sala.")
        return 0

    # ---- reescreve as constantes na pagina ----------------------------------
    def bloco(nome, valor):
        return f"const {nome} = {json.dumps(valor)};"
    n = lambda a, c=5: [round(float(x), c) for x in a]
    novo = {
        "QUEDA_MU": n(mu), "QUEDA_SD": n(sd),
        "QUEDA_W1": [n(l) for l in rede.W1], "QUEDA_B1": n(rede.b1),
        "QUEDA_W2": n(rede.W2), "QUEDA_B2": round(float(rede.b2), 5),
        "QUEDA_LIMIAR": round(float(limiar), 2),
    }
    html = open(SALA, encoding="utf-8").read()
    for nome, valor in novo.items():
        padrao = re.compile(r"^const " + nome + r" = .*?;$", re.M | re.S)
        if not padrao.search(html):
            print(f"NAO ACHEI {nome} na pagina — nada foi alterado.")
            return 1
        html = padrao.sub(bloco(nome, valor).replace("\\", "\\\\"), html, count=1)
    open(SALA, "w", encoding="utf-8").write(html)

    # As provas que travam o porte para JS foram geradas com os pesos ANTIGOS:
    # deixadas como estao, o teste acusaria divergencia que nao existe, e a gente
    # aprenderia a ignorar o teste — que e pior do que nao ter teste.
    refazer_provas(mu, sd, rede, locais)
    print("auditix-sala.html e treino/provas.json atualizados.")
    print("confira com: node testes/rede-queda.mjs")
    return 0


def refazer_provas(mu, sd, rede, locais):
    """Reescreve provas.json com os pesos novos, usando as SUAS gravacoes."""
    casos = []
    for rotulo, sessao, _ in locais:
        pass
    for linha in open(AMOSTRAS, encoding="utf-8"):
        if not linha.strip():
            continue
        d = json.loads(linha)
        porcorpo = {}
        for q in d["quadros"]:
            porcorpo.setdefault(q["corpo"], []).append(q)
        for corpo, qs in porcorpo.items():
            qs.sort(key=lambda q: q["t"])
            dur = (qs[-1]["t"] - qs[0]["t"]) / 1000.0
            fps = (len(qs) - 1) / dur if dur > 0.5 else float(d.get("fps", 30))
            jan = int(round(fps))
            if jan < MINIMO_AMOSTRAS:
                continue
            g = [dict(hx=q["qx"], hy=q["qy"], altura=q["altura"], eixo=q["eixo"],
                      ang=q["ang"], ombro=q["ombro"], prop=q["prop"]) for q in qs]
            velho = (E.FPS, E.JANELA)
            E.FPS, E.JANELA = jan, jan
            try:
                for i in range(0, max(1, len(g) - jan + 1), max(1, jan)):
                    c = E.caracteristicas(g, i, i + jan)
                    if c is None or not np.isfinite(c).all():
                        continue
                    z = (np.array(c) - mu) / sd
                    nota = float(1/(1+np.exp(-(np.tanh(z @ rede.W1 + rede.b1) @ rede.W2
                                               + rede.b2))))
                    casos.append(dict(clipe=f'{d["rotulo"]}-{d["sessao"]}-{corpo}',
                        queda=1 if d["rotulo"] in QUEDA else 0, i=i, fps=jan,
                        # Seis casas, nao tres: aqui as coordenadas sao NORMALIZADAS
                        # (0 a 1), e nao pixels. Arredondar a tres apagava justamente
                        # a diferenca entre quadros, que e o que a prova mede.
                        quadros=[[round(x["hx"],6), round(x["hy"],6), round(x["altura"],6),
                                  round(x["eixo"],6), round(x["ang"],4), round(x["ombro"],6),
                                  round(x["prop"],5)] for x in g[i:i+jan]],
                        car=[round(float(v),6) for v in c], nota=round(nota, 6)))
            finally:
                E.FPS, E.JANELA = velho
            if len(casos) >= 40:
                break
        if len(casos) >= 40:
            break
    if not casos:
        print("AVISO: nao consegui gerar provas novas; o teste rede-queda vai acusar.")
        return
    # cada gravacao pode ter taxa de quadros propria, entao o fps vai por caso
    json.dump(dict(fps=casos[0]["fps"], janela=len(casos[0]["quadros"]), casos=casos),
              open(os.path.join(AQUI, "provas.json"), "w"))


if __name__ == "__main__":
    raise SystemExit(main())
