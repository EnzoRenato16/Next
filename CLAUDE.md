# Auditix IA — o que é, como roda, e o que já custou tempo

Projeto do grupo 11 (2ECR) para o desafio DATEN × FIAP. Detecta **queda**,
**corrida**, **briga** e **pedido de ajuda** numa sala, e deixa trilha auditável.

Duas versões do MESMO sistema, e isso é proposital:

| onde | arquivo | quem enxerga o corpo | serve para |
|---|---|---|---|
| navegador | `auditix-sala.html` | MediaPipe, no Chrome | demonstração segura, webcam |
| AIBOX | `aibox/` | YOLO11-pose por ONNX Runtime | o que o desafio pede |

**As duas usam o mesmo cérebro.** As 12 características vêm de
`treino/extrair.py` e os 113 pesos de `treino/modelo.json`. Não existe um
segundo modelo. `testes/aibox.mjs` roda o mesmo cenário nos dois lados e cobra
que batam — geometria idêntica bit a bit, e numa queda os dois armam no mesmo
quadro.

## Como entrar na AIBOX (rede da FIAP)

```
câmera Intelbras 192.168.50.108  →  AIBOX 192.168.50.10  →  PC 192.168.50.72
        (RTSP)                          (a análise)          (servidor + painel)
```

No PC (Windows, **cmd**, como administrador):

```cmd
netsh interface ip set address name="Ethernet" static 192.168.50.72 255.255.255.0
ssh grupo11@192.168.50.10
```

> **A rede demora a acordar depois do `netsh`.** O primeiro `ping` ou `ssh`
> falha com *"Destination host unreachable"* e o segundo funciona. Isso custou
> meia hora achando que era cabo. Se falhar, repita o comando.

Na caixa, toda sessão nova precisa destas duas linhas:

```bash
P=/opt/eduvision/venv/bin/python
export PYTHONPATH=$HOME/pylibs
```

`/opt/eduvision/venv` é o ambiente que já vem na caixa, com OpenCV 4.10,
NumPy, Ultralytics e ONNX Runtime. **Não é o `python3` do sistema** — esse não
tem nada. `~/pylibs` é onde mora o `lap`, que o rastreador exige e que não dá
para instalar dentro do venv (a pasta não é do usuário `grupo11`).

## Rodar

```bash
cd ~/auditix && $P aibox/sala.py --mostrar
```

- imagem ao vivo: `http://192.168.50.10:8080` — **com `http://` na frente**,
  senão o Chrome tenta HTTPS e dá `ERR_SSL_PROTOCOL_ERROR`
- painel dos eventos: `http://127.0.0.1:8000/painel` no PC
- cadastro de rostos: `http://127.0.0.1:8000/cadastro` no PC (a tela da caixa
  tem atalho para os dois, montado com o endereço do `.env`)
- `--segundos N` para parar sozinho; sem isso roda até Ctrl+C

No PC, o servidor precisa aceitar conexão de fora:

```cmd
set HOST=0.0.0.0
set CALIBRACAO=1
python servidor.py
```

## Levar código novo para a caixa

**Os comandos longos viraram script.** No PC (cmd como administrador):

```cmd
pc puxar      DHCP, git pull, e volta para o IP fixo
pc enviar     copia aibox\*.py e *.sh, e ja limpa o \r do lado de la
pc servidor   sobe o servidor com HOST=0.0.0.0
pc entrar     ssh na caixa
```

Na caixa:

```bash
bash aibox/ir.sh              # acha o $P, limpa \r, confere o banco, roda
bash aibox/ir.sh --segundos 30
```

`ir.sh` também escreve `$P` e `$PYTHONPATH` no `~/.bashrc` na primeira vez, e
a partir da sessão seguinte eles já vêm prontos.

O passo a passo para ler offline no laboratório está em `PASSO-A-PASSO.md`.

**O porquê do `\r`:** o Git converte para fim de linha do Windows no checkout,
e o bash da caixa lê o `\r` como parte do comando (`$'\r': command not found`,
que não parece nem de longe com a causa). O `.gitattributes` impede isso em
clones novos, mas o clone do laboratório é anterior a ele — por isso o `pc
enviar` limpa por ssh logo depois de copiar, em vez de confiar na memória de
alguém.

## O banco: a caixa analisa, o PC guarda

A AIBOX **não tem banco**. Ela analisa e manda cada alerta para o servidor do
PC (`SERVIDOR` no `.env` da caixa), e é o PC que grava — no Postgres da AWS, ou
em SQLite local quando o RDS não responde. **Os painéis leem do PC**, então
banco parado = painel vazio, mesmo com a caixa funcionando perfeitamente.

Para saber se está tudo ligado, na caixa:

```bash
$P aibox/conferir.py            # só olha, não grava nada
$P aibox/conferir.py --gravar   # grava um evento de teste e confere que chegou
```

Ele responde, em português: se `SERVIDOR` está configurado, se a porta do PC
responde, **qual banco está realmente em uso** (é aqui que se descobre que caiu
para SQLite), se a cadeia de hash fecha, se o painel e o cadastro abrem, e —
com `--gravar` — se a linha chegou mesmo ao banco.

A tela ao vivo da caixa também mostra **"não chegaram"** em vermelho ao lado de
"alertas enviados". Um enviador que erra calado é indistinguível de um que
funciona, e foi assim que a foto do alerta ficou um dia sem subir.

As três causas de "não responde", em ordem de frequência:

1. o servidor no PC subiu **sem** `set HOST=0.0.0.0`
2. o firewall do Windows barrando a porta
3. o PC voltou para DHCP e perdeu o `192.168.50.72`

## As armadilhas que já custaram tempo

1. **O OpenCV da caixa não abre RTSP.** `FFMPEG: YES` na lista, mas o plugin
   não carrega, e `GStreamer: NO`. Por isso existe `aibox/gstcam.py`, que chama
   o `gst-launch-1.0` por fora. Não tente voltar para `cv2.VideoCapture`.
2. **A câmera é Intelbras**, então o caminho é
   `/cam/realmonitor?channel=1&subtype=1`. Com o caminho errado ela responde
   **401**, não 404 — parece senha errada e não é.
3. **Usuário e senha vão SEPARADOS da URL** (`CAM_USER`/`CAM_PW` no `.env`).
   A senha tem `@`, que dentro do endereço parte a URL no lugar errado.
4. **No `sed`, `&` na substituição significa "todo o texto que casou".** A URL
   tem `&subtype=1`, e isso embaralhou o `.env`. Use apagar-e-acrescentar:
   `sed -i '/^CAMERA_RTSP/d'` e depois `echo "CAMERA_RTSP=..." >>`.
5. **`~pylibs` não é `~/pylibs`.** Sem a barra o bash não expande.
6. `$P` e `$PYTHONPATH` se perdem a cada nova sessão de SSH.

## Os números medidos na caixa (Qualcomm QCS6490, ARM, 8 núcleos, 7 GB)

| configuração | quadros/s | latência do modelo |
|---|---|---|
| PyTorch, entrada 640 | 1,5 | 600 ms |
| PyTorch, entrada 320 | 3,1 | 300 ms |
| **ONNX Runtime, entrada 320** | **8,7** | **~110 ms** |

A nossa análise (12 características + rede + regras) custa **0,2 a 0,5 ms**.
Todo o peso é o modelo de pose. Quem quiser acelerar o Auditix não mexe no
Auditix, mexe no detector.

Para medir de novo depois de qualquer mudança:

```bash
$P aibox/medir.py
```

Ele separa o teto da câmera do teto do modelo — e isso importa, porque otimizar
o modelo contra um teto que é da câmera é trabalho jogado fora.

## O que ainda NÃO existe na caixa

- **Reconhecimento facial DENTRO da `aibox/`.** A caixa detecta corpo e
  acompanha, e não sabe o nome de ninguém: quem mede rosto hoje é o navegador
  (`/cadastro` + `POST /api/reconhecer`).

  **MAS O MOTOR JÁ EXISTE NESTE REPOSITÓRIO**, em `daten/` (EduVision):
  YuNet + SFace em ONNX, feitos para CPU ARM, com conferência de paridade entre
  OpenCV DNN e ONNX Runtime e detecção medida em 8,7 ms. Os dois modelos agora
  vão versionados em `daten/models/` — antes eram "baixe localmente", e baixar
  39 MB no laboratório é um passo que pode falhar no dia.

  O que falta é **juntar**, não construir: `aibox/sala.py` chamando o
  `FaceEngine` para batizar as trilhas. O ponto de atenção é o cadastro — os
  descritores de `cadastros` vieram do face-api.js e **não são comparáveis** com
  os do SFace. Duas listas, ou uma coluna de tipo.
- **Mapa de calor** e **botão de pedir ajuda**: só no navegador.
- **30 quadros por segundo.** O alvo hoje é 8,7. Ver `aibox/LEIA.md`.

## Biometria: o que é guardado, e o que não é

A imagem do rosto **não é guardada em lugar nenhum**. O cadastro grava 128
números medidos no navegador; a foto de alerta sobe com a cabeça em **mosaico**
(blocos de 4, feito reduzindo pela metade até caber — não é desfoque, que ainda
deixa reconhecer).

Os 128 números **ainda são dado biométrico**, então eles são **girados** antes
de encostar no disco:

- girar no espaço de 128 dimensões **não muda distância nenhuma**, então o
  reconhecimento sai idêntico — medido em `testes/biometria.mjs`, diferença
  de 1e-14;
- os eixos do giro saem de `CHAVE_BIO`, que mora no `.env` ou em
  `chave-bio.txt` **ao lado do banco, nunca dentro dele** (e no `.gitignore`);
- quem copiar só o banco não consegue cruzar com outro cadastro de rostos;
- trocar a chave invalida todos os cadastros — é a única forma de "trocar" uma
  biometria vazada, porque rosto não se troca.

**O limite, dito na cara:** isto protege contra o BANCO vazar. Quem tiver o
servidor inteiro tem a chave junto. É o mesmo limite de qualquer coisa cifrada
em disco, e o pitch diz isso.

**Hash não serviria**, e o motivo importa: hash muda inteiro quando a entrada
muda um fio. Dois rostos da mesma pessoa nunca dão os mesmos 128 números — dão
números *parecidos*, e reconhecer é medir esse parecido. Hash apaga a
semelhança junto com o resto.

Migração automática: `migrar_cadastros()` gira o que já estava cru e marca a
linha (`protegido = 1`). É UPDATE, nunca DELETE, e rodar duas vezes não gira
duas vezes.

## Regras do projeto que não se quebram

- **Linha do banco nunca é apagada** — quebraria a cadeia de hash. A tabela
  `calibracao` é a única exceção, e é exatamente por NÃO estar na cadeia.
- **O `.env` não vai para o git.** É onde mora a senha da câmera.
- Corrida e briga são **regra**, não modelo treinado, e o código, a tela e o
  pitch dizem isso. Queda é modelo, com 4.509 clipes por trás.
- `svatech-dashboard.html`, `svatech-scanner.html` e `SVATech_Health.md` são de
  outro projeto. Não mexer.

## Testes

```bash
node testes/aibox.mjs      # o Python da caixa calcula igual ao navegador?
node testes/rede-queda.mjs  # o JS calcula igual ao treino?
```

Os 18 arquivos em `testes/` rodam com o servidor no ar (`CALIBRACAO=1`).
