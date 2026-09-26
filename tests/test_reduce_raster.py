import io

import numpy as np
import pytest

from lineova.raster import bin_points, block_reduce, encode_png, normalize, shade
from lineova.reduce import is_sorted, m4


def test_m4_keeps_extremes_per_column(rng):
    n = 200_000
    x = np.linspace(0, 1, n)
    y = rng.standard_normal(n)
    y[12345] = 50.0
    y[99999] = -50.0
    rx, ry = m4(x, y, (0, 1), 300)
    assert len(rx) <= 4 * 300 + 2
    assert ry.max() == 50.0 and ry.min() == -50.0
    assert rx[0] == x[0] and rx[-1] == x[-1]


def test_m4_passthrough_small():
    x = np.arange(10.0)
    assert m4(x, x, (0, 9), 100)[0] is x


def test_is_sorted():
    assert is_sorted(np.arange(5.0)) and not is_sorted(np.array([1.0, 0.0]))


def test_bin_points_counts_everything_in_range(rng):
    x, y = rng.random(10_000), rng.random(10_000)
    g = bin_points(x, y, (0, 1), (0, 1), (20, 30))
    assert g.shape == (20, 30) and g.sum() == 10_000


def test_bin_points_ignores_nan_and_outside():
    x = np.array([0.5, np.nan, 2.0, 0.1])
    y = np.array([0.5, 0.5, 0.5, np.nan])
    assert bin_points(x, y, (0, 1), (0, 1), (4, 4)).sum() == 1


def test_bin_points_top_row_is_high_y():
    g = bin_points(np.array([0.5]), np.array([0.99]), (0, 1), (0, 1), (10, 10))
    assert g[0].sum() == 1


def test_bin_points_categories():
    g = bin_points(np.array([0.1, 0.9]), np.array([0.1, 0.9]), (0, 1), (0, 1), (2, 2),
                   categories=np.array([0, 1]), n_categories=2)
    assert g.shape == (2, 2, 2) and g[0].sum() == 1 and g[1].sum() == 1


def test_normalize_modes():
    c = np.array([[0, 1, 10, 100]])
    for how in ("linear", "log", "eq_hist"):
        t = normalize(c, how)
        assert t[0, 0] == 0 and t[0, 3] == 1 and np.all(np.diff(t[0]) >= 0)


def test_shade_rgba():
    img = shade(np.array([[0, 5], [1, 0]]), np.array([1.0, 0.0, 0.0]))
    assert img.shape == (2, 2, 4) and img[0, 0, 3] == 0 and img[0, 1, 0] == 255


def test_png_roundtrip():
    PIL = pytest.importorskip("PIL.Image")
    a = np.zeros((3, 5, 4), np.uint8)
    a[1, 2] = (10, 20, 30, 255)
    im = PIL.open(io.BytesIO(encode_png(a)))
    assert im.size == (5, 3) and im.getpixel((2, 1)) == (10, 20, 30, 255)


def test_block_reduce():
    a = np.arange(16.0).reshape(4, 4)
    b = block_reduce(a, 2, 2)
    assert b.shape == (2, 2) and b[0, 0] == np.mean([0, 1, 4, 5])
