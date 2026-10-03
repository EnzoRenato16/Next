@echo off
REM ===========================================================================
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
set RAMO=claude/entender-projeto-0tgk9u
set CAIXA=grupo11@192.168.50.10
set MEUIP=192.168.50.72
set PLACA=Ethernet

if "%1"=="" goto menu
if /i "%1"=="puxar"    goto puxar
if /i "%1"=="internet" goto internet
if /i "%1"=="rede"     goto rede
if /i "%1"=="enviar"   goto enviar
if /i "%1"=="modelos"  goto modelos
if /i "%1"=="entrar"   goto entrar
if /i "%1"=="servidor" goto servidor
if /i "%1"=="pitch"    goto pitch
goto menu

:menu
echo.
echo   pc puxar      internet, git pull, e volta para o IP fixo
echo   pc internet   so volta para o DHCP e FICA la (para navegar, baixar)
echo   pc rede       so volta para o IP fixo (192.168.50.72)
echo   pc enviar     copia o codigo (aibox e daten\app) para a caixa
echo   pc modelos    copia os modelos de rosto (39 MB, so uma vez)
echo   pc entrar     abre o ssh na caixa
echo   pc servidor   sobe o servidor aceitando conexao de fora
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
ssh %CAIXA% "mkdir -p ~/auditix/aibox ~/auditix/daten/app ~/auditix/daten/models"
if errorlevel 1 (
  echo.
  echo    !! a caixa nao respondeu. Rode  pc rede  primeiro: sem o IP fixo ela nao existe.
  goto fim
)
scp aibox\*.py aibox\*.sh %CAIXA%:~/auditix/aibox/
scp daten\app\*.py %CAIXA%:~/auditix/daten/app/
if errorlevel 1 (
  echo.
  echo    !! nao copiou tudo. Veja a mensagem acima.
  goto fim
)
REM O \r do Windows morre AQUI, do lado de la, e nao depois. Deixar para o
REM usuario lembrar e o que fez o bash da caixa responder "$'\r': command not
REM found" - uma mensagem que nao parece nem de longe com a causa.
echo    limpando o fim de linha do Windows do lado de la...
ssh %CAIXA% "cd ~/auditix && sed -i 's/\r$//' aibox/*.py aibox/*.sh daten/app/*.py"
echo.
echo    PRONTO. Na caixa agora e so:   bash aibox/ir.sh
goto fim

:modelos
echo.
echo -- copiando os modelos de rosto (YuNet + SFace, 39 MB) --
echo    So precisa uma vez: eles nao mudam. O --rosto nao funciona sem eles.
ssh %CAIXA% "mkdir -p ~/auditix/daten/models"
scp daten\models\*.onnx %CAIXA%:~/auditix/daten/models/
if errorlevel 1 (
  echo.
  echo    !! nao copiou. Confira se os arquivos existem aqui:  dir daten\models
  echo       se nao existirem, rode  pc puxar  antes.
  goto fim
)
echo.
echo    PRONTO. Conferindo o tamanho do lado de la (o SFace tem que dar ~38 MB):
ssh %CAIXA% "ls -la ~/auditix/daten/models/"
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
