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


@pytest.mark.parametrize('max_mb', [None, 0.01])
def test_binary_png_stays_binary_after_scaling_and_size_limit(max_mb):
    pixels = np.random.default_rng(3).integers(0, 2, (900, 1200), dtype=np.uint8) * 255
    image = Image.fromarray(pixels).convert('1', dither=Image.Dither.NONE)
    encoded = encode_image(image, ExportOptions(mode='percent', percent=75, format='PNG', max_mb=max_mb))
    with Image.open(BytesIO(encoded.data)) as output:
        assert output.mode == '1'
        assert set(output.convert('L').tobytes()) == {0, 255}
    assert encoded.resized_for_limit == (max_mb is not None)
    if max_mb is not None:
        assert len(encoded.data) <= 10_000


def test_binary_image_can_still_export_as_jpeg():
    image = Image.new('1', (20, 20), 1)
    image.putpixel((10, 10), 0)
    encoded = encode_image(image, ExportOptions())
    with Image.open(BytesIO(encoded.data)) as output:
        assert output.format == 'JPEG'
        assert output.size == image.size


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


def test_watermark_default_gray_translucent_and_source_unchanged():
    image = Image.new('RGB', (640, 480), 'white')
    original = image.tobytes()
    encoded = encode_image(image, ExportOptions(format='PNG', watermark_text='仅供测试专用'))
    pixels = np.asarray(Image.open(BytesIO(encoded.data)))
    assert image.tobytes() == original
    assert pixels.min() >= 191
    assert pixels.min() < 230
    assert np.array_equal(pixels[:, :, 0], pixels[:, :, 1])
    assert np.array_equal(pixels[:, :, 1], pixels[:, :, 2])
    assert np.any(pixels[180:300, 200:440] < 230)
    assert np.any(pixels[:140] < 230) or np.any(pixels[340:] < 230)


def test_watermark_custom_color_and_size_on_binary_output():
    image = Image.new('1', (640, 480), 1)
    counts = []
    for size in (20, 60):
        encoded = encode_image(image, ExportOptions(format='PNG', watermark_text='测试',
                                                   watermark_color='#ff0000', watermark_size=size))
        output = Image.open(BytesIO(encoded.data))
        assert output.mode == 'RGB'
        pixels = np.asarray(output)
        assert pixels[:, :, 0].min() == 255
        assert pixels[:, :, 1].min() >= 127
        counts.append(np.count_nonzero(pixels[160:320, 240:400, 1] < 230))
    assert counts[1] > counts[0]
    assert image.mode == '1' and set(image.convert('L').tobytes()) == {255}


@pytest.mark.parametrize('format_name', ['PNG', 'JPEG'])
def test_watermark_respects_resize_and_hard_file_limit(format_name):
    encoded = encode_image(noise_image(), ExportOptions(mode='percent', percent=50, format=format_name,
                                                       max_mb=0.03, watermark_text='仅供测试专用'))
    assert len(encoded.data) <= 30_000
    with Image.open(BytesIO(encoded.data)) as output:
        assert output.size == (encoded.width, encoded.height)
        assert output.width <= 600 and output.height <= 450


@pytest.mark.parametrize('size', [(1, 1), (20, 80), (640, 480)])
def test_long_watermark_on_small_images(size):
    encoded = encode_image(Image.new('RGB', size, 'white'),
                           ExportOptions(format='PNG', watermark_text='测试用途' * 25, watermark_size=300))
    with Image.open(BytesIO(encoded.data)) as output:
        assert output.size == size


@pytest.mark.parametrize('options', [
    ExportOptions(watermark_text='字' * 101), ExportOptions(watermark_text='两行\n文字'),
    ExportOptions(watermark_color='red'), ExportOptions(watermark_color='#12345g'),
    ExportOptions(watermark_size=7), ExportOptions(watermark_size=301), ExportOptions(watermark_size=36.5),
])
def test_invalid_watermark_options(options):
    with pytest.raises(ValueError):
        encode_image(Image.new('RGB', (32, 32)), options)
