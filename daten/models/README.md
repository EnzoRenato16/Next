# Modelos (OpenCV Zoo)

O reconhecimento facial usa dois modelos ONNX pequenos, que rodam em **CPU/ARM64**
(o AIBOX não tem GPU CUDA). Baixe **uma vez** (no notebook, com internet) e mande
pro AIBOX junto com o projeto — assim você **não baixa nada durante a aula**.

Coloque os dois arquivos **nesta pasta** (`models/`), com estes nomes exatos:

| Arquivo | O que é | Tamanho |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | Detector de rosto (YuNet) | ~230 KB |
| `face_recognition_sface_2021dec.onnx` | Embedding de rosto (SFace) | ~37 MB |

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
