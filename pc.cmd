@echo off
REM ===========================================================================
REM  ESTA E A COPIA DA VERSAO NPU (ramo npu/divisao-npu-cpu): tudo vai para
REM  ~/auditix-npu na caixa. A versao atual (~/auditix, pasta Next-Final) nao e tocada.
REM  Auditix IA - atalhos do PC do laboratorio.   Uso:  pc <comando>
REM
REM  POR QUE ISTO EXISTE. O PC do laboratorio so tem internet no DHCP e a caixa
REM  so responde no IP fixo, entao toda ida e vinda de codigo e uma troca de
REM  rede. Sao quatro comandos longos de netsh, digitados a mao, sem internet
REM  para copiar e colar de lugar nenhum - e cada erro de digitacao custa uma
REM  rodada de tentativa e erro.
REM
REM  SEM ACENTO DE PROPOSITO: o cmd do Windows embaralha acento e o texto fica
REM  ilegivel justamente na hora em que ele precisa ser lido.
REM ===========================================================================
setlocal
set RAMO=npu/divisao-npu-cpu
set CAIXA=grupo11@192.168.50.10
set MEUIP=192.168.50.72
REM Nome da placa de rede com cabo. No PC do laboratorio de 20/10 ela NAO se
REM chamava "Ethernet" e o netsh respondeu so "Element not found". Para usar
REM outro nome:  set PLACA=Ethernet 2   (ou $env:PLACA="Ethernet 2" no PowerShell)
REM antes do pc. O nome certo sai de:  Get-NetAdapter
if not defined PLACA set PLACA=Ethernet

if "%1"=="" goto menu
if /i "%1"=="puxar"    goto puxar
if /i "%1"=="internet" goto internet
if /i "%1"=="rede"     goto rede
if /i "%1"=="enviar"   goto enviar
if /i "%1"=="modelos"  goto modelos
if /i "%1"=="galeria"  goto galeria
if /i "%1"=="entrar"   goto entrar
if /i "%1"=="servidor" goto servidor
if /i "%1"=="pitch"    goto pitch
if /i "%1"=="copiar"   goto copiar
if /i "%1"=="npu"      goto npu
goto menu

:menu
echo.
echo   pc puxar      internet, git pull, e volta para o IP fixo
echo   pc internet   so volta para o DHCP e FICA la (para navegar, baixar)
echo   pc rede       so volta para o IP fixo (192.168.50.72)
echo   pc enviar     copia o codigo (aibox e daten\app) para a caixa
echo   pc modelos    copia os modelos de rosto (39 MB, so uma vez)
echo   pc galeria    copia a galeria da arena (arena\galeria.json) para a caixa
echo   pc entrar     abre o ssh na caixa
echo   pc servidor   sobe o servidor aceitando conexao de fora
echo   pc copiar     VERSAO NPU: copia .env, modelos e galeria de ~/auditix para ~/auditix-npu (so le o original)
echo   pc npu        VERSAO NPU: copia o pacote da NPU (pasta npu-pacote, baixada do GitHub) para a caixa
echo   pc pitch      abre a apresentacao (Auditix-pitch.html) no navegador
echo.
echo   A ordem de uma noite normal:  puxar -^> enviar -^> servidor (outra janela) -^> entrar
echo.
goto fim

:admin
REM netsh so funciona como administrador, e sem isto ele falha com uma mensagem
REM que nao diz que o problema e esse.
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo   !! ABRA O CMD COMO ADMINISTRADOR.
  echo      Menu Iniciar, digite cmd, botao direito, "Executar como administrador".
  echo.
  exit /b 1
)
exit /b 0

:internet
REM O PC NAO VOLTA A NAVEGAR SOZINHO depois de mudar o cabo de lugar. A placa
REM continua cravada no 192.168.50.72, que na rede da FIAP nao existe, e ela
REM nem pede endereco porque acha que ja tem um. O sintoma e "a internet nao
REM volta" com o cabo certo na parede - e nada aponta para o IP.
REM
REM O `puxar` tambem faz isto, mas ele volta para o IP fixo no fim. Este aqui
REM FICA no DHCP, que e o que voce quer quando o assunto e navegar.
call :admin || goto fim
echo.
echo -- voltando para o DHCP --
echo    O cabo tem que estar na tomada da PAREDE. No switch da caixa nao ha
echo    internet: a AIBOX nao e roteador, e o DHCP de la nao responde.
netsh interface ip set address name="%PLACA%" dhcp
netsh interface ip set dns     name="%PLACA%" dhcp
ipconfig /renew
echo.
echo    Se ainda nao navegar, espere uns 10 segundos e rode  ipconfig  para
echo    ver se chegou um endereco que NAO comeca com 192.168.50.
goto fim

:puxar
call :admin || goto fim
echo.
echo -- voltando para o DHCP para ter internet --
netsh interface ip set address name="%PLACA%" dhcp
netsh interface ip set dns     name="%PLACA%" dhcp
echo    esperando a rede acordar...
timeout /t 8 /nobreak >nul
echo.
echo -- git pull --
git pull origin %RAMO%
if errorlevel 1 (
  echo.
  echo    !! o pull falhou. A rede costuma demorar mais que os 8 segundos:
  echo       tente  git pull origin %RAMO%  de novo antes de seguir.
  echo.
  pause
)
echo.
goto rede

:rede
call :admin || goto fim
echo -- voltando para o IP fixo %MEUIP% --
netsh interface ip set address name="%PLACA%" static %MEUIP% 255.255.255.0
echo.
echo    A REDE DEMORA A ACORDAR. O primeiro ping falha com "Destination host
echo    unreachable" e o segundo funciona. Isso ja custou meia hora achando
echo    que era cabo.
echo.
timeout /t 6 /nobreak >nul
ping -n 2 192.168.50.10 >nul 2>&1
if errorlevel 1 (
  echo    primeira tentativa falhou, tentando de novo...
  ping -n 3 192.168.50.10
) else (
  echo    a caixa responde.
)
goto fim

:enviar
echo.
echo -- copiando o codigo para a caixa --
REM daten\app e o motor de rosto do --rosto. Sem ele a caixa sobe, mas o
REM reconhecimento sai desligado com "No module named daten". As pastas sao
REM criadas antes porque o scp nao cria pasta que nao existe do lado de la.
ssh %CAIXA% "mkdir -p ~/auditix-npu/aibox ~/auditix-npu/daten/app ~/auditix-npu/daten/models"
if errorlevel 1 (
  echo.
  echo    !! a caixa nao respondeu. Rode  pc rede  primeiro: sem o IP fixo ela nao existe.
  goto fim
)
scp aibox\*.py aibox\*.sh %CAIXA%:~/auditix-npu/aibox/
scp daten\app\*.py %CAIXA%:~/auditix-npu/daten/app/
if errorlevel 1 (
  echo.
  echo    !! nao copiou tudo. Veja a mensagem acima.
  goto fim
)
REM O \r do Windows morre AQUI, do lado de la, e nao depois. Deixar para o
REM usuario lembrar e o que fez o bash da caixa responder "$'\r': command not
REM found" - uma mensagem que nao parece nem de longe com a causa.
echo    limpando o fim de linha do Windows do lado de la...
ssh %CAIXA% "cd ~/auditix-npu && sed -i 's/\r$//' aibox/*.py aibox/*.sh daten/app/*.py"
echo.
echo    PRONTO. Na caixa agora e so:   bash aibox/ir.sh
goto fim

:modelos
echo.
echo -- copiando os modelos de rosto (YuNet + SFace, 39 MB) --
echo    So precisa uma vez: eles nao mudam. O --rosto nao funciona sem eles.
ssh %CAIXA% "mkdir -p ~/auditix-npu/daten/models"
scp daten\models\*.onnx %CAIXA%:~/auditix-npu/daten/models/
if errorlevel 1 (
  echo.
  echo    !! nao copiou. Confira se os arquivos existem aqui:  dir daten\models
  echo       se nao existirem, rode  pc puxar  antes.
  goto fim
)
echo.
echo    PRONTO. Conferindo o tamanho do lado de la (o SFace tem que dar ~38 MB):
ssh %CAIXA% "ls -la ~/auditix-npu/daten/models/"
goto fim

:galeria
echo.
echo -- copiando a galeria da arena (quem esta autorizado) --
REM Gerada no PC com:  python aibox\cadastrar_fotos.py fotos-cadastro --galeria arena\galeria.json
REM So os 128 numeros de cada autorizado, nenhuma foto. Na caixa, o modo arena
REM (bash aibox/arena.sh) compara contra ela sem precisar deste PC.
if not exist arena\galeria.json (
  echo    !! nao achei arena\galeria.json. Gere com cadastrar_fotos.py --galeria primeiro.
  goto fim
)
ssh %CAIXA% "mkdir -p ~/auditix-npu/arena"
scp arena\galeria.json %CAIXA%:~/auditix-npu/arena/galeria.json
if errorlevel 1 (
  echo.
  echo    !! nao copiou. A caixa respondeu? Rode  pc rede  e tente de novo.
  goto fim
)
echo.
echo    PRONTO. Conferindo do lado de la:
ssh %CAIXA% "cd ~/auditix-npu && /opt/eduvision/venv/bin/python aibox/galeria.py"
goto fim

:copiar
echo.
echo -- VERSAO NPU: copiando .env, modelos e galeria da versao atual --
REM A GALERIA vai POR CIMA, sempre: com cp -n a copia ficava velha para sempre.
REM Nunca apontar o GALERIA da pasta NPU para ~/auditix (o Cadastrar gravaria la).
REM So LE ~/auditix. cp -n nao sobrescreve nada que ja exista em ~/auditix-npu,
REM e nada e gravado em ~/auditix: a versao atual fica intacta para a final.
ssh %CAIXA% "mkdir -p ~/auditix-npu/daten ~/auditix-npu/arena && cp -n ~/auditix/.env ~/auditix-npu/.env; cp -rn ~/auditix/daten/models ~/auditix-npu/daten/; cp -rn ~/auditix/treino ~/auditix-npu/ 2>/dev/null; cp ~/auditix/arena/galeria.json ~/auditix-npu/arena/galeria.json 2>/dev/null; ls -la ~/auditix-npu/arena/galeria.json; ls -la ~/auditix-npu ~/auditix-npu/daten/models"
echo.
echo    O .env so e copiado na PRIMEIRA vez. Diferencas entre o .env atual (~/auditix, com <) e o da NPU (>), senhas escondidas:
ssh %CAIXA% "diff ~/auditix/.env ~/auditix-npu/.env | sed -E 's/(password=)[^&]*/\1***/; s/(CAM_PW=).*/\1***/; s/(rtsp:\/\/[^:\/@]+:)[^@]*@/\1***@/' || true; echo (fim da comparacao: nada acima = iguais)"
echo    Se um limiar mudou em ~/auditix depois da copia, copie a linha para ~/auditix-npu/.env na mao (nano ~/auditix-npu/.env).
goto fim

:npu
echo.
echo -- VERSAO NPU: pacote da NPU (modelos .dlc + bibliotecas do SNPE) --
REM O pacote e o zip "npu-pacote" do GitHub Actions, descompactado AQUI, na
REM pasta npu-pacote (tem que ter modelos\ e npu-lib\ dentro).
if not exist npu-pacote\modelos\yunet.dlc (
  echo    !! nao achei npu-pacote\modelos\yunet.dlc. Baixe o zip npu-pacote e
  echo       descompacte nesta pasta, numa pasta chamada npu-pacote.
  goto fim
)
ssh %CAIXA% "mkdir -p ~/auditix-npu/daten/models/npu ~/auditix-npu/npu-lib/dsp"
REM So o que a caixa usa: yunet (8 bits) e a reserva de 16, o ArcFace por canal e o pose. Metade do scp.
scp npu-pacote\modelos\yunet.dlc npu-pacote\modelos\yunet_a16.dlc npu-pacote\modelos\arcface_pc.dlc npu-pacote\modelos\pose.dlc npu-pacote\modelos\relatorio.txt %CAIXA%:~/auditix-npu/daten/models/npu/
scp npu-pacote\npu-lib\* %CAIXA%:~/auditix-npu/npu-lib/
scp npu-pacote\npu-lib\dsp\* %CAIXA%:~/auditix-npu/npu-lib/dsp/
ssh %CAIXA% "ls -la ~/auditix-npu/daten/models/npu ~/auditix-npu/npu-lib ~/auditix-npu/npu-lib/dsp"
goto fim

:entrar
ssh %CAIXA%
goto fim

:servidor
echo.
echo -- servidor, aceitando conexao da caixa --
echo    HOST=0.0.0.0 e o que deixa a AIBOX alcancar este PC. Sem isso o
echo    servidor so responde aqui dentro e o painel nunca enche.
echo.
set HOST=0.0.0.0
set CALIBRACAO=1
where uv >nul 2>&1
if errorlevel 1 (python servidor.py) else (uv run servidor.py)
goto fim

:pitch
echo.
echo -- a apresentacao, servida so para este PC --
echo    Pelo duplo clique as fontes nao carregam: o navegador barra fonte de
echo    arquivo local. Por aqui carrega tudo, sem internet.
echo    Abre no MODO 5 MIN (10 slides). M volta ao deck completo.
echo    Teclas: setas trocam, F tela cheia, N roteiro de fala, R repete o evento,
echo    numero + Enter abre qualquer slide (para as perguntas), T zera o tempo.
echo    Os videos ficam em ppt\midia (fora do Git). Feche a janela "pitch" no fim.
where uv >nul 2>&1
if errorlevel 1 (start "pitch" python -m http.server 8090 --bind 127.0.0.1) else (start "pitch" uv run python -m http.server 8090 --bind 127.0.0.1)
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8090/Auditix-pitch.html
goto fim

:fim
endlocal
