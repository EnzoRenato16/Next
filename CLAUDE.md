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
pc internet   so volta para o DHCP e FICA la (para navegar)
pc enviar     copia aibox\*.py, *.sh e daten\app, e ja limpa o \r do lado de la
pc modelos    copia os modelos de rosto (39 MB, uma vez so)
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

**A internet não volta sozinha quando você muda o cabo de lugar.** A placa
continua cravada no `192.168.50.72`, que na rede da FIAP não existe, e ela nem
pede endereço porque acha que já tem um. O sintoma é "o cabo está na parede e
não navega", e nada nele aponta para o IP. `pc internet` resolve. O cabo no
switch da caixa também nunca dá internet: a AIBOX não é roteador.

**No PowerShell é `.\pc`, não `pc`.** O PowerShell não procura programa na
pasta de agora, e responde "não é reconhecido como nome de cmdlet" — que soa
como arquivo faltando e não é.

**`pc entrar` dando *Connection timed out*: entre direto.**

```powershell
ssh grupo11@192.168.50.10
```

É exatamente o que o `pc entrar` faz por dentro, então o timeout é da rede
acordando depois do `netsh`, nunca do script. Testado no laboratório: o `pc
entrar` deu timeout e o `ssh` na linha seguinte entrou. **Repita até entrar**
antes de procurar defeito em cabo, em IP ou no script. Vale o mesmo para o `pc
enviar`, que começa com um ssh.

> A senha erra fácil (três erros seguidos e o servidor fecha a conexão com
> *Connection closed by 192.168.50.10 port 22*, que parece rede e é senha).
> Depois disso é só chamar o `ssh` de novo.

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

## Demonstrar para a banca (funcionalidades mínimas A e B)

- **B, câmera:** `bash aibox/camera_teste.sh` (ou `... cadastro` para a
  `.109`) abre o RTSP pelo mesmo cano da `sala.py`, lê 5 s e diz quantos
  quadros chegaram. UMA tentativa, nunca em laço (armadilha 5).
- **A, partida automática:** `bash aibox/servico.sh instalar`. O `grupo11` não
  é root, então não há `/etc/systemd`: é o `@reboot` do cron do usuário. O
  `rodar` espera o PC responder, roda a `sala.py` direto (o `ir.sh` pergunta
  "rodar assim mesmo?" e serviço não responde), religa em 60 s se cair, 10 min
  se a câmera deu 403, e para com INT para o servidor registrar "parada" sem
  sirene. `SERVICO_ARGS=--rosto` no `.env` passa argumentos. **Com o serviço
  rodando, não rode o `ir.sh` junto:** a porta 8080 já está ocupada.

## O pitch (`Auditix-pitch.html`)

Deck em HTML com three.js (`vendor/three/three.min.js`, r160, versionado: o
laboratório não tem internet). 12 slides num palco 1920x1080 escalado; setas
trocam, `F` tela cheia, `N` roteiro de fala, `R` repete o evento da sala (slide 4: queda, corrida ou briga) ou
desfaz a adulteração (slide da cadeia). Abrir com `pc pitch` (serve em 127.0.0.1:8090):
pelo duplo clique as fontes de `vendor/fontes` não carregam.

**Modo 5 minutos, ligado por padrão** (o pitch tem 5 min). O deck completo e o
modo 5 minutos têm os MESMOS 12 slides, na mesma ordem:
`s1 s3 s4 s10 s10b s9 s11 s8 s8b s12 s12b s13` (dados, Auditix IA, sala 360,
vídeo, A e B, cadeia, painel, privacidade, LGPD, AIBOX, custo, equipe). A cadeia
vem antes do painel porque o primeiro cartão do painel é ela.
`M` alterna com o deck completo (lembrado no navegador); número + Enter abre
qualquer slide para as perguntas, e → volta ao roteiro dali; cronômetro na
barra, âmbar aos 4:20 e rubi aos 5:00, `T` zera. Para mudar o roteiro, edite
`CURTO_IDS` no script.

- Os dois dados de abertura têm fonte na tela: 15.759 episódios de violência
  em escolas em 2024 (Anuário Brasileiro de Segurança Pública 2025, SINAN) e
  mais de 55 mil internações de crianças por queda em 2025 (Criança Segura,
  DataSUS). Não troque por número sem fonte.
- O slide da cadeia calcula SHA-256 de verdade, com a fórmula do servidor.
- `ppt/pitch-imagens.js`: capturas do painel embutidas (sem rosto, versionado).
- `ppt/midia/`: vídeos e fotos do laboratório, **fora do Git** (rosto de gente).
  Arquivo que falta vira espaço tracejado com o nome esperado; `LEIA.txt` lista.

## A entrega dos alertas (`aibox/entrega.py`)

O laço da análise **nunca espera a rede**: entrega o alerta numa fila e segue
(0,05 ms medido com o servidor levando 1,5 s). Uma thread envia; se o PC não
responde, **guarda e reenvia** com espera crescente até 30 s. Recusa (4xx) não
se repete. Lote de calibração que falha é descartado — não pode ficar na frente
de uma queda.

**Reenviar sem duplicar.** Cada alerta nasce com uma `chave`; o servidor que já
viu a chave devolve o evento original (tabela `recebidos`). A conferência é
DEPOIS do cadeado da cadeia: cinco cópias juntas viram uma linha (testado).

**O horário.** O servidor carimba a chegada. A caixa manda `ocorreu_ha_ms`,
medido no relógio DELA na hora de mandar — um intervalo, nunca uma hora, porque
subtrair o relógio de uma máquina do da outra faz a diferença entre relógios
parecer atraso. Fica em `recebidos`, FORA da fórmula da cadeia.

**O e-mail sai depois da resposta** (`BackgroundTasks`). Rodava dentro do
`/api/evento` com 5 s de prazo e a caixa desiste em 4: sem internet, o evento
era gravado e contado como "não chegou". A espera do e-mail é por **tipo e
pessoa** — só por tipo, duas quedas de alunos diferentes davam um e-mail.

## Prova sem rosto (`esqueletos`)

A AIBOX não manda foto. Cada trilha carrega 3 s de pontos (`trilhas.POSES_MS`)
e o alerta leva os últimos 2,5 s (até 24 quadros × 17 pontos, ~8 KB), com o x
**multiplicado pela proporção da imagem**. O painel desenha em "corpo", com
rastro e o último quadro em vermelho. Fora da cadeia, como a foto, e sem
registro de acesso: não identifica ninguém.

## "Estou ciente" e a sirene (painel)

Queda nova toma a tela inteira em ~1 s (a vigia pergunta a cada 2 s; a carga
pesada continua a cada 15 s), com sirene de oscilador puro (adaptada do EPI
Guard, com aval do autor) até alguém apertar **Estou ciente**. O clique vira
uma linha da CADEIA — `tipo_evento='ciente'`, `aluno_id='evento-<id>'` — e a
tabela mostra "ciente em X s". Uma vez por alerta, mesmo com cinco cliques
juntos. Só alerta grave aceita. O alarme usa `completo=1`: não passa pelo filtro
de vitrine `PAINEL_TIPOS`.

**Armadilhas de tela pegas em foto, não em teste:** `hidden` perde para um
`display` escrito no próprio elemento; e num `<svg>` a propriedade `.hidden`
não existe (use `toggleAttribute`). Teste de tela confere `getComputedStyle`,
não o atributo.

## O sistema cego avisa (`aibox/batimento.py`, `/api/batimento`, `/api/saude`)

Painel quieto porque nada aconteceu e painel quieto porque a caixa morreu eram a
mesma tela. Agora a caixa bate a cada 5 s dizendo como está a imagem:

| a caixa diz | quando | vira na cadeia |
|---|---|---|
| `ok` | chega quadro, com detalhe | nada (batida não é fato) |
| `sem_imagem` | 10 s sem quadro | `camera_sem_imagem` |
| `tampada` | 10 s de imagem lisa (desvio do brilho < `TAMPADA_LIMIAR`=15) | `camera_tampada` |
| `parada` | Ctrl+C ou `--segundos` acabou | `caixa_parada` (sem sirene) |
| — (silêncio) | `SEM_SINAL_S`=30 s sem batida, **notado pelo servidor** | `sem_sinal` |

Uma linha **por episódio**, e `sinal_voltou` fecha. `sem_sinal`,
`camera_sem_imagem` e `camera_tampada` formam `CEGUEIRA`: tocam a sirene, pedem
ciente e mandam e-mail (`ALARMES = GRAVES | CEGUEIRA`), mas ficam **fora de
`GRAVES`** para não contar como ocorrência na série. O estado de agora mora só na
memória do servidor — `/api/saude` responde mesmo com o banco fora — e por isso
uma caixa só é vigiada depois de bater uma vez desde que o servidor subiu.

**A câmera escreve na própria imagem.** A Intelbras grava o relógio no alto e
"VIPC Intelbras" embaixo, em branco, dentro do vídeo. Com a lente tapada o resto
fica preto e só esse texto já dá desvio de ~20: no laboratório a lente coberta
nunca desceu de 22, com limiar 10, e o alarme não tinha como tocar. A conta
agora ignora as faixas de cima e de baixo (`FAIXA_TOPO`, `FAIXA_BASE`). Mão na
frente com luz vazando continua **não** contando (40 a 42 contra 59 a 61 da
sala): borrado não é liso.

De carona, na `sala.py`: RTSP que **trava sem cair** deixava o laço esperando
quadro para sempre. Agora, 15 s sem quadro (`TRAVADA_S`) = reabre a câmera.

A ideia de "câmera fora do ar" veio do Lot Vulture (licença PolyForm Shield):
**só a ideia**, o código foi escrito do zero.

## Três chaves que vêm DESLIGADAS de propósito

| chave | onde | o que faz | por que desligada |
|---|---|---|---|
| `QUEM_ESCREVE=127.0.0.1,192.168.50.10` | `.env` do PC | todo POST de fora da lista é recusado; o resto da rede só lê | IP errado na lista = todo alerta recusado (a recusa diz o IP visto) |
| `NUCLEOS=grandes` | `.env` da caixa | modelo nos núcleos A78, `gst-launch` nos A55 | só depois de `medir.py --nucleos` dizer GANHA |
| `--fluido` | `ir.sh` | vídeo ao vivo no ritmo da câmera (teto 25/s) | JPEG a 25/s custa CPU; compare `análise/s` com e sem |

`taskset` no terminal seria errado para os núcleos: prende também os FILHOS, e
o `gst-launch` é filho — a decodificação disputaria os núcleos grandes com o
modelo. Por isso `aibox/nucleos.py` faz por dentro, com `preexec_fn`.

O vídeo fluido NÃO interpola o esqueleto (o EPI Guard interpola): desenhar
pontos que o modelo não mediu não cabe num sistema auditável. O esqueleto de um
quadro novo é o da última análise, e a tela mostra `análise/s` e `vídeo/s`.

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
5. **A câmera bloqueia o IP depois de tentativas seguidas (403 Forbidden).**
   Uma rodada de testes de `gst-launch` mais a sala reconectando a cada 15 s
   fez a `.108` responder **403** para a caixa por uns 30 min, com a senha
   CERTA: a página web da câmera abria normal pelo PC (outro IP). 403 é
   bloqueio, 401 é senha ou caminho. Remédio: Ctrl+C e **não tentar nada** até
   passar. Teste de câmera, um de cada vez.
6. **`~pylibs` não é `~/pylibs`.** Sem a barra o bash não expande.
8. **`Element not found` no `pc rede` = a placa não se chama "Ethernet".** No
   PC do laboratório de 20/10 tinha outro nome, o IP fixo não entrou e o ping
   falhou como se fosse cabo. `Get-NetAdapter` mostra o nome; `set PLACA=...`
   (cmd) ou `$env:PLACA="..."` (PowerShell) antes do `pc`.
7. `$P` e `$PYTHONPATH` se perdem a cada nova sessão de SSH.

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

## O hardware que a caixa tem e o Auditix ainda não usa

Achado no laboratório, com `gst-inspect-1.0` e `ls /root/lib`:

- **`qtivdec`**: decodificador H.264 por hardware. A câmera manda 30/s, a
  análise usa ~6, e os outros eram decodificados na CPU para nada (744% de
  800%). `GST_DECODIFICADOR=qtivdec` no `.env` liga; desligado até medir. **Testado
  no laboratório: sem imagem** (`sem_imagem` e reabrindo). Provável causa: o
  `qtivdec` entrega em memória do hardware que o `videoconvert` não lê; o
  candidato é `qtivdec ! qtivtransform`. Não confirmado (a câmera bloqueou no
  meio dos testes).
- **NPU Hexagon V68** (`/dev/adsprpc-smd`, `libSnpeHtpV68Skel.so`) e os plugins
  `qtimltflite` + `qtimlvpose` do Qualcomm IM SDK: pose rodando na NPU, fora
  da CPU. O ONNX Runtime da caixa (1.16.3) NÃO tem o provedor da NPU, então o
  caminho é TFLite quantizado pelo GStreamer, não o ONNX de hoje.
- **GPU Adreno** (`/dev/kgsl-3d0`).

## O que ainda NÃO existe na caixa

- **Mapa de calor** e **botão de pedir ajuda**: só no navegador.
- **30 quadros por segundo.** O alvo hoje é 8,7. Ver `aibox/LEIA.md`.

## Rosto na caixa (`--rosto`)

O motor é o `daten/` (EduVision), que já existia: **YuNet** acha o rosto e cinco
pontos, **SFace** alinha e devolve 128 números. ONNX, CPU ARM, sem GPU. Os dois
modelos vão versionados em `daten/models/` (conferidos por sha256 contra o
opencv_zoo) — baixar 39 MB no laboratório é um passo que pode falhar no dia.

> **Isto já falhou em silêncio uma vez.** Uma regra `daten/models/*.onnx` no
> `.gitignore` da raiz barrou os modelos; o `git add -A` pulou sem avisar e o
> commit dizia que eles iam versionados. Confira sempre com
> `git ls-files daten/models` — têm de aparecer os dois `.onnx`.

Levar para a caixa (no PC):

```cmd
pc enviar     o código, incluindo daten\app
pc modelos    os dois .onnx, 39 MB, uma vez só
```

E na caixa:

```bash
$P aibox/cadastrar.py --nome "Enzo Renato"   # colhe 6 amostras pela câmera
                                             # (CAMERA_CADASTRO, ou a da sala)
bash aibox/ir.sh --rosto                     # e a caixa passa a chamar pelo nome
```

**Duas câmeras no laboratório:** a `.108` no alto vigia a sala, a `.109` na
altura do rosto serve para cadastrar (`CAMERA_CADASTRO` no `.env` da caixa).
Pela de cima o rosto sai pequeno e todo mundo da sala entra no quadro, e o
cadastro para em "mais de um rosto". As duas usam o mesmo `CAM_USER`/`CAM_PW`.

**O balcão de cadastro (`aibox/balcao.py`): a tela `/cadastro` do PC opera a
câmera da caixa.** Navegador não lê RTSP, e o motor do navegador mede o rosto
num formato que a caixa não lê. Então a tela PEDE e a caixa FAZ: com
`CAMERA_CADASTRO` no `.env`, a `sala.py` sobe o balcão na porta 8081, e a tela
acha o endereço sozinha (a caixa manda a porta no batimento; o servidor anota o
IP de quem bateu e devolve em `/api/saude`). "Ligar a câmera" abre a `.109` e
mostra em MJPEG; "Cadastrar" colhe 6 amostras com o SFace e grava como `sface`.
A câmera só abre quando a tela pede, e fecha 20 s depois que ninguém olha.
**Sem prova de vida nesse modo:** a da webcam usa os 68 pontos do face-api, e o
YuNet dá 5. A tela diz isso. Rosto menor que `BALCAO_ROSTO_MIN` (15% da altura)
não é colhido.

**Cadastrar por fotos (`aibox/cadastrar_fotos.py`, roda no PC).** Uma subpasta
por pessoa em `fotos-cadastro/` (no `.gitignore`: rosto do grupo, repositório
público), o nome da pasta vira o nome. Mesmo motor da caixa (YuNet + SFace),
grava como `sface`. `--conferir` só olha. Ele recusa foto com dois rostos, sem
rosto, rosto menor que 80 px e foto que não abre (HEIC do iPhone: exportar JPG),
e **tira a foto cujo rosto destoa das outras da pasta** (foto de outra pessoa no
lugar errado). Gira a foto deitada escolhendo o giro de **maior nota** do YuNet:
o primeiro giro que acha rosto não serve, porque ele acha rosto até de cabeça
para baixo, com os olhos no lugar errado (0,74 contra 0,91 de pé, no teste).
Precisa de `pip install opencv-python numpy` no Python do PC.

**Juntar em vez de substituir (`acrescentar`).** Recadastrar o mesmo nome
substitui (quem mudou o cabelo refaz). Com `acrescentar: true` no
`/api/cadastro`, as amostras novas se somam às que a pessoa já tem no mesmo
motor, até `CADASTRO_TOTAL_MAX` = 24 (cada envio continua até 12). É o que deixa
cadastrar por fotos em casa e completar pela câmera da sala sem a segunda vez
apagar a primeira. Vale em `cadastrar_fotos.py --acrescentar`, `cadastrar.py
--acrescentar` e na caixinha "Juntar" da tela `/cadastro` no modo caixa, que vem
marcada. Grava linha nova e desativa a antiga, nunca edita.

> **Defeito pego no teste antes de chegar ao laboratório:** ligar a câmera
> sobrescrevia a fase "colhendo" que o pedido de cadastro tinha acabado de
> marcar. O primeiro pedido se perdia, e o segundo, de outra pessoa, era aceito
> no lugar. `testes/balcao_lado.py` cobra isso.

**Desligado por padrão, de propósito:** custa CPU numa caixa que já está
apertada de quadros por segundo, e a análise de queda não pode piorar porque um
extra foi ligado sem ninguém decidir.

Duas decisões que sustentam isso:

1. **Roda em outra thread.** O laço principal entrega um quadro e segue; quando
   a resposta chega, o nome aparece. Rosto pago dentro do laço sairia direto dos
   8,7 quadros por segundo.
2. **Não olha todo quadro.** A cada 2 s para quem não tem nome, 10 s para
   reconferir quem já tem. Ninguém troca de cara entre um quadro e outro.

**DOIS MOTORES QUE NÃO SE FALAM.** `faceapi` (navegador, distância euclidiana,
menor = mais parecido) e `sface` (caixa, cosseno, **maior** = mais parecido).
Os dois devolvem 128 números, e é por isso que misturar é perigoso: nada
estoura, a comparação roda, e o resultado é ruído. Cada cadastro carrega o
`tipo`, e a comparação só acontece dentro do mesmo tipo. A mesma pessoa pode —
e deve — estar cadastrada nos dois.

**Reconhecido vira linha da cadeia, como no navegador.** O quadro "Pessoas" do
painel é feito das linhas `reconhecido`. A caixa só colava o nome na etiqueta e
nunca mandava a linha: no laboratório o nome aparecia na tela ao vivo e o painel
dizia "ninguém foi reconhecido ainda". Agora `rosto.novos()` entrega, e a
`sala.py` manda pela fila dos alertas, com o nome. Uma linha por pessoa a cada
`ROSTO_REGISTRO_S` (300 s), por mais que o rastreador troque o número dela.

A caixa **nunca tem o cadastro na mão**: ela manda os 128 números e recebe um
nome. Quem levar a caixa embora não leva rosto de ninguém.

## A cadeia conferida no navegador (`/cadeia`)

`/api/verificar` responde se a cadeia fecha, mas isso é o servidor dando
atestado de si mesmo. A página `/cadeia` **baixa os eventos e recalcula os
hashes com o SHA-256 do próprio navegador**, e tem um botão que adultera uma
linha para mostrar a quebra se propagando. **Nada é gravado** — a alteração
acontece só na cópia do navegador.

**A armadilha que isso revelou:** `/api/eventos` filtra por `PAINEL_TIPOS`, e a
cadeia encadeia **toda** linha gravada. Conferir a partir da lista filtrada é
somar elos com buraco no meio e concluir que houve adulteração onde não houve —
um único evento `teste-conexao` do `conferir.py --gravar` já fazia isso. Por
isso existe `/api/eventos?completo=1`, que devolve todos os tipos e o
`hash_anterior` de entrada.

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
duas vezes. `testes/banco-antigo.mjs` cria o banco com as versões antigas do
servidor (as que o laboratório pode ter rodado) e cobra que o aluno cadastrado
antes continua sendo reconhecido.

> **Copiou o `auditix.db` para outro PC? Copie o `chave-bio.txt` junto.** Sem
> ele o servidor cria uma chave nova, e todo cadastro girado com a antiga vira
> ruído — nada quebra, ninguém é reconhecido. O servidor avisa com `[bio]
> ATENCAO` na partida quando isso acontece.

## A final do NEXT: quem é cadastrado e quem não é

Passamos em terceiro. O desafio da final: numa sala com umas 20 pessoas, dizer
quem se cadastrou na facial e quem não, mantendo queda, corrida e briga.

**O que o professor respondeu (out/2026):** não vai ter internet, só a do
evento, e bem instável. Não há tempo de cadastrar no dia: o grupo chega
cadastrado. Falta perguntar se é o mesmo laboratório e as mesmas câmeras, se dá
para chegar antes, e a que distância as pessoas ficam.

**Como vai ser (guia oficial da arena e grupo da turma, lidos em 19/10/2026):**

- **Sábado 24/10/2026, ARCA (Vila Leopoldina).** Estande A24, 12h às 15h
  (pitch e demonstração). Concentração 16h a 16h30. **Arena 17h às 17h45.**
  Premiação a partir das 18h.
- **Arena: até 5 min no total, setup incluído** (guia sugere 2 min de acesso e
  3 de prova, sem prorrogação). Notebook só como terminal por SSH com o usuário
  do grupo; **o processamento tem de rodar na AI BOX**. AI BOX e câmeras fixas
  da organização: não mexer, sem sudo, sem mudar configuração da estação.
- **Teste:** 4 cadastrados e 2 desconhecidos pelo guia; o professor falou em 3
  e 2 no grupo da turma (número final a confirmar). Os desconhecidos são um de
  outra equipe e um da plateia. Ordem e posição mudam. **Só os autorizados
  previstos podem estar cadastrados**, nada de ajuste manual nem treino na hora.
- **Ao final, mostrar:** autorizados identificados, alertas de desconhecidos,
  estado das câmeras e latência/estabilidade. Erro não se esconde.
- **Câmeras novas de 4 MP** (compradas em 19/10; marca, caminho RTSP e
  resolução a confirmar). Duas previstas, número final anunciado no dia.
- **Prazo de teste: quarta 21/10 à noite**, quando o professor recolhe totens
  e AI BOX para levar ao evento. Câmeras ficam no teatro da FIAP.
- **Feedback da banca para nós (3º, 32/40):** aderência e pitch subiram para
  Excelente; **viabilidade caiu para Adequado**. Pedem custos, implantação,
  manutenção e escala, métricas técnicas e uma demonstração curta e confiável.

**O que vale nota (áudio do professor, 19/10):** a definição final é **só na
arena**, e a arena é **só identificação** (cadastrado ou não; sem queda, briga
nem corrida). O estande das 12h às 15h é divulgação do projeto completo, mas é
obrigatório: faltar tira ponto.

### Modo arena (`aibox/arena.py`, `bash aibox/arena.sh`)

Feito para a regra da arena: **tudo na caixa**, sem servidor no notebook, sem
IP fixo, um comando só. O notebook abre `http://IP_DA_CAIXA:8080`.
O passo a passo do laboratório (entrar, `.env`, galeria, calibrar, ensaio
cronometrado) está em `ARENA-PASSO-A-PASSO.md`.

- **Só rosto, sem YOLO:** a CPU inteira para o rosto em resolução cheia
  (`ARENA_LARG`/`ARENA_ALT`, padrão 1920x1080; `ARENA_FPS`=6 joga fora quadro
  antes de converter, pelo `videorate` do `gstcam`). Câmera em `CAMERA_ARENA`
  (e `CAMERA_ARENA2`) no `.env`, ou `--camera`. Aceita arquivo de vídeo para
  ensaio.
- **Galeria local** (`aibox/galeria.py`, `arena/galeria.json`, no
  `.gitignore`): só os autorizados da prova, gerada por
  `cadastrar_fotos.py --galeria arena/galeria.json` no PC e copiada com
  `pc galeria`, ou na caixa com `cadastrar.py --galeria arena/galeria.json
  --acrescentar`. **A caixa tem o cadastro na mão aqui**, ao contrário do
  sistema da escola: apagar depois do evento.
- **O juiz decide por trilha, não por quadro.** Leitura só de rosto bom (nota
  do YuNet ≥ 0,80, largura ≥ 32 px, de pé, virado até `ARENA_FRENTE`).
  `ARENA_FRENTE` era 0,35 fixo e barrava quem estava perto da HAIZ olhando
  de lado ("analisando 0/3 (de lado)", 20/10); agora **0,70**, medido na
  HAIZ (`calib-samuel-lado.log`, Samuel girando a cabeça, sala cheia, com
  0,85 só no teste): de 0,55 a 0,70 o Samuel deu no mínimo 0,41 (17
  leituras) e estranho no máximo 0,19; de 0,70 a 0,85 estranho no máximo
  0,19, mas o dono cai para 0,15 a 0,27 em um quarto das leituras, e isso
  só daria alerta errado contra o autorizado. De frente: Samuel mediana
  0,73. Estranhos na rodada: 219 leituras, máximo 0,25. Antes, 0,55: Medido no LFW
  com o ArcFace, galeria de frente e leitura virada 0,35 a 0,55: dono p5
  0,37 a 0,41, estranho no máximo 0,24 (virado, o estranho cai junto com o
  dono). Amostra pequena (o LFW é quase todo de frente): conferir no log,
  que agora diz quanto o rosto descartado estava virado. AUTORIZADO com 3
  leituras, média ≥ `ARENA_LIMIAR` (0,36), folga de 0,05 sobre o segundo nome e
  maioria dos votos. DESCONHECIDO com 5 leituras e média < 0,26. No meio,
  "analisando", até 14 leituras: aí quem não foi autorizado com folga vira
  desconhecido (de propósito: na dúvida, alerta). Desconhecido que volta
  (trilha nova) é comparado com os já vistos e não vira segundo alerta.
  Desconhecido que depois é reconhecido sai da conta. **Autorizado não cai
  para desconhecido** por virar o rosto.
- **Mas a trilha pode trocar de dono.** O rastreador cola o rosto no mais
  próximo do quadro anterior, e duas pessoas que se cruzam trocam de trilha.
  Se as 8 últimas leituras BOAS da trilha autorizada nunca deram o nome dela e
  a média ficou abaixo de 0,26, a trilha recomeça ("o rosto deixou de ser X"),
  e o estranho que herdou a trilha leva o alerta dele. Quem já foi identificado
  continua no placar (`Juiz.identificados`).
- **Os limiares do `.env` valem** (`ARENA_LIMIAR` e cia.): `configurar()` relê
  depois do `carregar_env`. Antes da revisão eram lidos no import e o `.env`
  era ignorado calado, o que jogaria fora a calibração do laboratório.
- **Câmeras de 4 MP:** `CAM_CODEC=h265` se a câmera mandar H.265 (o cano de
  H.264 não negocia e dá "sem imagem"). A arena pede 1920x1080 com faixa
  preta em vez de esticar (rosto esticado não bate com as fotos). O
  `arena.sh` avisa se `CAMERA_ARENA` estiver no fluxo secundário
  (`subtype=1`): aumentar 640x360 não cria pixel de rosto.
- Câmera sem resposta: reabre em 30 s, depois 60, 120, até 5 min. Insistir
  de 30 em 30 mantinha o bloqueio 403 de pé (armadilha 5).
- **A galeria guarda os 128 números CRUS**, sem o giro da `CHAVE_BIO` que o
  servidor faz. A chave teria de morar na mesma caixa, então o giro não
  protegeria nada ali. Por isso a regra é outra: só os autorizados da prova, e
  `arena/` apagada da caixa e do PC depois do evento.
- **Ctrl+C mostra o resultado** (autorizados X de N, alertas, câmeras, tempo
  por quadro) e grava `arena/resultados/*.json`, sem imagem.
- `--calibrar` imprime a nota de cada leitura: é como escolher o limiar no
  laboratório, com colegas fazendo o papel de desconhecido.
  Mostra também o tamanho do rosto em px e, uma vez por segundo, o rosto
  DESCARTADO e o motivo (nota baixa, rosto pequeno, torto, de lado): é como
  achar, sem ninguém da galeria, a distância em que a câmera deixa de ler.
- `testes/arena_juiz.py` cobra a decisão com vetores sintéticos (41 casos,
  incluindo o "parecido perigoso", a troca de trilha, o `.env` e dois
  desconhecidos parecidos na tela ao mesmo tempo; passa com 41 sementes, e com
  `ARENA_TOPK=3`). Ensaio com vídeo montado de duas fotos:
  1 de 1 autorizado, 1 alerta, 74 ms por quadro neste PC (a caixa é mais lenta:
  medir).
- **Porta 8080 ocupada = serviço da sala rodando:** `bash aibox/servico.sh
  parar` antes da arena.
- **Conferir a galeria sem a caixa:** `python aibox\galeria.py conferir` faz
  cada foto virar uma leitura contra a galeria sem ela (como o juiz) e diz se
  acertou o dono e com que folga; `cadastrar_fotos.py --conferir` com várias
  pastas aponta o ARQUIVO da foto que confunde. O "pior par" entre pessoas
  assusta mais do que pesa: Daniel x Lucas deu 0,43 no pior par e +0,41 de
  folga no teste que importa.
- **O limiar 0,36 é BAIXO para a nossa galeria (medido em 20/10).** Enzo, fora
  da galeria, num vídeo de celular de perto: 0,28 a 0,34 contra o Lucas quase o
  tempo todo, picos de 0,38 a 0,40. Com 0,36 ele virou desconhecido e depois
  "subiu" para Lucas (janela de 8 leituras com média 0,37). Com
  `ARENA_LIMIAR=0.45` e `ARENA_LIMIAR_BAIXO=0.38`: 0 de 4 e 1 alerta logo no
  começo. Falta o outro lado: o dono tem de passar de 0,45 na câmera da caixa.
  Se não passar com folga, `ARENA_TOPK=3` (nota = média das 3 fotos mais
  parecidas, e não só a melhor) derruba mais o estranho que o dono.
- **SFace contra ArcFace pequeno (`aibox/comparar_modelos.py`).** O
  `w600k_mbf.onnx` (13 MB, buffalo_s da InsightFace, licença NÃO comercial,
  fora do Git) roda pelo `cv2.dnn` do OpenCV 4.10, igual ao ONNX Runtime
  (cosseno 1,0), ~11 ms por rosto no PC. Medido no LFW (3.000 pares de cada,
  mesmo YuNet e mesmo portão da arena): com rosto de 96 px os dois quase
  empatam (99,3% contra 98,7% dos donos aceitos com 0,1% de estranhos
  aprovados); com rosto de 38 px o ArcFace erra metade (99,0% contra 97,8%).
  Estranho no SFace chega a 0,40 (bate com o Enzo); no ArcFace, a 0,34, com
  mediana 0,00. Ganho real, mas moderado: só trocar se os vídeos do grupo
  mostrarem folga bem maior, e só com teste na caixa. No vídeo do Enzo contra
  a galeria do grupo: pico 0,40 no SFace, 0,24 no ArcFace.
- **ArcFace na arena (`aibox/arcface.py`), opcional.** A GALERIA diz o motor
  (`"motor": "arcface"`, 512 números): `cadastrar_fotos.py --motor arcface
  --galeria ...` cria, e a arena, o `cadastrar.py` (passada) e o `conferir`
  seguem o motor dela. `galeria.gravar` recusa misturar motores. Limiar por
  motor: `ARENA_LIMIAR` é só do SFace, `ARENA_LIMIAR_ARCFACE` (padrão 0,34 /
  0,26) só do ArcFace, para um limiar calibrado num não valer no outro.
- **A passada pela câmera confere quem está na frente.** Com `--acrescentar`,
  amostra com cosseno < 0,25 contra a média do que a pessoa já tem fica de
  fora. Achado no teste: sem isso, outra pessoa na frente da câmera entrava na
  galeria com o nome errado e só o `conferir` via depois.
- **Câmera nova da arena: HAIZ, `192.168.50.109:554`** (20/10). Página em
  `/doc/page/main.html`, com cara de Hikvision. Usuário e senha diferentes das
  Intelbras (passados pela organização; ficam só no `.env` da caixa, nunca no
  Git). O `gstcam` agora aceita usuário e senha DENTRO do endereço
  (`rtsp://usuario:senha@ip/...`) e aí não usa o `CAM_USER`/`CAM_PW`. O
  caminho RTSP se descobre no PC com `python aibox\achar_rtsp.py IP`, que
  tenta os caminhos comuns um por vez, com pausa, e diz resolução e codec.
  **Achado:** é padrão **Xiongmai**, `/user=USUARIO&password=SENHA&channel=1&stream=0.sdp`
  (Hikvision e Dahua respondem `451 Parameter Not Understood`), **2880x1620,
  H.264**. Com `password=` no caminho o `gstcam` também não usa o
  `CAM_USER`/`CAM_PW`.
- **Primeira calibração na HAIZ (20/10, ~2 min, `calib-0454.log`):** 4
  estranhos (3 passando + 1 sentado), 622 leituras boas contra a galeria
  ArcFace. Nota do estranho: mediana 0,14, p99 0,24, **máximo 0,26**; pior
  janela de 8 leituras 0,23. Com o limiar 0,34: **0 aprovados, 4 alertas para
  4 pessoas**. Na caixa: **283 a 402 ms por quadro** (mediana 342), 2,6 a 3,6
  análises/s, pior com mais rostos na tela. O lado do DONO na HAIZ ainda não
  foi medido. Rodadas 05:02 e 05:05: mais 154 leituras, máximo 0,23, 0
  aprovados; mas nas 05:02 **3 pessoas viraram 1 alerta**.
- **Seis rodadas de estranhos na HAIZ (20/10, 0454 a 0550): 2.129 leituras
  boas, máximo 0,26, 0 aprovados.** Rodada 0550 (já com `ARENA_FRENTE` 0,55
  e o log novo): 911 leituras, p99 0,21; quem ficou sentado 2:40 a 46-65 px
  deu UM alerta só. **156 a 181 ms por quadro, 5,4 análises/s**, contra
  296 a 545 nas rodadas anteriores com o mesmo código: a diferença é carga
  na caixa (outros grupos?), não o Arena. Descartes: 75 nota baixa, 53 de
  lado (17 entre 0,55 e 0,75, o resto perfil de verdade). Alerta #4 teve
  "mais parecido #3: 0,50", abaixo do 0,60 de juntar: se era a mesma
  pessoa, o 0,60 está alto para rosto de 75-86 px.
- **Rastreador: rosto que muda mais de 1,6x de largura é outra trilha**
  (`TAMANHO_MAX`). Achado no log do Samuel (20/10, sala cheia, ~5 rostos):
  um estranho de 54 px ao fundo sumiu, o Samuel entrou no mesmo ponto com
  179 px, herdou a trilha, e o placar tirou o alerta do estranho ("AUTORIZADO
  Samuel, era o desconhecido #5"). Comparar os vetores não separa esse caso
  do dono que começa longe e ilegível, por isso a trava é no rastreador.
  Samuel na HAIZ, antes da passada: 0,61 a 0,74 de frente (114 a 227 px),
  autorizado em 3 trilhas; de costas não há rosto. O `--calibrar` agora
  diz quanto cada leitura estava virada, para medir o `ARENA_FRENTE`.
- **Samuel depois da passada (21/10, 12 -> 18 amostras, `conferir` 100%,
  menor folga +0,46):** de frente 0,75 a 0,82 (antes ~0,73); virado 0,3:
  0,72 a 0,76; virado 0,5: 0,64 a 0,69; 131 a 143 px virado 0,5 a 0,6:
  0,45 a 0,52. **O ponto fraco é ANDANDO de lado:** trilha nova com 3
  leituras 0,34 / 0,30 / 0,27 (115 a 155 px). Estranhos, 2.558 leituras em
  todos os logs: pior leitura 0,27, pior média de 3 seguidas 0,24, de 8
  0,23. Baixar `ARENA_LIMIAR_ARCFACE` para 0,30 ainda deixaria 0,06 de
  colchão, mas só decidir depois de medir os outros três andando.
- **Juntar desconhecidos: corrigido depois da HAIZ.** (1) Trilha que ainda era
  vista depois que a outra começou (as duas no mesmo quadro) nunca é juntada:
  são duas pessoas. Uma janela de 1,5 s no lugar disso dava DOIS alertas para
  quem anda rápido e volta com outro número no quadro seguinte. (2) O
  limite é por motor: `ARENA_MESMO_DESC` (SFace, 0,45) e
  `ARENA_MESMO_DESC_ARCFACE` (0,60). (3) Toda junção aparece no terminal
  ("o mesmo desconhecido #k voltou (parecido 0,xx)") e todo alerta diz o mais
  parecido, para calibrar esse limite na caixa como o outro.
- **Desempenho na HAIZ:** procurar rosto em 1280 de largura
  (`ARENA_DETECCAO`, agora o padrão) baixou de ~530 para **~296 ms por
  quadro, 3,2 análises/s**, sem perder qualidade: o rosto continua medido no
  quadro cheio. **Não medir de novo quem já foi decidido foi tentado e
  desfeito:** a pessoa nova que ocupa o lugar herdava o nome (ensaio 4 de 4
  virou 1 de 4). O que sobra de peso é decodificar 2880x1620 a 30/s na CPU
  (`qtivdec` resolveria, mas deu "sem imagem" no último teste).
- **Vídeo fluido na página (`CAMERA_ARENA_VIDEO`, desligado por padrão).**
  A página mostrava só os quadros analisados (2 a 6 por segundo), e o grupo
  vizinho mostrava 28/30: parece travado mesmo decidindo em 1 s. Com
  `CAMERA_ARENA_VIDEO` (na HAIZ, o mesmo endereço com `stream=1`), o vídeo
  vem do fluxo LEVE da câmera, em outra conexão, a 25/s, com as caixas da
  última análise; a identificação continua no fluxo principal e não muda
  (ensaio igual com e sem). Caixa com mais de 0,8 s some (`MARCA_MAX_S`).
  A página mostra `leituras/s` (análise) e `quadros/s` (vídeo) separados.
  **Na HAIZ o `stream=1` não abriu (vídeo 0/s) e a página ficou PRETA**:
  agora, sem quadro do fluxo leve por 2 s, a página volta aos quadros
  analisados sozinha. Testar o fluxo leve no PC: `achar_rtsp.py IP --fluxo 1`.
  **Causa:** o fluxo leve da HAIZ é **H.265, 704x480** (o principal é
  H.264). `CAMERA_ARENA_VIDEO_CODEC=h265` vale só para essa conexão
  (`Gst(..., codec=)`); o `CAM_CODEC` continua sendo o da identificação.
  Ligado, o vídeo saiu em blocos verdes e rosa (H.265 com referência
  faltando): o cano do vídeo fluido usa `avdec_h265 output-corrupt=false`,
  que descarta em vez de mostrar. Só nele, não na identificação.
  30 leituras por segundo não existe nesta CPU com rosto em 4 MP.
- **Webcam no PC do laboratório:** o leitor padrão do Windows (MSMF) falha com
  `-1072873854`; `$env:OPENCV_VIDEOIO_PRIORITY_MSMF="0"` resolve.

**Estado em 20/10/2026 (laboratório, sem porta livre na caixa):** galeria
montada por fotos no PC do laboratório (`Desktop\Next-arena`, OpenCV 4.10 igual
ao da caixa) com os 4 da arena: **Lucas, Daniel, Samuel e Matheus**
(Guilherme e Enzo fora; Enzo opera o terminal). `conferir`: todos acertam
100% das fotos, menor folga +0,41. Uma foto do Matheus que puxava para o
Samuel saiu. Falta, com a caixa: `pc galeria`, a passada pela câmera da sala
(`--acrescentar`), calibrar e o ensaio cronometrado.

**Decisão de 20/10: a galeria da arena passou para o ArcFace.** Vídeo de
celular do Samuel (dono) e do Enzo (estranho), `comparar_modelos.py`: folga
+0,13 no SFace e +0,21 no ArcFace; do lado do estranho, o colchão até o limiar
dobrou (0,40 contra 0,45 no SFace; 0,24 contra 0,34 no ArcFace). Na arena com
o ArcFace e os limiares padrão 0,34 / 0,26: Samuel autorizado (0,71), Enzo 0
de 4 e 1 alerta. `arena\galeria.json` (no PC do laboratório) é a ArcFace;
`arena\galeria-sface.json` é a reserva SFace: voltar é trocar o arquivo, com
`ARENA_LIMIAR=0.45` e `ARENA_LIMIAR_BAIXO=0.38`. **Na caixa, `pc modelos` é
obrigatório agora** (leva o `w600k_mbf.onnx`). Falta confirmar com os vídeos
de Lucas, Daniel e Matheus e na câmera da caixa.

**O gargalo é pixel, não modelo.** A caixa lê o fluxo secundário em 640x360
(`CAM_LARG`/`CAM_ALT` em `aibox/gstcam.py`). Com a lente de ~99° da VIP 1230 D
G2, o rosto tem uns 44 px a 1 m e 11 px a 4 m (estimativa, medir no
laboratório), e o YuNet não acha abaixo de ~40. Em 1920x1080 seria 131 px a 1 m
e 33 px a 4 m. NPU, treino ou API paga não recuperam rosto de 11 px.

Plano, em ordem:

1. medir no laboratório o rosto em pixels a 2, 4 e 6 m, nas duas câmeras
2. rosto lido do fluxo principal (`subtype=0`), recortado na cabeça que o YOLO
   já acha (olhos, nariz, orelhas); a queda continua no fluxo leve
3. três estados por trilha: cadastrado (nome), não cadastrado, ainda não sei;
   decidir só depois de várias leituras boas do mesmo rosto
4. limiar calibrado com vídeo do laboratório (o 0,363 é da OpenCV para rosto
   bom); colegas de outros grupos fazem o papel de não cadastrado
5. cadastro com várias poses: fotos em casa (`cadastrar_fotos.py`) e depois uma
   passada pela câmera da sala com "Juntar" marcado (FEITO o caminho, falta cadastrar)
6. depois: `qtivdec` (decodificador por hardware), YOLO na NPU, e um modelo de
   rosto mais forte (AdaFace, MIT) que só cabe com a CPU livre

**Não treinar classificador com as pessoas do grupo:** ele não tem a opção
"nenhuma delas" e enfia todo visitante numa classe. Comparar vetor com cadastro,
como já é.

**No dia, banco SÓ local.** Cadastro feito no Postgres da AWS não existe no
SQLite do fallback: com a internet do evento caindo, o grupo some. Rodar sem
`DATABASE_URL`, cadastrar nesse `auditix.db`, levar `chave-bio.txt` junto e
cópia num pen drive. O e-mail de alarme não sai sem internet; sirene e painel
sim.

**Nuvem descartada para a final** (sem internet, LGPD, e não resolve pixel):

- AWS Rekognition: US$ 0,001 por rosto consultado; busca só o maior rosto da
  foto, então é uma chamada por pessoa
- Azure Face: identificação exige aprovação da Microsoft
- SageMaker Edge Manager: a AWS desligou em 26/04/2024
- "guardar fotos e mandar quando a internet voltar": guarda rosto de quem não
  consentiu e chega depois da apresentação
- InsightFace (buffalo_l): modelo só para pesquisa, comercial sob cotação

**LGPD:** em ago/2026 a ANPD suspendeu o reconhecimento facial de alunos da rede
estadual do Paraná (Nota Técnica nº 4/2026): faltou necessidade,
proporcionalidade e alternativa menos invasiva. Resposta pronta: finalidade é
segurança, não chamada; consentimento do responsável (art. 14); quem não se
cadastrou não deixa nada (conferir se `/api/reconhecer` descarta o vetor antes
de afirmar no pitch).

**Material que o Enzo mandou, ainda não aproveitado:**

- post sobre a **Decisions API da OpenAI** (beta desde 06/10/2026, `gpt-6-luna`,
  US$ 0,10 por milhão de tokens de entrada, saída grátis). Não serve para
  identificar: não compara com cadastro e a política da OpenAI proíbe base de
  rostos sem consentimento. Ideia guardada: segunda opinião sobre briga e
  corrida mandando só o desenho do esqueleto, sem rosto. Precisa de internet.
- **github.com/gpscorreia/face-liveness-python**: prova de vida por desafios
  sorteados (pisque, vire à esquerda, vire à direita) com MediaPipe Face
  Landmarker, piscada pelas notas `eyeBlinkLeft`/`eyeBlinkRight` > 0,4.
  **Sem licença: só a ideia, nada de código.** Não reconhece ninguém e precisa de
  uma pessoa colaborando perto da câmera, então não serve para a sala. Duas
  ideias para o cadastro: sortear a ordem dos desafios (ordem fixa deixa passar
  vídeo gravado) e dar prova de vida ao balcão da caixa, que hoje não tem porque
  o YuNet dá só 5 pontos (testar se o MediaPipe instala na caixa).

- post do **VIGIA** (TCC da Uniamérica, out/2026): YOLOv8n acha pessoas e, com
  duas ou mais, uma R3D-18 olha 16 quadros e diz violência ou não; treinada no
  **RWF-2000** (2.000 vídeos de câmera de vigilância), 90% de acurácia, AUC 0,95,
  11 de 12 cenários encenados certos, 14 ms por análise **em GPU de PC**. Serve
  para tirar a briga de "regra" e virar modelo treinado, como a queda. Não
  copiar a R3D-18 para a caixa (vídeo inteiro em 3D, pesada para a CPU ARM sem
  NPU); o caminho do nosso jeito é passar o YOLO11-pose nos vídeos do RWF-2000 e
  treinar uma rede pequena sobre os pontos de DUAS pessoas, como fizemos com a
  queda. Conferir a licença do RWF-2000 (github mchengny) e lembrar que os
  vídeos vêm do YouTube. Não ajuda no desafio da facial: fica para depois dele.

## Regras do projeto que não se quebram

- **Linha do banco nunca é apagada** — quebraria a cadeia de hash. A tabela
  `calibracao` é a única exceção, e é exatamente por NÃO estar na cadeia.
- **O `.env` não vai para o git.** É onde mora a senha da câmera.
- Corrida e briga são **regra**, não modelo treinado, e o código, a tela e o
  pitch dizem isso. Queda é modelo, com 4.509 clipes por trás.
- A ideia do hospital (SVATech Health) saiu do projeto: não há mais arquivos
  dela. Se voltar a aparecer alguma menção, é resto — pode tirar.

## Testes

```bash
node testes/aibox.mjs      # o Python da caixa calcula igual ao navegador?
node testes/rede-queda.mjs  # o JS calcula igual ao treino?
```

Os 30 arquivos `.mjs` em `testes/` rodam com o servidor no ar (`CALIBRACAO=1`).
