"""O banco esta funcionando? — roda na caixa:  $P aibox/conferir.py

POR QUE ISTO EXISTE. A analise roda na AIBOX, mas o BANCO mora no PC. Entre os
dois tem um cabo, um IP, um firewall do Windows e uma linha de .env. Qualquer um
desses quebra em silencio: a caixa continua analisando, continua desenhando o
esqueleto na tela, e o painel simplesmente nunca enche. E ai nao da para saber
se nao aconteceu nada ou se nada chegou.

Este arquivo responde isso em dez segundos, e sem biblioteca nenhuma alem do que
vem no Python — de proposito, porque ele tem que funcionar justamente quando
alguma coisa nao esta instalada.

  $P aibox/conferir.py            so olha, nao grava nada
  $P aibox/conferir.py --gravar   grava um evento de teste e confere que chegou
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BOM, RUIM, AVISO = "  ok  ", "  NAO ", "  !!  "


def ler_env():
    """O mesmo .env que a sala.py le. Sem dependencia de nada."""
    valores = {}
    caminho = os.path.join(AQUI, ".env")
    if not os.path.exists(caminho):
        return valores
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def pegar(base, rota, espera=6):
    """Devolve (codigo, corpo_decodificado_ou_texto). Nunca levanta."""
    try:
        with urllib.request.urlopen(base + rota, timeout=espera) as r:
            bruto = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(bruto)
            except ValueError:
                return r.status, bruto
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def mandar(base, rota, corpo, espera=6):
    pedido = urllib.request.Request(
        base + rota, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=espera) as r:
            bruto = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(bruto)
            except ValueError:
                return r.status, bruto
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, str(e)


def main():
    gravar = "--gravar" in sys.argv
    env = ler_env()
    base = env.get("SERVIDOR", os.environ.get("SERVIDOR", "")).rstrip("/")
    problemas = []

    print("=" * 58)
    print(" O banco esta funcionando?")
    print("=" * 58)

    # ---- 1. o endereco esta configurado? ---------------------------------
    print("\n-- para onde a caixa manda --")
    if not base:
        # Sem SERVIDOR no .env a sala.py usa 127.0.0.1, que NA CAIXA e a propria
        # caixa — onde nao roda servidor nenhum. Os eventos saem e morrem ali.
        print(RUIM + "SERVIDOR nao esta no .env")
        print("      a sala.py vai usar http://127.0.0.1:8000, que na caixa e a")
        print("      PROPRIA caixa. Os eventos sairiam e morreriam ali.")
        print("      conserto:  echo 'SERVIDOR=http://192.168.50.72:8000' >> .env")
        print("\n" + "=" * 58)
        return 1
    print(BOM + "SERVIDOR = " + base)
    if "127.0.0.1" in base or "localhost" in base:
        print(AVISO + "isso aponta para a PROPRIA caixa. So esta certo se o")
        print("      servidor estiver rodando aqui dentro, e ele roda no PC.")
        problemas.append("SERVIDOR aponta para a propria caixa")

    # ---- 2. a porta responde? --------------------------------------------
    print("\n-- o cabo e a rede --")
    sem_esquema = base.split("//", 1)[-1]
    maquina = sem_esquema.split("/", 1)[0]
    if ":" in maquina:
        ip, porta = maquina.rsplit(":", 1)
        porta = int(porta)
    else:
        ip, porta = maquina, 80
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect((ip, porta))
        print(BOM + ip + ":" + str(porta) + " responde")
    except Exception as e:
        print(RUIM + ip + ":" + str(porta) + " nao responde  (" + str(e) + ")")
        print("      as tres causas, em ordem de frequencia:")
        print("      1. o servidor no PC subiu SEM  set HOST=0.0.0.0")
        print("      2. o firewall do Windows esta barrando a porta")
        print("      3. o PC voltou para DHCP e perdeu o 192.168.50.72")
        print("\n" + "=" * 58)
        return 1
    finally:
        s.close()

    # ---- 3. que banco esta em uso, e a cadeia fecha? ----------------------
    print("\n-- o banco --")
    cod, v = pegar(base, "/api/verificar")
    if cod != 200 or not isinstance(v, dict):
        print(RUIM + "/api/verificar respondeu " + str(cod) + ": " + str(v)[:120])
        print("\n" + "=" * 58)
        return 1

    qual = v.get("banco", "?")
    print(BOM + "servidor no ar, gravando em: " + qual)
    if qual == "sqlite":
        # Nao e erro: o servidor cai para SQLite sozinho quando o Postgres nao
        # responde, e a demonstracao nao morre por causa da nuvem. Mas quem
        # esperava ver os dados no RDS precisa saber que eles nao estao la.
        print(AVISO + "e SQLite LOCAL, nao o Postgres da AWS.")
        print("      o servidor cai para ca sozinho quando o RDS nao responde —")
        print("      de proposito, para a apresentacao nao depender da nuvem.")
        print("      se voce esperava ver os dados no RDS, eles NAO estao la.")
        print("      olhe a janela do servidor no PC: o motivo esta impresso nela.")
        problemas.append("gravando em SQLite local, nao no Postgres")

    total = v.get("total", 0)
    print(BOM + str(total) + " evento(s) na cadeia")
    if v.get("integra"):
        print(BOM + "a cadeia de hash fecha — nada foi adulterado")
    else:
        print(RUIM + "A CADEIA NAO FECHA: " + str(v.get("motivo")))
        print("      quebrou no evento " + str(v.get("quebrou_em")))
        problemas.append("cadeia de hash quebrada")

    # ---- 4. os paineis abrem? --------------------------------------------
    print("\n-- as telas --")
    for rota, nome in (("/painel", "painel de eventos"),
                       ("/cadastro", "cadastro de rostos")):
        cod, _ = pegar(base, rota)
        if cod == 200:
            print(BOM + nome + "   " + base + rota)
        else:
            print(RUIM + nome + " respondeu " + str(cod))
            problemas.append(nome + " nao abre")

    # ---- 5. gravar de verdade --------------------------------------------
    print("\n-- gravar de verdade --")
    if not gravar:
        print("      pulado. Para testar a gravacao inteira:")
        print("          $P aibox/conferir.py --gravar")
        print("      (grava UM evento do tipo 'teste-conexao'. Ele fica na cadeia")
        print("       para sempre, porque linha de cadeia nao se apaga — mas nao")
        print("       aparece no painel, que filtra por queda.)")
    else:
        cod, ev = mandar(base, "/api/evento", dict(
            aluno_id="conferir", tipo_evento="teste-conexao",
            localizacao=env.get("LOCAL_CAMERA", "sala-12")))
        if cod != 200 or not isinstance(ev, dict):
            print(RUIM + "/api/evento respondeu " + str(cod) + ": " + str(ev)[:120])
            problemas.append("o servidor nao aceitou um evento")
        else:
            print(BOM + "evento gravado, id " + str(ev.get("id")))
            cod2, v2 = pegar(base, "/api/verificar")
            depois = v2.get("total", 0) if isinstance(v2, dict) else 0
            if depois > total:
                # A pergunta nao e "o servidor respondeu ok", e "a linha esta la".
                print(BOM + "e a contagem subiu de " + str(total) + " para " +
                      str(depois) + " — chegou ao banco mesmo")
            else:
                print(RUIM + "o servidor disse ok mas a contagem nao subiu")
                problemas.append("o evento nao apareceu no banco")

        # A calibracao e outro caminho, e ela e que enche a planilha de custo.
        cod3, _ = mandar(base, "/api/calibracao", dict(
            camera=env.get("LOCAL_CAMERA", "sala-12"), amostras=[]))
        if cod3 == 200:
            print(BOM + "registro de calibracao ligado")
        elif cod3 == 403:
            print(AVISO + "calibracao DESLIGADA no servidor (CALIBRACAO=0)")
            print("      sem isso nao ha planilha de custo nem margem de falso")
            print("      positivo. No PC:  set CALIBRACAO=1  antes de subir.")
            problemas.append("calibracao desligada no servidor")
        else:
            print(RUIM + "/api/calibracao respondeu " + str(cod3))

    # ---- veredito ---------------------------------------------------------
    print("\n" + "=" * 58)
    if problemas:
        print(" FUNCIONA, com " + str(len(problemas)) + " ressalva(s):")
        for p in problemas:
            print("   - " + p)
    else:
        print(" ESTA TUDO CERTO. O que a caixa vir vai parar no painel.")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
