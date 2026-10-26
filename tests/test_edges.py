import numpy as np

from paper_scanner.edges import fill_document_frame


def test_removes_background_without_resizing_or_changing_interior():
    original = np.full((260, 360, 3), [130, 120, 95], dtype=np.uint8)
    original[8:-8, 8:-8] = [175, 174, 170]
    original[30:80, 9:12] = 0
    original[100:140, 9:13] = [230, 25, 20]
    enhanced = original.copy()
    enhanced[8:-8, 8:-8] = 250
    enhanced[30:80, 9:12] = 0
    enhanced[100:140, 9:13] = [230, 25, 20]
    before = enhanced.copy()
    result = fill_document_frame(original, enhanced)
    assert result.shape == before.shape
    assert np.array_equal(result[30:80, 9:12], before[30:80, 9:12])
    assert np.array_equal(result[100:140, 9:13], before[100:140, 9:13])
    assert np.array_equal(result[20:-20, 20:-20], before[20:-20, 20:-20])
    perimeter = np.concatenate((result[:4].reshape(-1, 3), result[-4:].reshape(-1, 3), result[:, :4].reshape(-1, 3), result[:, -4:].reshape(-1, 3)))
    assert np.mean(np.min(perimeter, axis=1) == 255) > 0.98


def test_no_detected_boundary_keeps_full_bleed_color():
    original = np.full((200, 300, 3), [20, 90, 180], dtype=np.uint8)
    expected = original.copy()
    assert np.array_equal(fill_document_frame(original, original), expected)


def test_black_printed_frame_is_preserved():
    original = np.full((260, 360, 3), 175, dtype=np.uint8)
    original[:8] = original[-8:] = 0
    original[:, :8] = original[:, -8:] = 0
    expected = original.copy()
    result = fill_document_frame(original, original)
    black_pixels = np.all(expected == 0, axis=2)
    assert np.all(result[black_pixels] == 0)
    assert np.array_equal(result[20:-20, 20:-20], expected[20:-20, 20:-20])
