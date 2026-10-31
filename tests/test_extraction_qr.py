import cv2
import numpy as np

from modules.extraction.qr import parse, read_qr

PAYLOAD = ("Application No. : TN-6202605053287\nApplicant Name : Satyajit\n"
           "Service Applied : OBC Certificate\nAddress :  TAMBARAM Village / Town, Chengalpattu District.")


def certificate_page(payload: str | None, qr_px: int = 260) -> np.ndarray:
    page = np.full((2200, 1700, 3), 255, np.uint8)
    cv2.putText(page, "Other Backward Class Certificate", (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 4)
    if payload:
        qr = cv2.QRCodeEncoder.create().encode(payload)
        qr = cv2.resize(qr, (qr_px, qr_px), interpolation=cv2.INTER_NEAREST)
        page[1800:1800 + qr_px, 150:150 + qr_px] = cv2.cvtColor(qr, cv2.COLOR_GRAY2RGB)
    return page


def test_parse_tn_e_district_payload():
    assert parse(PAYLOAD) == {"certificate_number": "TN-6202605053287", "name": "Satyajit", "service": "OBC Certificate"}


def test_reads_qr_from_certificate_page():
    r = read_qr([certificate_page(PAYLOAD)])
    assert r.status == "decoded" and r.values["certificate_number"] == "TN-6202605053287"


def test_page_without_qr_is_absent():
    assert read_qr([certificate_page(None)]).status == "absent"


def test_qr_payload_aadhaar_is_masked():
    assert parse("Applicant Name : Satyajit 1234 5678 9012")["name"] == "Satyajit XXXX XXXX 9012"
