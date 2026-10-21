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
- **Fluxo principal da HAIZ em 1920x1080 a 10–12 quadros/s** (página web da
  câmera). A arena já reduz para 1920, então o rosto não perde pixel, e a CPU
  deixa de decodificar 4 MP a 30/s (o maior peso hoje). Comparar `ms` e
  `latencia` na linha de status antes e depois.
- `latencia` na página e no resultado é a idade do quadro na decisão (desde
  que saiu do GStreamer); "tempo por quadro" é só a análise. O buffer do
  `rtspsrc` é 0 na arena (`ARENA_LATENCIA`, a sala segue com 100); se a
  imagem vier rasgada, `ARENA_LATENCIA=100` no `.env`.
- `NUCLEOS=grandes` agora também vale na arena (rosto nos 4 núcleos grandes,
  decodificação nos 4 pequenos). Só deixar no `.env` se `ms` cair.

## Deixar a caixa mais rápida (uma vez, no laboratório)

Na ordem. Cada passo é independente: se um não der certo, siga para o próximo.
Antes de cada um, anote o `ms` e a `latencia` da linha de status da arena
(`bash aibox/arena.sh --segundos 60`), para comparar depois.

1. **Vídeo decodificado pelo hardware da caixa.** Com a arena parada:

   ```bash
   $P aibox/acelerar.py
   ```

   Ele testa por 20 s, com uma conexão só. Se aparecer `FUNCIONOU`, já ficou
   ligado no `.env`. Abra a arena e olhe a imagem da página: se estiver
   estranha (blocos, cores erradas), `$P aibox/acelerar.py --desfazer`.
2. **HAIZ no tamanho que a arena usa.** No navegador do PC, abra
   `http://192.168.50.109` e entre com o usuário da câmera. Em Configuração →
   Codificação (o nome pode variar: "Encode", "Vídeo"), no **fluxo principal**:
   resolução **1080P (1920x1080)** e **12 quadros/s**. Salve. O caminho
   RTSP no `.env` não muda. Se a página da câmera pedir plugin ou não abrir,
   pule este passo.
3. **Núcleos.** `$P aibox/medir.py --nucleos`. Se ele disser `GANHA`, ponha
   `NUCLEOS=grandes` no `.env`; se disser `NAO GANHA`, não mexa.
4. **Sala e arena nunca juntas.** O `arena.sh` já para a sala sozinho antes de
   começar. Depois da arena, se quiser a sala de novo:
   `bash aibox/servico.sh iniciar`.

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
