"""真实模型推理检查，保存阶段输出供人工核对。"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from paper_scanner.engine import Model, Scanner, ScanOptions, read_image, resource_dir
from paper_scanner.exporting import ExportOptions, encode_image, save_unique

root = Path(__file__).resolve().parents[1]
(root / 'artifacts').mkdir(exist_ok=True)
image = np.asarray(read_image(root / 'samples/手绘文档原图.jpg'))
for name, input_name, side in [('document_detect', 'hed_input', 384), ('document_enhance', 'img_input', 512)]:
    started = time.monotonic()
    model = Model(resource_dir() / f'{name}.mnn', input_name, 'img_output')
    output = model.run(cv2.resize(image, (side, side)))
    print(name, output.shape, float(output.min()), float(output.max()), 'seconds', time.monotonic() - started, flush=True)
    if name == 'document_detect':
        for c in range(output.shape[-1]):
            heat = output[..., c]
            if heat.max() <= 1.5:
                heat = heat * 255
            Image.fromarray(np.clip(heat, 0, 255).astype('uint8')).save(root / f'artifacts/detection-{c}.png')
    else:
        Image.fromarray(np.clip(output, 0, 255).astype('uint8')).save(root / 'artifacts/background-estimate.jpg')
scanner = Scanner()
result = scanner.process(root / 'samples/手绘文档原图.jpg', ScanOptions())
result.image.save(root / 'artifacts/扫描效果.jpg', quality=95)
print('corners', result.corners.tolist(), result.warning, flush=True)
print('result', result.image.size, result.seconds, flush=True)
for mode, value in [('original', 100), ('percent', 70), ('percent', 50)]:
    encoded = encode_image(result.image, ExportOptions(mode, value, max_mb=2))
    path = save_unique(encoded, root / 'artifacts/exports', f'{value}pct', 'JPEG')
    print(path.name, encoded.width, encoded.height, len(encoded.data), flush=True)
