import cv2
import numpy as np

from modules.extraction import preprocess


def _page(angle: float) -> np.ndarray:
    img = np.full((900, 1200, 3), 255, np.uint8)
    for i, line in enumerate(["GOVERNMENT OF TAMIL NADU", "INCOME CERTIFICATE", "This is to certify that",
                              "S SATYAJIT son of K SUBRAMANIAN", "Annual income Rs 2,50,000", "Chennai district"]):
        cv2.putText(img, line, (120, 200 + 90 * i), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)
    m = cv2.getRotationMatrix2D((600, 450), angle, 1.0)
    return cv2.warpAffine(img, m, (1200, 900), borderValue=(255, 255, 255))


def test_deskew_brings_7deg_within_1deg():
    out, measured = preprocess.deskew(_page(7))
    assert abs(abs(measured) - 7) < 1.0
    assert abs(preprocess.measure_skew(out)) < 1.0


def test_deskew_leaves_straight_page():
    img = _page(0)
    out, measured = preprocess.deskew(img)
    assert abs(measured) <= 0.5 and out is img


def test_quality_flags_dark_and_blurry():
    q = preprocess.quality(_page(0))
    assert not q.too_dark and not q.too_blurry
    dark = (_page(0) * 0.15).astype(np.uint8)
    assert preprocess.quality(dark).too_dark
    blurry = cv2.GaussianBlur(_page(0), (61, 61), 0)
    assert preprocess.quality(blurry).too_blurry


def test_find_document_crops_paper_on_dark_background():
    bg = np.full((1600, 1200, 3), 30, np.uint8)
    paper = np.full((1000, 700, 3), 245, np.uint8)
    bg[300:1300, 250:950] = paper
    out, found = preprocess.find_document(bg)
    assert found
    assert abs(out.shape[0] - 1000) < 40 and abs(out.shape[1] - 700) < 40
