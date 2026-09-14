# Alerta por e-mail (AWS Lambda + SES)

Quando a Sala detecta uma queda, o servidor manda o evento para uma função na
AWS, que escreve o e-mail e envia. Leva poucos segundos.

**Por que não mandar o e-mail direto do servidor da escola:** a máquina fica
atrás do roteador, pode estar desligada, e a senha do e-mail ficaria guardada
nela — na mão de quem sentar naquele computador. Na Lambda a credencial é do
papel da função, não existe como arquivo, e não sai de lá.

O evento é **gravado na trilha de auditoria antes** de a notificação ser
tentada. Se a AWS estiver fora do ar, o registro continua existindo: o histórico
nunca depende de o e-mail ter dado certo.

---

## 1. Verificar o e-mail no SES

O SES só envia de endereços verificados, e em conta nova só **para** endereços
verificados também.

1. Console da AWS → busque **SES** → escolha a região **São Paulo
   (sa-east-1)** no canto superior direito
2. Menu lateral → **Identities** → **Create identity**
3. **Email address** → digite o e-mail que vai *enviar* → **Create**
4. Abra a caixa desse e-mail e clique no link de confirmação
5. **Repita para cada e-mail que vai RECEBER** (enquanto a conta estiver em
   sandbox, só dá para mandar para endereços verificados)

> Para sair do sandbox e enviar para qualquer endereço, é preciso pedir
> *production access* à AWS. Para a apresentação, o sandbox basta: verifique o
> e-mail de vocês.

## 2. Criar a função

1. Console → **Lambda** → **Create function**
2. **Author from scratch**
   - Function name: `auditix-alerta`
   - Runtime: **Python 3.12**
   - **Create function**
3. Na aba **Code**, apague o conteúdo do `lambda_function.py` e cole o de
   `aws/lambda_alerta.py` deste repositório
4. **Deploy**
5. Aba **Configuration** → **General configuration** → **Edit** → Handler:
   `lambda_function.handler` → **Save**

## 3. Dar permissão de enviar e-mail

1. **Configuration** → **Permissions** → clique no nome do **Role**
2. Abre o IAM → **Add permissions** → **Attach policies**
3. Procure **AmazonSESFullAccess** → **Add permissions**

> Para valer, o certo é uma política só com `ses:SendEmail`. A completa serve
> para começar; trocar depois é um clique.

## 4. Configurar a função

**Configuration** → **Environment variables** → **Edit** → três variáveis:

| Key | Value |
|---|---|
| `REMETENTE` | o e-mail verificado que envia |
| `DESTINO` | quem recebe (vírgula separa vários) |
| `SEGREDO` | uma senha longa que você inventa agora |

Guarde o `SEGREDO`: ele vai no servidor da escola no passo 6.

## 5. Criar a URL da função

1. **Configuration** → **Function URL** → **Create function URL**
2. Auth type: **NONE**
3. **Save**
4. Copie a URL (algo como `https://abc123.lambda-url.sa-east-1.on.aws/`)

> **NONE não quer dizer aberto a todos** — quer dizer que a AWS não confere
> nada, e quem confere é a própria função, pelo `SEGREDO`. Sem esse segredo,
> qualquer um que descubra a URL dispara e-mails em nome da escola, e a conta é
> de vocês. É por isso que ele existe.

## 6. Ligar o servidor da escola nela

No `.env` ao lado do `servidor.py` (crie se não existir):

```
WEBHOOK_URL=https://abc123.lambda-url.sa-east-1.on.aws/
WEBHOOK_SEGREDO=a-mesma-senha-do-passo-4
ALERTA_TIPOS=graves
ALERTA_ESPERA=60
```

Reinicie o servidor. Pronto.

- `ALERTA_TIPOS=graves` manda só queda e afins. `todos` manda **tudo**,
  inclusive cada pessoa reconhecida — serve para testar e é insuportável em uso
  normal.
- `ALERTA_ESPERA=60` é o silêncio mínimo, em segundos, entre dois e-mails do
  mesmo tipo. Um alerta a cada poucos segundos é a forma mais rápida de a caixa
  de entrada virar lixo e ninguém mais ler nenhum.

## 7. Testar sem cair no chão

Com o servidor no ar:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/evento -H "Content-Type: application/json" -d "{\"aluno_id\":\"corpo-1\",\"tipo_evento\":\"queda\",\"localizacao\":\"sala-12\"}"
```

O e-mail deve chegar em segundos. Se não chegar:

| onde olhar | o que procura |
|---|---|
| janela do servidor | `webhook falhou` — a URL está errada ou fora do ar |
| Lambda → **Monitor** → **View CloudWatch logs** | `segredo não confere`, ou erro do SES |
| SES → **Identities** | o remetente e o destinatário estão verificados? |

## Conferir sem a AWS

`node testes/alerta.mjs` sobe um servidor no lugar da Lambda e confere o
caminho inteiro: a queda vira alerta, o evento comum não, o segredo vai junto,
e a espera segura a rajada. Roda em segundos e não gasta nada.

## O que isso custa

Praticamente nada nessa escala: a AWS dá 1 milhão de execuções de Lambda por
mês e 62 mil e-mails; vocês vão usar dezenas. Mas **a conta é da conta AWS de
quem criar** — por isso o segredo do passo 4 não é opcional.
