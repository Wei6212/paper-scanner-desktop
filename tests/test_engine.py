import numpy as np
from PIL import Image
import pytest

from paper_scanner.engine import read_image, validate_quad, warp_document


def test_perspective_crop_keeps_colors_and_content():
    rgb = np.full((200, 300, 3), 80, dtype=np.uint8)
    rgb[30:170, 40:260] = [250, 250, 250]
    rgb[80:120, 100:200] = [220, 30, 20]
    corners = np.float32([[40 / 299, 30 / 199], [259 / 299, 30 / 199], [259 / 299, 169 / 199], [40 / 299, 169 / 199]])
    cropped = warp_document(rgb, corners)
    assert cropped.shape == (140, 220, 3)
    assert np.allclose(cropped[70, 110], [220, 30, 20], atol=3)
    assert np.mean(cropped[:10]) > 240


def test_tiny_or_nonfinite_quad_rejected():
    with pytest.raises(ValueError):
        validate_quad(np.zeros((4, 2)), 100, 100)
    with pytest.raises(ValueError):
        validate_quad(np.full((4, 2), np.nan), 100, 100)


def test_exif_orientation_and_transparency(tmp_path):
    path = tmp_path / '透明.png'
    Image.new('RGBA', (30, 20), (0, 0, 0, 0)).save(path)
    image = read_image(path, 90)
    assert image.size == (20, 30)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    jpeg = tmp_path / '方向.jpg'
    source = Image.new('RGB', (30, 20), 'red')
    exif = source.getexif()
    exif[274] = 6
    source.save(jpeg, exif=exif)
    assert read_image(jpeg).size == (20, 30)


def test_normalized_identity_grid_keeps_image():
    from paper_scanner.engine import Scanner
    rgb = np.zeros((120, 180, 3), dtype=np.uint8)
    rgb[..., 0] = np.arange(180, dtype=np.uint8)[None, :]
    rgb[..., 1] = np.arange(120, dtype=np.uint8)[:, None]
    x, y = np.meshgrid(np.linspace(-1, 1, 385, dtype=np.float32), np.linspace(-1, 1, 385, dtype=np.float32))
    out = Scanner._remap_normalized(rgb, np.stack((x, y), axis=-1))
    assert out.shape == rgb.shape
    assert np.max(np.abs(out.astype(int) - rgb.astype(int))) <= 1


def test_real_models_preserve_color_and_whiten_sample():
    from pathlib import Path
    from paper_scanner.engine import Scanner, ScanOptions
    root = Path(__file__).resolve().parents[1]
    result = Scanner().process(root / 'samples/手绘文档原图.jpg', ScanOptions())
    output = np.asarray(result.image)
    assert result.image.width > 1500
    assert result.image.height > 1000
    assert np.mean(np.min(output, axis=2) > 240) > 0.55
    assert np.count_nonzero((output[..., 0] > 180) & (output[..., 1] < 100)) > 1000
    assert result.warning == ''
