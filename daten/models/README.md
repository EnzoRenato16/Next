# Modelos (OpenCV Zoo)

O reconhecimento facial usa dois modelos ONNX pequenos, que rodam em **CPU/ARM64**
(o AIBOX não tem GPU CUDA). Baixe **uma vez** (no notebook, com internet) e mande
pro AIBOX junto com o projeto — assim você **não baixa nada durante a aula**.

Coloque os dois arquivos **nesta pasta** (`models/`), com estes nomes exatos:

| Arquivo | O que é | Tamanho |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | Detector de rosto (YuNet) | ~230 KB |
| `face_recognition_sface_2021dec.onnx` | Embedding de rosto (SFace) | ~37 MB |
| `objeto_suspeito_yolov8.onnx` | Objeto suspeito, opcional (YOLOv8) | ~12 MB |

## Onde baixar
Repositório oficial **opencv/opencv_zoo** (GitHub):

- `models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
- `models/face_recognition_sface/face_recognition_sface_2021dec.onnx`

> Se os nomes do arquivo baixado forem diferentes, ou renomeie para os nomes
> acima, ou ajuste `YUNET_MODEL` / `SFACE_MODEL` em `app/config.py`.

## Verificação rápida (no venv, com opencv-contrib instalado)
```python
import cv2
cv2.FaceDetectorYN.create("models/face_detection_yunet_2023mar.onnx", "", (320,320))
cv2.FaceRecognizerSF.create("models/face_recognition_sface_2021dec.onnx", "")
print("modelos OK")
```


---

## Objeto suspeito (opcional)

Detecta objeto que **parece** arma de fogo ou lâmina. É a única camada
desligada por padrão — ligar é decisão de quem instala:

```bash
export ARMAS_ATIVO=1
```

### Baixar

```bash
curl -L -o models/objeto_suspeito_yolov8.onnx \
  https://huggingface.co/Hadi959/weapon-detection-yolov8/resolve/main/best.onnx
```

YOLOv8, entrada 640×640, duas classes: `pistol` e `knife`. A saída vem crua
(sem NMS embutida) — a decodificação e a supressão estão em `app/armas.py`,
escritas à mão para não arrastar a dependência do Ultralytics para o projeto.

### Licença — leia antes de usar

O modelo foi exportado pelo Ultralytics e carrega **AGPL-3.0** no metadata.
AGPL é viral: se vocês distribuírem ou servirem o sistema com este modelo
dentro, o código de vocês precisa ser aberto sob a mesma licença. Para um
trabalho acadêmico com repositório público, tudo bem. Para virar produto
fechado, **não serve** — aí é treinar um modelo próprio, ou usar um com
licença permissiva.

O autor do modelo não declarou licença própria na página do Hugging Face.
Cite a fonte se usar.

### Por que os limiares são altos

| Ajuste | Padrão | Para quê |
|---|---|---|
| `ARMA_CONF` | 0.60 | confiança mínima. Baixar isso enche a escola de alarme falso |
| `ARMA_HITS` | 4 | leituras seguidas antes de virar evento — sombra pisca, objeto fica |
| `ARMA_SILENCIO` | 30s | um objeto parado na mesa não gera um evento por quadro |
| `ARMA_CADA` | 5 | roda 1x a cada N frames; é a camada mais cara |

Isto não é excesso de zelo. Sistemas em produção já confundiram uma clarineta
e um saco de salgadinho com arma, e em 2023 a **sombra do braço** de um aluno
colocou uma escola no Texas em *lockdown*. Faca é o caso que funciona pior — e
é justamente o mais pedido numa escola.

### Regras que o código impõe

- O evento é gravado como **`objeto_suspeito`**, nunca "arma detectada".
- O alerta **nunca leva `aluno_id`**. Amarrar um alerta de arma a um nome, com
  a taxa de erro que esta tecnologia tem, é dano que não se desfaz.
- Nada dispara sozinho: o evento acorda uma pessoa, e ela decide.

### Enviar para o painel

O EduVision grava no SQLite dele. Para o evento também entrar na cadeia de
hash e aparecer no `/painel`:

```bash
export AUDITIX_URL='http://<ip-do-servidor>:8000'
```

Se a rede cair, o evento continua gravado localmente — o envio falha em
silêncio e avisa no log.
