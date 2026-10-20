# Operar a AI BOX: comandos e problemas

## A rede do laboratório

```
câmera HAIZ 192.168.50.109  ─┐
câmera Intelbras 192.168.50.108 ─┼─ switch ─ AI BOX 192.168.50.10 ─ PC 192.168.50.72
```

No PC do laboratório (Windows, usuário `labsfiap`, pasta
`Desktop\Next-arena`). O notebook não tem porta de rede: usa adaptador USB
Realtek, que aparece como **"Ethernet 2"**.

```powershell
netsh interface ip set address name="Ethernet 2" static 192.168.50.72 255.255.255.0
ssh grupo11@192.168.50.10
```

- A rede demora a acordar: o primeiro `ping`/`ssh` pode falhar; repita.
- No PowerShell os scripts do projeto são `.\pc`, não `pc`.
- Placa com outro nome: `$env:PLACA="Ethernet 2"` antes do `.\pc`.

## Levar código novo para a caixa (no PC)

```powershell
git pull origin claude/entender-projeto-0tgk9u
.\pc enviar        # copia aibox\*.py, *.sh e daten\app e limpa o \r
.\pc modelos       # modelos de rosto (inclui o w600k_mbf.onnx), uma vez
.\pc galeria       # copia arena\galeria.json do PC para a caixa
```

## Na caixa

```bash
cd ~/auditix
P=/opt/eduvision/venv/bin/python          # o Python certo (nao e o python3)
export PYTHONPATH=$HOME/pylibs
```

### Rodar a arena (o comando da prova)

```bash
bash aibox/arena.sh
```

No notebook: `http://192.168.50.10:8080` (com `http://`). O `arena.sh`
imprime outro IP (`192.168.225.1`), que é de outra placa: use o do SSH.
Ctrl+C mostra e grava o resultado.

### Calibrar (ver a nota de cada leitura)

```bash
bash aibox/arena.sh --calibrar 2>&1 | tee arena/calib-NOME.log
cat arena/calib-NOME.log            # para colar na conversa
```

Roteiro com uma pessoa do grupo: de frente perto, de frente longe, três quartos
para cada lado, e **atravessar andando 2 ou 3 vezes** (o caso mais fraco).

### Cadastrar (a passada pela câmera da arena)

Pelo botão (recomendado): `bash aibox/arena.sh --preparo`, escolher o nome na
página e clicar em **Cadastrar**. Vale o **maior rosto** (≥ 90 px e 1,5x maior
que o segundo); a pessoa fica na frente de todos, a 1 ou 2 m, virando a cabeça
devagar. Só completa quem já está na galeria.

Pelo terminal (exige estar sozinho na imagem):

```bash
cp arena/galeria.json arena/galeria-antes.json
CAM="$(grep ^CAMERA_ARENA= .env | cut -d= -f2-)"
$P aibox/cadastrar.py --nome "Lucas" --camera "$CAM" --galeria arena/galeria.json --acrescentar
$P aibox/galeria.py conferir
```

### O `.env` da caixa (sem senha aqui)

- `CAMERA_ARENA=` endereço da HAIZ no padrão Xiongmai:
  `rtsp://192.168.50.109:554/user=USUARIO&password=SENHA&channel=1&stream=0.sdp`
  (2880x1620, H.264). Usuário e senha: com o grupo, nunca no Git.
- Para a Intelbras .108: `rtsp://192.168.50.108:554/cam/realmonitor?channel=1&subtype=0`
  com `CAM_USER`/`CAM_PW` no `.env` e `CAM_CODEC=h265` (o principal dela é
  H.265; por software dá atraso crescente, inviável sem o `qtivdec`).
- Cópia da configuração da HAIZ: `.env.bak-haiz` (voltar: `cp .env.bak-haiz .env`).
- Editar sempre apagando e acrescentando a linha (o `&` do endereço embaralha
  o `sed` de substituição).

### Velocidade

- Ver quem usa a CPU: `top -bn1 | head -15` e
  `pgrep -af "gst-launch|arena.py|cadastrar.py"`. Nunca rodar a passada e a
  arena juntas (duas decodificações de 4 MP).
- Em 21/10 de manhã, grupo05 e grupo06 usavam ~3 núcleos (load 18,7): a
  lentidão era deles.
- Teste do decodificador de hardware (uma vez, arena parada):

  ```bash
  URL="$(grep ^CAMERA_ARENA= .env | cut -d= -f2-)"
  timeout 20 gst-launch-1.0 rtspsrc location="$URL" protocols=tcp ! rtph264depay ! h264parse ! qtivdec ! video/x-raw,format=NV12 ! videoconvert ! video/x-raw,format=BGR ! fakesink num-buffers=90 2>&1 | tail -5
  ```

  Se terminar sem erro: `GST_DECODIFICADOR=qtivdec bash aibox/arena.sh --calibrar`
  e comparar CPU e leituras/s. Só deixar no `.env` se a imagem sair normal.
- `ARENA_DETECCAO=960` deixa a busca de rosto ~40% mais barata (rostos muito
  pequenos podem sumir).

## Problemas conhecidos

| sintoma | causa | o que fazer |
|---|---|---|
| `Connection timed out` no ssh | rede acordando | repetir |
| `Connection closed ... port 22` | 3 senhas erradas | chamar o ssh de novo |
| `python: command not found` na caixa | comando do PC rodado na caixa | `exit` e rodar no PowerShell |
| `401` da câmera | caminho ou senha | conferir com `achar_rtsp.py` no PC |
| `403` da câmera | câmera bloqueou o IP por insistência | Ctrl+C, nada por 30 min |
| `451 Parameter Not Understood` | caminho de outro fabricante | a HAIZ é Xiongmai |
| `not-linked` | codec errado (H.265 com cano H.264) | `CAM_CODEC=h265` |
| imagem em blocos verdes e rosa | H.265 corrompido | não usar esse fluxo |
| porta 8080 ocupada | serviço da sala rodando | `bash aibox/servico.sh parar` |
| `$'\r': command not found` | fim de linha do Windows | `.\pc enviar` limpa |
| comando colado termina em `--` | linha longa quebrou | usar variável curta |
| "mais de um rosto" na passada | HAIZ vê a sala toda | usar o botão (`--preparo`) |
| passada recusada com notas ~0,0 | colheu outra pessoa | refazer com a pessoa mais perto |

## Descobrir o caminho de uma câmera (no PC)

```powershell
python aibox\achar_rtsp.py 192.168.50.109 --usuario admin            # principal
python aibox\achar_rtsp.py 192.168.50.109 --usuario admin --fluxo 1  # leve
```

Pede a senha sem mostrar, tenta um caminho por vez com pausa, e diz
resolução e codec.
