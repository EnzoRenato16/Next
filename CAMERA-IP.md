# Câmera IP na Sala — passo a passo

A webcam do notebook serve para demonstrar. Numa sala de verdade a câmera fica
no alto, presa, olhando a sala inteira — e isso é uma câmera IP.

Este guia vai da caixa fechada até a Sala analisando a imagem dela.

## Antes de começar: onde a câmera vai ficar

**Canto da sala, uns 2,5 a 3 metros, inclinada para baixo (30° a 45°).**

Não é gosto. O detector de queda mede o quadril descer e o tronco tombar — os
dois são movimentos verticais na imagem. **De uma câmera no teto olhando para
baixo, uma pessoa em pé e a mesma pessoa caída ocupam quase o mesmo lugar no
quadro**, e o detector perde o que usa para decidir. As 4.509 quedas que
treinaram o modelo são todas de lado.

A regra prática: se na imagem dá para ver o **quadril** das pessoas, está bom.
Sem quadril a análise de queda desliga sozinha — e a faixa da tela avisa.

## 1. Câmera

Serve qualquer câmera com **RTSP**. Duas que testamos no papel:

- **Tapo C200** (~R$ 200) — barata, 1080p, gira pelo app. Entrega 15 quadros
  por segundo: custa 2 pontos de revocação (89% → 87%), medido em
  `treino/taxa.py`. Boa para montar e testar.
- **Intelbras VIP 1230 D G2** (~R$ 400–680) — sem app, sem nuvem, PoE, 30fps.
  É a escolha para instalação de verdade.

**Não compre câmera a bateria ou solar** (Tapo C425, C460, C660, D230): elas
não têm RTSP. Funcionam lindamente no celular e não existem para o nosso site.

## 2. Ligar a câmera e achar o IP

Na Tapo: app Tapo, adicionar dispositivo, conectar ao Wi-Fi da casa/escola.
Na Intelbras: cabo de rede; o IP sai no utilitário da Intelbras ou na lista do
roteador.

Anote o IP (algo como `192.168.0.50`) e **reserve esse IP no roteador** pelo
MAC da câmera. Sem isso, um dia ele muda sozinho e o sistema "para sem motivo".

## 3. Criar a conta da câmera (só Tapo)

A Tapo tem **duas senhas diferentes**, e é aqui que todo mundo trava:

- a **conta Tapo** (seu e-mail) é da nuvem, serve para o app;
- a **conta da câmera** é local, e é a única que o RTSP aceita.

No app: câmera → engrenagem → **Configurações avançadas** → **Conta da
câmera**. Crie usuário e senha. **Use só letras e números** — `@`, `:` e `/`
quebram a URL mais adiante.

Na Intelbras não existe esse passo: você abre o IP dela no navegador e
configura ali, sem app e sem conta em lugar nenhum.

## 4. Testar no VLC ANTES de qualquer outra coisa

VLC → *Mídia* → *Abrir fluxo de rede* → cole:

```
rtsp://USUARIO:SENHA@192.168.0.50:554/stream1
```

(Na Intelbras o caminho é outro, veja o manual do modelo.)

**Faça este teste.** Se a imagem aparecer aqui, a câmera está resolvida e tudo
o que der errado depois é software. Se você pular direto para o passo 5 e não
funcionar, vai ficar depurando câmera, senha e ponte ao mesmo tempo.

## 5. A ponte (go2rtc)

Navegador nenhum abre RTSP — não existe truque, é limitação do Chrome. Quem
traduz é o **go2rtc**: um executável só, sem instalador.

Baixe em <https://github.com/AlexxIT/go2rtc/releases> (`go2rtc_win64.zip`) e
deixe o `.exe` numa pasta com um arquivo `go2rtc.yaml` ao lado:

```yaml
api:
  listen: ":1984"
  origin: "*"        # sem isto o navegador recusa a conexão

streams:
  sala: rtsp://USUARIO:SENHA@192.168.0.50:554/stream1
```

Dois cliques no `go2rtc.exe` e deixe a janela aberta. Confira em
<http://127.0.0.1:1984> — a câmera tem que aparecer na lista.

**A senha da câmera fica neste arquivo e em nenhum outro lugar.** Nunca no
HTML: a página é servida ao navegador, e qualquer aluno lê o código com F12.

## 6. Apontar a Sala para a ponte

```powershell
uv run servidor.py
```

Abra <http://127.0.0.1:8000/>, clique em **"fonte de vídeo: webcam"** logo
abaixo do botão, e escreva:

```
127.0.0.1:1984/sala
```

Clique em **Abrir a sala**. A escolha fica salva no navegador; para voltar à
webcam, é só apagar o campo.

## Quando não funciona

| A tela diz | O que é |
|---|---|
| a ponte não respondeu | go2rtc fechado, ou falta `origin: "*"` no yaml |
| a ponte não conhece esse fluxo | o nome não bate com o do yaml (`sala`) |
| a câmera IP não entregou imagem | a ponte respondeu mas a câmera não — teste no VLC |
| erro 401 no go2rtc | senha errada, ou caractere especial nela; ou reinicie a câmera |

## Internet

Nenhuma. Os modelos de rosto e de corpo ficam em `vendor/`, versionados junto
do projeto e servidos pelo proprio `servidor.py` — as fontes tambem. Com todo
acesso externo bloqueado, a Sala e o Painel abrem do mesmo jeito, com zero
pedidos para fora.

Vinham de CDN, e bastava a rede bloquear `jsdelivr` ou `googleapis` para a tela
ficar presa em "Carregando o detector de corpo..." para sempre. Numa rede de
escola ou de evento, isso e o projeto inteiro nao abrindo.

## Duas coisas para a apresentação

**A imagem não sai da rede.** Câmera, ponte e servidor na mesma máquina/rede;
nada trafega para a internet. Se usarem a Tapo, ela ainda conversa com a nuvem
da TP-Link — dá para cortar com uma regra no roteador bloqueando a internet
para o IP dela (o RTSP local continua funcionando; o relógio interno da câmera
pode desandar, mas quem carimba a hora dos eventos é o nosso servidor).

**O atraso é de fração de segundo**, porque a ponte entrega WebRTC. Se algum
tutorial mandar usar HLS, ignore: HLS atrasa vários segundos e serve para
gravação, não para alerta.

---

O caminho da câmera IP tem teste: `testes/camera-ip.mjs`. Ele não precisa da
câmera — sobe um par WebRTC falso, a 15fps de propósito. O que ele não prova é
compatibilidade com o go2rtc de verdade; isso só com o equipamento na mão.
