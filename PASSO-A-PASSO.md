# Noite na AIBOX — o que fazer, na ordem

Este arquivo existe para ser lido **no PC do laboratório, sem internet**. Tudo
aqui é um comando curto: os longos viraram script.

Abra um `cmd` **como administrador** (Menu Iniciar → digite `cmd` → botão
direito → *Executar como administrador*). Sem isso o `netsh` falha com uma
mensagem que não diz que o problema é esse.

---

## 1. Pegar o código novo  (2 min)

```cmd
cd C:\caminho\do\Next
pc puxar
```

Ele tira o PC do IP fixo, baixa o código, e devolve o IP fixo. É a dança
inteira num comando.

> Se o `git pull` falhar, a rede não acordou ainda. Rode
> `git pull origin claude/entender-projeto-0tgk9u` de novo e siga.

## 2. Mandar para a caixa  (30 s)

```cmd
pc enviar
```

Copia os arquivos **e já apaga o fim de linha do Windows do lado de lá**. Era
isso que fazia o bash responder `$'\r': command not found` — uma mensagem que
não parece nem de longe com a causa.

## 3. Subir o servidor  (deixe esta janela aberta)

Em **outra** janela de `cmd`:

```cmd
pc servidor
```

`HOST=0.0.0.0` é o que deixa a caixa alcançar o PC. Sem isso o servidor só
responde aqui dentro e **o painel nunca enche**.

## 4. Entrar na caixa e rodar

```cmd
pc entrar
```

E, lá dentro:

```bash
bash aibox/ir.sh
```

Esse script faz o resto sozinho: acha o Python certo, limpa o que precisa,
**confere se o banco do PC está alcançável** e só então roda. Se o caminho até
o banco estiver quebrado ele avisa antes, em vez de você descobrir pelo painel
vazio meia hora depois.

Para uma rodada curta de teste:

```bash
bash aibox/ir.sh --segundos 30
```

## 4b. Reconhecimento facial (opcional)

**Uma vez só**, no PC, mande os modelos de rosto para a caixa (39 MB):

```cmd
pc modelos
```

Ele confere o tamanho no fim: o SFace tem que aparecer com ~38 MB. Se
aparecer com poucos bytes, o arquivo não veio inteiro.

Depois, cadastre cada um pela câmera da caixa — são 6 amostras, mexendo a
cabeça:

```bash
$P aibox/cadastrar.py --nome "Enzo Renato"
```

E rode com o reconhecimento ligado:

```bash
bash aibox/ir.sh --rosto
```

Aí a etiqueta na imagem ao vivo deixa de ser `#7` e passa a ser o nome, e o
alerta no painel também.

> **Vem desligado de propósito.** Rosto custa CPU, e a detecção de queda — que é
> o que o desafio pede — não pode piorar por causa de um extra. Se os quadros
> por segundo caírem demais, é só rodar sem `--rosto`.

> O cadastro da caixa é **separado** do cadastro do navegador: são dois motores
> de rosto diferentes, e os números de um não servem para o outro. Cadastre nos
> dois se quiser ser reconhecido nas duas telas.

## 5. Ver

| o quê | onde |
|---|---|
| imagem ao vivo | `http://192.168.50.10:8080` |
| painel de eventos | `http://127.0.0.1:8000/painel` |
| cadastrar rosto | `http://127.0.0.1:8000/cadastro` |
| conferir a cadeia | `http://127.0.0.1:8000/cadeia` |

**Com `http://` na frente.** Sem isso o Chrome tenta HTTPS e dá
`ERR_SSL_PROTOCOL_ERROR`.

Na tela ao vivo, olhe os dois números do canto: **alertas enviados** e **não
chegaram**. O segundo em vermelho é o banco não recebendo.

---

## Se alguma coisa der errado

**Primeiro, sempre:**

```bash
$P aibox/conferir.py
```

Ele diz em português onde quebrou. As causas, em ordem de frequência:

1. o servidor no PC subiu **sem** `HOST=0.0.0.0` → use `pc servidor`
2. o firewall do Windows barrando a porta 8000
3. o PC voltou para DHCP e perdeu o `192.168.50.72` → `pc rede`
4. `SERVIDOR` faltando no `.env` da caixa → sem ele a caixa manda os alertas
   para **ela mesma**, e eles morrem ali

**Se ele disser que está gravando em SQLite** e não no Postgres: não é erro, é
o servidor caindo para o banco local sozinho quando a AWS não responde — de
propósito, para a apresentação não depender da nuvem. Mas os dados **não estão
no RDS**. O motivo está impresso na janela do servidor.

---

## Como me mandar o que aconteceu

Você vai estar sem internet, então guarde em arquivo em vez de fotografar:

**Na caixa:**

```bash
$P aibox/conferir.py > /tmp/saida.txt 2>&1
bash aibox/ir.sh --segundos 30 > /tmp/rodada.txt 2>&1
```

**No PC**, traga os dois:

```cmd
scp grupo11@192.168.50.10:/tmp/*.txt .
```

Quando voltar para o DHCP (`pc puxar`), é só colar o conteúdo aqui. Muito
melhor que foto de tela: eu leio o número exato.
