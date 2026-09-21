"""Quem e quem entre um quadro e o outro.

POR QUE ISTO E OBRIGATORIO e nao um refinamento: sem acompanhar a pessoa ao
longo do tempo, "ha um corpo deitado" e "este corpo CAIU" sao a mesma imagem. A
queda e uma afirmacao sobre o passado, e passado so existe com identidade.

Quando o detector ja devolve identidade — o `track()` do Ultralytics, que usa
ByteTrack — este arquivo apenas repassa. O casamento por sobreposicao abaixo e
para o caso em que nao ha: e simples de proposito, porque briga de dois alunos
correndo nao e o cenario de vigilancia para o qual ByteTrack foi feito, e um
rastreador ruim escondido atras de um nome bonito e pior que um simples
declarado.
"""
from . import medidas, regras

SUMIU_MS = 1500      # tempo sem ver antes de encerrar a trilha
IOU_MIN = 0.20       # sobreposicao minima para dizer "e a mesma pessoa"


def _iou(a, b):
    if a is None or b is None:
        return 0.0
    x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
    x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1])
    ub = (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(ua + ub - inter, 1e-9)


class Rebanho:
    """O conjunto de trilhas vivas, e a memoria dos pares para a briga."""

    def __init__(self):
        self.trilhas = {}
        self.pares = {}
        self._prox = 1

    def _nova(self, agora, ident=None):
        if ident is None:
            ident = self._prox
            self._prox += 1
        else:
            self._prox = max(self._prox, int(ident) + 1)
        t = regras.Trilha(int(ident), agora)
        self.trilhas[int(ident)] = t
        return t

    def quadro(self, deteccoes, asp, agora):
        """`deteccoes` e uma lista de (ident_ou_None, kp17). Devolve alertas."""
        vistos = set()

        # 1. quem ja veio com identidade do detector
        livres = []
        for ident, kp in deteccoes:
            if ident is None:
                livres.append(kp)
                continue
            t = self.trilhas.get(int(ident)) or self._nova(agora, ident)
            t._kp = kp
            vistos.add(t.id)

        # 2. o resto, por sobreposicao de caixa, do melhor par para o pior
        if livres:
            candidatas = [t for t in self.trilhas.values() if t.id not in vistos]
            pares = []
            for di, kp in enumerate(livres):
                cx = medidas.caixa(kp)
                for t in candidatas:
                    s = _iou(cx, getattr(t, "caixa", None))
                    if s >= IOU_MIN:
                        pares.append((s, di, t.id))
            pares.sort(reverse=True)
            usadas, tomadas = set(), set()
            for s, di, tid in pares:
                if di in usadas or tid in tomadas:
                    continue
                usadas.add(di); tomadas.add(tid)
                t = self.trilhas[tid]
                t._kp = livres[di]
                vistos.add(tid)
            for di, kp in enumerate(livres):
                if di not in usadas:
                    t = self._nova(agora)
                    t._kp = kp
                    vistos.add(t.id)

        # 3. analisar so quem foi visto NESTE quadro
        alertas = []
        for tid in list(vistos):
            t = self.trilhas[tid]
            t.caixa = medidas.caixa(t._kp)
            alertas += t.ver(t._kp, asp, agora)

        # 4. A briga vem DEPOIS de todas as trilhas analisadas, nunca no meio:
        #    e uma pergunta sobre pares, e no meio do laco metade das pessoas
        #    ainda esta com os numeros do quadro anterior.
        vivas = [self.trilhas[i] for i in vistos]
        alertas += regras.analisar_briga(vivas, agora, asp, self.pares)

        # 5. quem sumiu
        for tid, t in list(self.trilhas.items()):
            if agora - t.visto > SUMIU_MS:
                del self.trilhas[tid]
        return alertas
