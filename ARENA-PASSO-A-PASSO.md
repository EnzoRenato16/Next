# Laboratório, ensaio da ARENA: o que fazer, na ordem

Meta de hoje: deixar a AI BOX pronta para a arena de sábado e sair de lá com
**três números anotados**: a nota dos autorizados, a nota dos desconhecidos e
o tempo do setup. Prazo final: quarta 21/10 à noite, quando o professor
recolhe a caixa.

Leve: este guia no celular, as fotos do grupo no PC (se já chegaram), **dois
colegas de OUTRO grupo** para fazer o papel de desconhecido, e um cronômetro.

Quem vai ser cadastrado: **só os 3 ou 4 que vão entrar na arena**. A regra
proíbe ter mais gente cadastrada do que os autorizados previstos.

---

## 1. No PC: pegar o código novo (2 min)

Abra o **cmd como administrador** (Menu Iniciar, digite `cmd`, botão direito,
"Executar como administrador") e vá para a pasta do projeto:

```cmd
cd C:\Users\EWZ\Desktop\Next
pc puxar
```

O `pc puxar` vai para a internet, faz o `git pull` e volta para o IP fixo
`192.168.50.72`. Confira que chegou o commit novo:

```cmd
git log --oneline -1
```

Tem que aparecer `Revisao do modo arena` ou algo mais novo.

> No PowerShell é `.\pc puxar`, não `pc puxar`.
> O cabo do PC tem que estar na **parede** para o pull e no **switch da caixa**
> para falar com ela.

**Só se for cadastrar por FOTOS** (passo 5A), ainda com internet:

```cmd
pc internet
pip install opencv-python numpy
pc rede
```

## 2. No PC: mandar o código para a caixa (30 s)

```cmd
pc enviar
```

Se for a primeira vez com rosto nesta caixa (ou se der erro de modelo depois):

```cmd
pc modelos
```

> Deu *Connection timed out*? É a rede acordando. **Repita o comando.**
> Deu *Connection closed by 192.168.50.10*? É **senha errada** três vezes,
> não rede. Chame de novo e digite com calma.

## 3. Entrar na caixa

```cmd
pc entrar
```

ou direto:

```cmd
ssh grupo11@192.168.50.10
```

- **Usuário:** `grupo11`
- **Senha:** a que o professor passou (se ele trocou depois do nosso pedido,
  é a nova). A senha não aparece enquanto você digita: é normal.
- Na primeira vez ele pergunta *"Are you sure you want to continue
  connecting"*: escreva `yes`.

Já dentro da caixa (o prompt muda para `grupo11@...`):

```bash
cd ~/auditix
P=/opt/eduvision/venv/bin/python
export PYTHONPATH=$HOME/pylibs
```

> Toda sessão nova de SSH perde o `P` e o `PYTHONPATH`. Se aparecer
> `No module named numpy` ou `cv2`, você esqueceu essas duas linhas (ou usou
> `python3` em vez de `$P`).

## 4. Na caixa: desligar a sala e configurar a arena (3 min)

**Parar o serviço da sala** (senão a porta 8080 e a câmera ficam ocupadas):

```bash
bash aibox/servico.sh estado
bash aibox/servico.sh parar
```

**Ver o `.env` sem mostrar a senha:**

```bash
grep -v PW .env
```

**Pôr as câmeras da arena no `.env`.** Hoje, com as Intelbras do laboratório,
no **fluxo principal** (`subtype=0`, 1920x1080; o `subtype=1` é 640x360 e o
rosto some):

```bash
sed -i '/^CAMERA_ARENA/d' .env
echo 'CAMERA_ARENA=rtsp://192.168.50.108:554/cam/realmonitor?channel=1&subtype=0' >> .env
echo 'CAMERA_ARENA2=rtsp://192.168.50.109:554/cam/realmonitor?channel=1&subtype=0' >> .env
grep CAMERA_ARENA .env
```

> **Aspas simples sempre**, e **nunca** `sed` para escrever endereço: o `&`
> do endereço embaralha o `.env` (armadilha 4). Usuário e senha da câmera
> continuam vindo do `CAM_USER` / `CAM_PW` que já estão lá.

Se quiser testar com uma câmera só, apague a linha `CAMERA_ARENA2`:
`sed -i '/^CAMERA_ARENA2/d' .env`

## 5. Cadastrar os autorizados (a galeria)

A galeria é o arquivo `~/auditix/arena/galeria.json`, só com os autorizados
da prova. Dois caminhos; o melhor é **fazer os dois** (fotos + passada pela
câmera), porque a câmera da sala vê o rosto de cima e as fotos não.

### 5A. Pelas fotos (no PC)

No PC, uma pasta por pessoa, com o nome completo:

```
fotos-cadastro\
  Enzo Renato Cunha\    frente.jpg  esquerda.jpg  direita.jpg  ...
  Matheus Martins Porto\ ...
```

```cmd
python aibox\cadastrar_fotos.py fotos-cadastro --conferir
python aibox\cadastrar_fotos.py fotos-cadastro --galeria arena\galeria.json
pc galeria
```

O `--conferir` só olha e diz quais fotos não servem (dois rostos, rosto
pequeno, torto, HEIC do iPhone). Precisa de 3 a 12 fotos boas por pessoa. O
`pc galeria` copia para a caixa e lista quem ficou lá.

### 5B. Pela câmera (na caixa)

Cada autorizado, **sozinho na frente da câmera**, a uns 1 a 2 m, mexendo a
cabeça devagar (6 amostras, uns 10 s):

```bash
$P aibox/cadastrar.py --nome "Enzo Renato Cunha" --galeria arena/galeria.json --acrescentar
```

- `--acrescentar` **junta** com as fotos. Sem ele, substitui.
- Ele usa a `CAMERA_CADASTRO` do `.env` (a `.109`, na altura do rosto). Para
  usar a da sala: acrescente `--camera 'rtsp://192.168.50.108:554/cam/realmonitor?channel=1&subtype=0'`.
- **O nome tem de ser escrito igual** ao das fotos, senão vira outra pessoa.

**Conferir quem está na galeria:**

```bash
$P aibox/galeria.py
```

Errou alguém? `$P aibox/galeria.py remover "Nome Errado"`.

## 6. Calibrar (o passo mais importante, 10 min)

```bash
bash aibox/arena.sh --calibrar
```

No PC, abra no Chrome: **`http://192.168.50.10:8080`** (com `http://` na
frente). Aparece a imagem com as caixas de rosto e o placar.

Com `--calibrar`, o terminal imprime a nota de cada leitura:

```
   c1-3 leitura 4: Enzo Renato Cunha 0.52, Matheus Martins Porto 0.11
```

Faça assim, **uma pessoa de cada vez**, andando pela área onde a prova vai
acontecer (perto, no meio, longe):

1. cada **autorizado** entra, olha para a câmera, anda um pouco, sai
2. cada **colega de outro grupo** faz o mesmo

**Anote numa folha:**

| quem | nota mais baixa | nota típica | virou o quê na tela |
|---|---|---|---|
| autorizado 1 | | | |
| autorizado 2 | | | |
| autorizado 3 | | | |
| desconhecido 1 (nota do 1º nome) | | | |
| desconhecido 2 (nota do 1º nome) | | | |

Anote também **até que distância o rosto é lido**. Se a caixa ficar em
"analisando (rosto pequeno)", a pessoa está longe demais: anote a distância.

`Ctrl+C` encerra e mostra o RESULTADO.

### Ajustar o limiar com o que você anotou

- `ARENA_LIMIAR` (padrão 0,36): **abaixo** da nota típica dos autorizados
- `ARENA_LIMIAR_BAIXO` (padrão 0,26): **acima** da nota típica dos
  desconhecidos
- o LIMIAR tem que ficar maior que o LIMIAR_BAIXO

Exemplo: autorizados dando 0,40 a 0,60 e desconhecidos dando 0,05 a 0,20 →
LIMIAR 0,33 e LIMIAR_BAIXO 0,24.

```bash
sed -i '/^ARENA_LIMIAR/d' .env
echo 'ARENA_LIMIAR=0.33' >> .env
echo 'ARENA_LIMIAR_BAIXO=0.24' >> .env
```

Rode de novo e confira que a primeira linha mostra o limiar novo:
`[arena] limiar 0.33 / 0.24`.

> Se autorizado e desconhecido dão notas **misturadas** (por exemplo, os dois
> perto de 0,25), o problema é pixel, não limiar: a pessoa está longe demais
> ou a câmera está no `subtype=1`. Aproxime e me mande os números.

## 7. Ensaio cronometrado, igual à prova (3 vezes)

A prova tem **5 minutos com o setup dentro**. Simule do zero:

1. feche tudo (`Ctrl+C`, `exit`)
2. **dispare o cronômetro**
3. `pc entrar` (ou `ssh grupo11@192.168.50.10`)
4. `cd ~/auditix && bash aibox/arena.sh`
5. abra `http://192.168.50.10:8080` no PC
6. entram os autorizados e os 2 desconhecidos, **em ordem diferente a cada
   vez**, cruzando uns pelos outros
7. quando o placar estiver certo, `Ctrl+C` e **pare o cronômetro**

Anote em cada rodada:

- tempo do setup (do cronômetro até a imagem aparecer)
- autorizados X de N
- alertas de desconhecido (tem que dar 2, nem mais nem menos)
- `tempo medio por quadro` (ms) e os quadros por segundo de cada câmera

Tire **foto do bloco "RESULTADO DA ARENA" no terminal** (sem rosto de
ninguém): é o slide de métricas que a banca pediu.

## 8. Antes de ir embora

```bash
$P aibox/galeria.py                 # a galeria certa está lá
grep -E 'CAMERA_ARENA|ARENA_' .env  # câmeras e limiares anotados
bash aibox/servico.sh remover       # nada sobe sozinho quando a caixa religar
```

**Por que remover o serviço:** no evento a caixa vai ser religada em outra
rede, e o serviço da sala subiria sozinho tentando a câmera do laboratório e
ocupando a porta 8080 bem na hora da prova. Se precisar dele de novo:
`bash aibox/servico.sh instalar`.

**Perguntar ao professor, pessoalmente:**

1. A caixa da arena é ESTA, com o usuário `grupo11` e os nossos arquivos?
   Qual vai ser o IP dela no evento?
2. As câmeras de 4 MP: marca, **H.264 ou H.265**, caminho RTSP do fluxo
   principal, usuário e senha?
3. São 3 ou 4 autorizados?
4. A que distância e altura as pessoas vão ficar da câmera?
5. Dá para testar com as câmeras novas antes de quarta à noite?

## No dia (sábado), só isto

```bash
ssh grupo11@IP_DA_CAIXA
cd ~/auditix
# se as câmeras forem outras: trocar CAMERA_ARENA (passo 4)
# se forem H.265: echo 'CAM_CODEC=h265' >> .env
bash aibox/arena.sh
```

No notebook: `http://IP_DA_CAIXA:8080`. No fim: `Ctrl+C` e mostrar o
RESULTADO. **Depois do evento:** `rm -r ~/auditix/arena` (a galeria tem os
números do rosto do grupo).

---

## Se alguma coisa der errado

| o que aparece | o que é | o que fazer |
|---|---|---|
| *Connection timed out* | rede acordando | repetir o comando |
| *Connection closed by ... port 22* | senha errada 3 vezes | `ssh` de novo, com calma |
| *Destination host unreachable* | PC fora do IP fixo, ou rede acordando | `pc rede`, e repetir |
| *$'\r': command not found* | fim de linha do Windows | `sed -i 's/\r$//' aibox/*.sh aibox/*.py` |
| *No module named ...* | sem o `$P` ou o `PYTHONPATH` | as duas linhas do passo 3 |
| *a porta 8080 está ocupada* | serviço da sala rodando | `bash aibox/servico.sh parar` |
| *401 Unauthorized* | caminho RTSP ou senha errados | conferir o endereço; NÃO ficar tentando |
| *403 Forbidden* | câmera bloqueou o IP | `Ctrl+C` e **não tentar nada por 30 min** |
| câmera "sem imagem" o tempo todo | endereço errado, ou câmera H.265 | conferir o endereço; `echo 'CAM_CODEC=h265' >> .env` |
| *a galeria está vazia* | faltou o passo 5 | `pc galeria` ou `cadastrar.py --galeria` |
| Chrome *ERR_SSL_PROTOCOL_ERROR* | faltou o `http://` | `http://192.168.50.10:8080` |
| "analisando (rosto pequeno)" | longe demais da câmera | aproximar; anotar a distância |
| "analisando (de lado)" | não está olhando para a câmera | olhar para a câmera |

**Câmera: um teste de cada vez, nunca em laço.** Tentativa seguida é o que
faz a Intelbras bloquear o IP por meia hora.

## O que me mandar depois

A tabela de notas do passo 6, a distância máxima que leu, os três resultados
do passo 7 (setup, X de N, alertas, ms) e qualquer mensagem de erro inteira.
