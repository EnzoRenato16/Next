"""O juiz da arena decide certo?   python3 testes/arena_juiz.py

Sem camera e sem rosto de verdade: vetores de 128 numeros feitos para imitar o
SFace. A "mesma pessoa" e o vetor dela mais ruido, ajustado para dar cosseno
parecido com o que o SFace da entre duas fotos da mesma pessoa (0,4 a 0,7), e
"outra pessoa" e um vetor sorteado (cosseno perto de 0).

O que este arquivo cobra e a regra da prova: AUTORIZADO so com evidencia, o
desconhecido nunca vira autorizado, o mesmo desconhecido nao conta duas vezes,
e o placar sai do estado de cada trilha.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aibox import arena  # noqa: E402

rng = np.random.default_rng(42)
falhas = 0


def ok(nome, cond, det=""):
    global falhas
    print(("  ok   " if cond else "  FALHA ") + nome + (f"   {det}" if det else ""))
    if not cond:
        falhas += 1


def unit(v):
    return v / np.linalg.norm(v)


def parecido(base, cos):
    """Um vetor com cosseno ~cos com a base."""
    r = unit(rng.normal(size=128))
    r = unit(r - (r @ base) * base)
    return unit(cos * base + np.sqrt(1 - cos ** 2) * r)


pessoas = {n: unit(rng.normal(size=128)) for n in ("Ana", "Bruno", "Carla")}
nomes = sorted(pessoas)
linhas, dono = [], []
for i, n in enumerate(nomes):
    for _ in range(6):                       # 6 fotos de cada, todas parecidas
        linhas.append(parecido(pessoas[n], 0.75))
        dono.append(i)
M = np.array([unit(v) for v in linhas], np.float32)


def novo_juiz():
    return arena.Juiz(nomes, M, dono)


print("\n== autorizado ==")
j = novo_juiz()
ev = []
for k in range(arena.MINIMO):
    ev += j.ler("c1-1", parecido(pessoas["Bruno"], 0.6), k)
ok("Bruno vira autorizado com o minimo de leituras", j.trilhas["c1-1"].estado == "autorizado"
   and j.trilhas["c1-1"].nome == "Bruno", j.trilhas["c1-1"].estado)
ok("e isso vira UM evento", len([e for e in ev if e["tipo"] == "autorizado"]) == 1)

j = novo_juiz()
j.ler("c1-1", parecido(pessoas["Ana"], 0.6))
ok("uma leitura so nao basta", j.trilhas["c1-1"].estado == "analisando")

print("\n== desconhecido ==")
j = novo_juiz()
estranho = unit(rng.normal(size=128))
for k in range(arena.MINIMO_DESC):
    j.ler("c1-7", parecido(estranho, 0.6), k)
ok("rosto longe de todos vira desconhecido", j.trilhas["c1-7"].estado == "desconhecido")
ok("e e o desconhecido #1", j.trilhas["c1-7"].numero == 1)

for k in range(20):
    j.ler("c1-7", parecido(estranho, 0.6), 10 + k)
ok("e continua desconhecido com mais leituras (nunca vira autorizado)",
   j.trilhas["c1-7"].estado == "desconhecido")

print("\n== o mesmo desconhecido sai e volta ==")
for k in range(arena.MINIMO_DESC):
    j.ler("c1-9", parecido(estranho, 0.6), 40 + k)
r = j.resumo()
ok("trilha nova da mesma pessoa NAO vira segundo alerta", r["desconhecidos"] == [1],
   str(r["desconhecidos"]))
outro = unit(rng.normal(size=128))
for k in range(arena.MINIMO_DESC):
    j.ler("c1-12", parecido(outro, 0.6), 60 + k)
ok("outra pessoa desconhecida vira o #2", j.resumo()["desconhecidos"] == [1, 2],
   str(j.resumo()["desconhecidos"]))

print("\n== dois desconhecidos parecidos AO MESMO TEMPO sao dois ==")
# Na camera HAIZ, tres estranhos viraram um alerta. Quem esta na tela junto
# com outro desconhecido e outra pessoa, por mais que os rostos se parecam.
j = novo_juiz()
gemeo = unit(rng.normal(size=128))
while max(abs(float(gemeo @ v)) for v in pessoas.values()) > 0.1:   # longe da galeria
    gemeo = unit(rng.normal(size=128))
for k in range(arena.MINIMO_DESC):
    j.ler("c1-30", parecido(gemeo, 0.9), k * 0.2)
    j.ler("c1-31", parecido(gemeo, 0.9), k * 0.2 + 0.1)
ok("viram dois alertas", j.resumo()["desconhecidos"] == [1, 2],
   str(j.resumo()["desconhecidos"]))
for k in range(arena.MINIMO_DESC):
    j.ler("c1-32", parecido(gemeo, 0.9), 20 + k * 0.2)
ok("e quem volta DEPOIS, sozinho, continua sendo um deles",
   len(j.resumo()["desconhecidos"]) == 2 and j.trilhas["c1-32"].numero in (1, 2),
   f"{j.resumo()['desconhecidos']} {j.trilhas['c1-32'].numero}")
j2 = novo_juiz()
for k in range(arena.MINIMO_DESC):
    j2.ler("c1-40", parecido(gemeo, 0.9), 1 + k * 0.3)        # ate 2,2 s
for k in range(arena.MINIMO_DESC):
    j2.ler("c1-41", parecido(gemeo, 0.9), 2.5 + k * 0.3)      # comeca 0,3 s depois
ok("quem anda rapido e volta com outro numero logo em seguida e UM alerta",
   j2.resumo()["desconhecidos"] == [1], str(j2.resumo()["desconhecidos"]))
ok("e isso aparece como 'juntou', com a nota", any(
    e["tipo"] == "juntou" and e["parecido"] is not None for e in j.eventos))

print("\n== limite de juntar desconhecidos por motor ==")
arena.configurar("arcface")
ok("ArcFace junta so com 0,60", arena.MESMO_DESCONHECIDO == 0.60, str(arena.MESMO_DESCONHECIDO))
arena.configurar("sface")
ok("SFace continua 0,45", arena.MESMO_DESCONHECIDO == 0.45, str(arena.MESMO_DESCONHECIDO))

print("\n== o parecido perigoso ==")
# Um desconhecido que lembra a Carla (cosseno 0,3 com ela): nao pode virar
# autorizado. E o "meliante" da prova.
j = novo_juiz()
sosia = parecido(pessoas["Carla"], 0.3)
for k in range(30):
    j.ler("c2-1", parecido(sosia, 0.65), k)
t = j.trilhas["c2-1"]
ok("quem so lembra uma autorizada nao vira autorizado", t.estado != "autorizado",
   f"{t.estado} {t.nome} nota {t.nota:.2f}")

print("\n== rosto ruim no comeco, bom depois ==")
j = novo_juiz()
for k in range(arena.MINIMO_DESC):
    j.ler("c1-3", parecido(pessoas["Ana"], 0.15), k)       # quase irreconhecivel
era = j.trilhas["c1-3"].estado
for k in range(arena.JANELA):
    j.ler("c1-3", parecido(pessoas["Ana"], 0.65), 10 + k)  # agora de frente
t = j.trilhas["c1-3"]
ok("comecou desconhecida", era == "desconhecido", era)
ok("e virou Ana quando o rosto ficou bom", t.estado == "autorizado" and t.nome == "Ana",
   f"{t.estado} {t.nome}")
ok("e saiu da conta de desconhecidos", j.resumo()["desconhecidos"] == [])
ok("o evento diz que ela era o desconhecido #1",
   any(e.get("era_desconhecido") == 1 for e in j.eventos))

print("\n== autorizado nao vira desconhecido por virar o rosto ==")
j = novo_juiz()
for k in range(arena.MINIMO):
    j.ler("c1-4", parecido(pessoas["Carla"], 0.6), k)
for k in range(30):
    j.ler("c1-4", parecido(pessoas["Carla"], 0.42), 10 + k)  # leituras fracas, dela
ok("Carla continua autorizada", j.trilhas["c1-4"].estado == "autorizado"
   and j.trilhas["c1-4"].nome == "Carla", f"{j.trilhas['c1-4'].estado}")
ok("e nenhuma troca foi acusada", not any(e["tipo"] == "troca" for e in j.eventos))

print("\n== a trilha do autorizado passa para outra pessoa ==")
# Duas pessoas se cruzam e o rastreador entrega a trilha da Carla para um
# estranho. Ele nao pode herdar o nome dela.
j = novo_juiz()
for k in range(arena.MINIMO):
    j.ler("c1-5", parecido(pessoas["Carla"], 0.6), k)
intruso = unit(rng.normal(size=128))
while max(abs(float(intruso @ v)) for v in pessoas.values()) > 0.1:  # longe da galeria
    intruso = unit(rng.normal(size=128))
for k in range(arena.JANELA + arena.MAXIMO):     # tempo de sobra para o juiz decidir
    j.ler("c1-5", parecido(intruso, 0.6), 10 + k)
t = j.trilhas["c1-5"]
ok("a troca e acusada", any(e["tipo"] == "troca" and e["nome"] == "Carla"
                             for e in j.eventos))
ok("o estranho vira desconhecido, nao Carla", t.estado == "desconhecido",
   f"{t.estado} {t.nome}")
ok("e Carla continua no placar, porque ja foi identificada",
   j.resumo()["autorizados"] == ["Carla"], str(j.resumo()["autorizados"]))
ok("e o alerta do estranho conta", j.resumo()["desconhecidos"] == [1])
troca = next(e for e in j.eventos if e["tipo"] == "troca")
alerta = next(e for e in j.eventos if e["tipo"] == "desconhecido")
ok("o tempo ate decidir do estranho conta da troca, nao de quando a Carla chegou",
   alerta["levou"] == round(alerta["quando"] - troca["quando"], 2),
   f"levou {alerta['levou']} s, troca em {troca['quando']} s")
ok("e a Carla teve o dela", next(e for e in j.eventos if e["tipo"] == "autorizado")["levou"]
   == arena.MINIMO - 1)

print("\n== o .env vale ==")
# carregar_env roda dentro do main, depois do import: os limiares tem de ser
# relidos ali, senao o ARENA_LIMIAR calibrado no laboratorio e ignorado.
antes = arena.LIMIAR
os.environ["ARENA_LIMIAR"] = "0.31"
arena.configurar()
ok("ARENA_LIMIAR lido depois do import vale", arena.LIMIAR == 0.31, str(arena.LIMIAR))
del os.environ["ARENA_LIMIAR"]
arena.configurar()
ok("e sem ele volta ao padrao", arena.LIMIAR == antes)

print("\n== o placar ==")
j = novo_juiz()
for n, tid in (("Ana", "c1-1"), ("Bruno", "c1-2"), ("Ana", "c2-5")):
    for k in range(arena.MINIMO):
        j.ler(tid, parecido(pessoas[n], 0.6), k)
for k in range(arena.MINIMO_DESC):
    j.ler("c1-8", parecido(estranho, 0.6), k)
r = j.resumo()
ok("Ana em duas cameras conta uma vez", r["autorizados"] == ["Ana", "Bruno"],
   str(r["autorizados"]))
ok("total da galeria", r["total_autorizados"] == 3)
ok("um desconhecido", len(r["desconhecidos"]) == 1)

print("\n== qualidade da leitura ==")
# linha do YuNet: x, y, w, h, olho_d(x,y), olho_e(x,y), nariz(x,y), boca(2x2), nota
frente = [100, 100, 60, 70, 115, 125, 145, 125, 130, 140, 118, 155, 142, 155, 0.92]
lado = list(frente)
lado[8] = 153                                              # nariz alem do olho
tres_quartos = list(frente)
tres_quartos[8] = 144                                      # virado 0,47: vale desde 20/10
pequeno = list(frente)
pequeno[2] = 20
ok("rosto de frente vale", arena.leitura_boa(np.array(frente))[0])
ok("rosto de lado nao vale", not arena.leitura_boa(np.array(lado))[0])
ok("rosto meio virado (3/4) vale", arena.leitura_boa(np.array(tres_quartos))[0],
   f"{arena.virado(tres_quartos):.2f}")
os.environ["ARENA_FRENTE"] = "0.35"
arena.configurar()
ok("ARENA_FRENTE do .env vale", not arena.leitura_boa(np.array(tres_quartos))[0])
del os.environ["ARENA_FRENTE"]
arena.configurar()
ok("rosto pequeno nao vale", not arena.leitura_boa(np.array(pequeno))[0])

print("\n== rastreador ==")
r = arena.Rastreador("c1")
a = r.associar([(100, 100, 60, 60)], 0.0)
b = r.associar([(120, 105, 60, 60)], 0.25)
c = r.associar([(600, 100, 60, 60)], 0.5)
ok("o mesmo rosto andando continua na mesma trilha", a == b, f"{a} {b}")
ok("rosto longe e trilha nova", c != a)
# HAIZ, 20/10: estranho de 54 px some ao fundo e o Samuel entra no mesmo ponto
# com 179 px. Nao pode herdar a trilha (o alerta do estranho sumia do placar).
r = arena.Rastreador("c1")
a = r.associar([(500, 300, 54, 60)], 0.0)
b = r.associar([(470, 260, 179, 200)], 0.4)
c = r.associar([(475, 262, 185, 205)], 0.6)
ok("rosto que triplica de tamanho e outra trilha", a != b, f"{a} {b}")
ok("e o rosto grande continua na trilha dele", b == c, f"{b} {c}")

print("\n== nota pela media das melhores fotos (ARENA_TOPK) ==")
# Um estranho que acerta UMA foto da Ana por sorte (0,5) e erra as outras.
sorte = [parecido(pessoas["Ana"], 0.75)] + [unit(rng.normal(size=128)) for _ in range(5)]
Mt = np.array([unit(v) for v in sorte + [parecido(pessoas["Bruno"], 0.75)
                                         for _ in range(6)]], np.float32)
dt = [0] * 6 + [1] * 6
leitura = parecido(Mt[0], 0.5)              # cosseno 0,5 com a foto de sorte
topk_antes = os.environ.pop("ARENA_TOPK", None)
arena.configurar()
um = arena.Juiz(["Ana", "Bruno"], Mt, dt)._por_pessoa(leitura)[0]
os.environ["ARENA_TOPK"] = "3"
arena.configurar()
tres = arena.Juiz(["Ana", "Bruno"], Mt, dt)._por_pessoa(leitura)[0]
del os.environ["ARENA_TOPK"]
arena.configurar()
ok("a sorte numa foto so pesa menos com a media das 3 melhores", tres < um - 0.1,
   f"melhor foto {um:.2f}, media das 3 {tres:.2f}")
ok("e sem a variavel volta a ser a melhor foto", arena.TOPK == 1)
if topk_antes is not None:
    os.environ["ARENA_TOPK"] = topk_antes
    arena.configurar()

print("\n== o nome na tela segue a ultima leitura ==")
j = novo_juiz()
for k in range(arena.MINIMO):
    j.ler("c1-20", parecido(pessoas["Bruno"], 0.6), k)
ok("autorizado aparece com o nome", arena.rotulo(j, "c1-20", "")[1].startswith("AUTORIZADO"))
outro = unit(rng.normal(size=128))
while max(abs(float(outro @ v)) for v in pessoas.values()) > 0.1:
    outro = unit(rng.normal(size=128))
j.ler("c1-20", parecido(outro, 0.6), 10)
ok("outro rosto na trilha: a tela diz conferindo, nao o nome",
   arena.rotulo(j, "c1-20", "")[1] == "conferindo", arena.rotulo(j, "c1-20", "")[1])
ok("e o placar continua com o Bruno", j.resumo()["autorizados"] == ["Bruno"])
j.ler("c1-20", parecido(pessoas["Bruno"], 0.6), 11)
ok("o Bruno volta e o nome volta", arena.rotulo(j, "c1-20", "")[1].startswith("AUTORIZADO"))

print("\n== cadastro pelo botao (modo preparo) ==")
c = arena.Coleta("Ana", 0.0)
va, vb = parecido(pessoas["Ana"], 0.7), parecido(pessoas["Bruno"], 0.7)
ok("sem rosto, espera", c.ver([], 0.1) is None and not c.vetores)
ok("rosto longe nao vale", c.ver([(60, va)], 0.2) is None and not c.vetores, c.msg)
ok("dois rostos do mesmo tamanho nao valem", c.ver([(120, va), (110, vb)], 0.3) is None
   and not c.vetores, c.msg)
ok("o maior, bem maior que o segundo, vale", c.ver([(150, va), (40, vb)], 0.4) is None
   and len(c.vetores) == 1, c.msg)
ok("antes do intervalo nao colhe de novo", c.ver([(150, va)], 0.5) is None and len(c.vetores) == 1)
ok("rosto de lado (sem vetor) nao vale", c.ver([(150, None)], 2.0) is None and len(c.vetores) == 1)
fim = None
for k in range(10):
    fim = c.ver([(150, parecido(pessoas["Ana"], 0.7))], 2.0 + 1.6 * k) or fim
    if fim:
        break
ok("completa com 6 amostras", fim == "pronto" and len(c.vetores) == 6, f"{fim} {len(c.vetores)}")
ok("estoura o prazo", arena.Coleta("Ana", 0.0).ver([], arena.Coleta.PRAZO_S + 1) == "prazo")

import json as _json
import tempfile
from aibox import galeria as _gal
with tempfile.TemporaryDirectory() as d:
    cam = os.path.join(d, "g.json")
    _gal.gravar("Ana", [list(map(float, parecido(pessoas["Ana"], 0.75))) for _ in range(5)],
                False, cam, motor="sface")
    outro = arena.Coleta("Ana", 0.0)
    outro.vetores = [list(map(float, parecido(pessoas["Bruno"], 0.7))) for _ in range(6)]
    okg, msg = arena.gravar_coleta(outro, cam, "sface")
    ok("outra pessoa no lugar da Ana nao entra", not okg
       and len(_gal.ler(cam)["pessoas"]["Ana"]) == 5, msg)
    certo = arena.Coleta("Ana", 0.0)
    certo.vetores = [list(map(float, parecido(pessoas["Ana"], 0.7))) for _ in range(6)]
    okg, msg = arena.gravar_coleta(certo, cam, "sface")
    ok("a Ana de verdade entra", okg and len(_gal.ler(cam)["pessoas"]["Ana"]) == 11, msg)
    novo = arena.Coleta("Zeca", 0.0)
    novo.vetores = certo.vetores
    ok("nome fora da galeria nao entra pelo botao", not arena.gravar_coleta(novo, cam, "sface")[0])

print("\nRESULTADO", "ok" if not falhas else f"{falhas} FALHA(S)")
sys.exit(1 if falhas else 0)
