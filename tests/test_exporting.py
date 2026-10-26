from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from paper_scanner.exporting import ExportOptions, encode_image, save_unique, target_size


def test_requested_pixel_sizes_and_aspect_ratio():
    assert target_size((4000, 3000), ExportOptions()) == (4000, 3000)
    assert target_size((4000, 3000), ExportOptions('percent', 70)) == (2800, 2100)
    assert target_size((4000, 3000), ExportOptions('percent', 50)) == (2000, 1500)
    assert target_size((4000, 3000), ExportOptions('custom', width=1000)) == (1000, 750)
    assert target_size((4000, 3000), ExportOptions('custom', width=1000, height=600)) == (800, 600)
    assert target_size((4000, 3000), ExportOptions('custom', height=900)) == (1200, 900)


def noise_image():
    return Image.fromarray(np.random.default_rng(17).integers(0, 256, (900, 1200, 3), dtype=np.uint8))


@pytest.mark.parametrize('format_name', ['JPEG', 'PNG'])
@pytest.mark.parametrize('max_mb', [0.03, 0.2, 2.0])
def test_file_size_is_a_hard_limit_and_decodable(format_name, max_mb):
    result = encode_image(noise_image(), ExportOptions(format=format_name, max_mb=max_mb))
    assert len(result.data) <= int(max_mb * 1_000_000)
    image = Image.open(BytesIO(result.data))
    image.load()
    assert image.size == (result.width, result.height)
    assert image.width / image.height == pytest.approx(4 / 3, abs=0.02)


def test_unlimited_original_does_not_resize():
    result = encode_image(noise_image(), ExportOptions())
    assert (result.width, result.height) == (1200, 900)
    assert not result.resized_for_limit


def test_save_never_overwrites_source_or_prior_result(tmp_path):
    source = tmp_path / '文档.jpg'
    source.write_bytes(b'original')
    existing = tmp_path / '文档_扫描.jpg'
    existing.write_bytes(b'existing')
    encoded = encode_image(Image.new('RGB', (32, 32), 'white'), ExportOptions())
    first = save_unique(encoded, tmp_path, '文档', 'JPEG')
    second = save_unique(encoded, tmp_path, '文档', 'JPEG')
    assert source.read_bytes() == b'original'
    assert existing.read_bytes() == b'existing'
    assert first != second
    assert first.read_bytes() == encoded.data
    assert second.read_bytes() == encoded.data
    assert not list(tmp_path.glob('.scan-*'))


@pytest.mark.parametrize('options', [ExportOptions('custom'), ExportOptions('percent', 0), ExportOptions(max_mb=-2), ExportOptions(max_mb=float('nan'))])
def test_invalid_options_fail_before_encoding(options):
    with pytest.raises(ValueError):
        encode_image(Image.new('RGB', (32, 32)), options)
