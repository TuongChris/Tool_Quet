# -*- coding: utf-8 -*-
"""Smoke Streamlit: màn hình tiến độ phải có số liệu THẬT khi job còn chạy.

Chạy chính ``app.py`` qua harness chính thức của Streamlit (AppTest), với một
audfprint giả nên không cần FFmpeg/audfprint thật và không đụng kho production.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP_PY = Path(__file__).resolve().parents[1] / "app.py"

AUDFPRINT_GIA = '''
import json, os, sys, time

listfile, db_file = sys.argv[1], sys.argv[2]
with open(listfile, encoding="utf-8") as fh:
    files = [d for d in fh.read().splitlines() if d.strip()]

for duong_dan in files:
    for su_kien, them in (
        ("clip_started", {"phase": "fingerprinting"}),
        ("clip_finished", {"status": "success", "elapsed_seconds": 0.3, "hash_count": 7}),
    ):
        print(
            "TIMCLIP_FINGERPRINT_EVENT "
            + json.dumps(
                {"event": su_kien, "file": duong_dan, "process_pid": os.getpid(), **them},
                ensure_ascii=False,
            ),
            flush=True,
        )
        time.sleep(0.45)

with open(db_file, "wb") as fh:
    fh.write(b"fake-database")
print("Saved fprints for %d files" % len(files), flush=True)
'''


def _van_ban(at) -> str:
    """Gom mọi text hiển thị trên trang để kiểm tra nội dung tiến độ."""
    phan = []
    for nhom in (at.markdown, at.info, at.caption, at.warning, at.error, at.code,
                 at.header, at.subheader):
        phan.extend(str(item.value) for item in nhom)
    phan.extend(str(item.label) for item in at.metric)
    phan.extend(str(item.value) for item in at.metric)
    return "\n".join(phan)


@pytest.fixture()
def kho_gia(tmp_path):
    folder = tmp_path / "ClipGocTest"
    folder.mkdir()
    for ten in ("00000000 - Clip một [aaaaaaaaaaa].opus",
                "00000000 - Clip hai [bbbbbbbbbbb].opus",
                "00000000 - Clip ba [ccccccccccc].opus"):
        (folder / ten).write_bytes(b"fixture")
    (folder / "clips_meta.json").write_text(
        json.dumps({
            "00000000 - Clip một [aaaaaaaaaaa].opus": {
                "id": "aaaaaaaaaaa",
                "title": "Clip một chính thức",
                "url": "https://youtu.be/aaaaaaaaaaa",
                "upload_date": "20240102",
                "duration": 610.0,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return folder


def test_man_hinh_tien_do_co_so_lieu_that_khi_job_dang_chay(
    tmp_path,
    kho_gia,
    monkeypatch,
):
    import streamlit

    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))

    script = tmp_path / "audfprint_gia.py"
    script.write_text(AUDFPRINT_GIA, encoding="utf-8")

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception

    # Màn hình tiến độ tự gọi st.rerun() để làm mới; AppTest sẽ lặp cho tới khi job
    # xong nên chỉ trả về khung hình CUỐI. Vô hiệu hoá rerun để chụp đúng khung hình
    # giữa chừng — thứ mà người dùng thực sự nhìn thấy.
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    eng = at.session_state.eng
    eng.require = lambda **kwargs: None
    eng._audfprint_build_cmd = lambda sub, *them, db_file: [
        sys.executable, "-u", str(script), them[them.index("--list") + 1], db_file
    ]
    eng.kho_dang_dung = "KhoTest"
    eng._doc_khos = lambda: {"dang_dung": "KhoTest", "danh_sach": [
        {"ten": "KhoTest", "db": Path(eng.db_file).name, "thu_muc": str(kho_gia), "shifts": 4}
    ]}
    eng._ghi_khos = lambda dang_ky: None
    eng.update_kho = lambda ten, thu_muc: None

    controller = at.session_state.fingerprint_controller
    controller.start(str(kho_gia), "new")
    at.session_state.job.update({
        "running": True, "pct": 0.0, "msg": "", "results": [], "error": "",
        "kind": "db", "fingerprint_job_id": "test", "da_day_sheet": False,
    })

    # Vẽ lại trang trong lúc worker còn chạy — đúng như người dùng nhìn thấy.
    thay_tien_do = []
    han = time.monotonic() + 60
    while controller.running and time.monotonic() < han and len(thay_tien_do) < 3:
        at.run()
        assert not at.exception
        thay_tien_do.append(_van_ban(at))

    ghep = "\n".join(thay_tien_do)
    assert "Đang tạo vân tay clip gốc" in ghep
    assert "Clip hiện tại" in ghep
    assert any(ten in ghep for ten in ("Clip một", "Clip hai", "Clip ba")), (
        "Màn hình tiến độ không hiện tên clip nào — đúng triệu chứng «đứng im»."
    )
    assert "Đã chạy" in ghep and "Đã xử lý" in ghep
    assert "Cập nhật gần nhất" in ghep
    assert any(
        cong_doan in ghep
        for cong_doan in ("Đang chạy audfprint", "Đang kiểm tra kho hiện có",
                          "Đang ghi database vân tay")
    )

    han = time.monotonic() + 60
    while controller.running and time.monotonic() < han:
        time.sleep(0.05)
    assert controller.error == ""
    assert controller.result["thanh_cong"] == 3


def test_bao_cao_hien_video_goc_cho_tung_doan_va_khong_nham_tong(tmp_path, kho_gia, monkeypatch):
    """Ba đoạn được chọn ⇒ ba video gốc; tổng đạt ngưỡng 12 giữ nguyên."""
    monkeypatch.setenv("TIMCLIP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TIMCLIP_OUTPUT_DIR", str(tmp_path / "ketqua"))

    at = AppTest.from_file(str(APP_PY), default_timeout=120).run()
    assert not at.exception

    import bang_ngang
    import dossier
    from engine import Match, ScanResult

    eng = at.session_state.eng
    eng.kho_dang_dung = "KhoTest"
    eng.kho_thu_muc = str(kho_gia)
    eng._metadata_cache_key = None
    eng._metadata_resolver_cache = None
    eng.db_clips = lambda bo_cache=False: [
        {"ten": p.name, "duong_dan": str(p), "so_hash": 100}
        for p in sorted(kho_gia.glob("*.opus"))
    ]

    kq = ScanResult(
        source_name="Video vi phạm 3 tiếng",
        source_ref="https://www.youtube.com/watch?v=Zlfty7Enrkg",
        source_id="Zlfty7Enrkg",
        duration_s=10800.0,
        matches=[
            Match(clip=p.name, start_s=i * 1200.0, end_s=i * 1200.0 + 300,
                  matched_s=300.0, clip_offset_s=0.0, hashes=500 - i,
                  confidence="cao", ty_le=40.0)
            for i, p in enumerate(sorted(kho_gia.glob("*.opus")))
        ],
        so_dat_nguong=12,
    )

    resolver = eng.clip_metadata_resolver(bo_cache=True)
    dong = bang_ngang.dung_dong_ngang(kq, resolver=resolver)
    header = bang_ngang.HEADER_NGANG

    for so in (1, 2, 3):
        assert dong[header.index(f"Link video gốc {so}")].startswith("https://youtu.be/")
        assert dong[header.index(f"Tên video gốc {so}")]
    for so in (4, 5):
        assert dong[header.index(f"Link video gốc {so}")] == ""
    assert dong[header.index("Tổng số đoạn phát hiện")] == 12

    # Thứ tự đoạn phải bám đúng thứ tự match, không bị dedup/sắp lại.
    assert [m.clip for m in kq.matches] == [p.name for p in sorted(kho_gia.glob("*.opus"))]
    # «Clip một» là clip duy nhất có metadata chính thức và nằm ở đoạn thứ 3.
    o_clip_mot = 3
    assert dong[header.index(f"Tên video gốc {o_clip_mot}")] == "Clip một chính thức"
    assert dong[header.index(f"Ngày đăng video gốc {o_clip_mot}")] == "02/01/2024"
    assert dong[header.index(f"Thời lượng video gốc {o_clip_mot}")] == "00:10:10"
    # Hai đoạn còn lại phục hồi từ tên file: có link/tên, không bịa ngày đăng.
    for so in (1, 2):
        assert dong[header.index(f"Ngày đăng video gốc {so}")] == ""
        assert dong[header.index(f"Thời lượng video gốc {so}")] == ""

    md = dossier.render_markdown(dossier.dung_ho_so(kq, resolver=resolver))
    assert md.count("- **Link video gốc:** https://youtu.be/") == 3
    assert "Tổng số đoạn vi phạm:** 3" in md

    rows = eng.to_rows([kq])
    assert len(rows) == 3
    assert all(row[5].startswith("https://youtu.be/") for row in rows)

    cov = eng.metadata_coverage(kq.matches)
    assert cov.selected_matches == 3
    assert cov.resolved_complete == 1        # chỉ clip có metadata chính thức
    assert cov.filename_fallbacks == 2       # hai clip còn lại phục hồi từ tên file
    assert cov.unresolved == 0 and cov.ambiguous == 0
