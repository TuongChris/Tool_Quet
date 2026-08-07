# -*- coding: utf-8 -*-
"""Công cụ audit/sửa ngày đăng — offline, fetcher giả, không gọi mạng."""

from __future__ import annotations

import json
from datetime import date

import kiem_ngay_dang

VN = "Asia/Ho_Chi_Minh"

TEN_CU = "00000000 - Clip cu [T_mKh8IUpWw].opus"
TEN_MOI = "20240701 - Clip moi [aaaaaaaaaaa].opus"


def _lap_kho(tmp_path):
    (tmp_path / TEN_CU).write_bytes(b"opus")
    (tmp_path / TEN_MOI).write_bytes(b"opus")
    (tmp_path / "clips_meta.json").write_text(json.dumps({
        # Schema cũ: chỉ có upload_date, không có epoch -> không sửa offline được.
        TEN_CU: {
            "id": "T_mKh8IUpWw", "title": "Clip cu",
            "url": "https://youtu.be/T_mKh8IUpWw",
            "upload_date": "20250620", "duration": 955.0,
        },
        # Đã có epoch lưu sẵn -> sửa được offline.
        TEN_MOI: {
            "id": "aaaaaaaaaaa", "title": "Clip moi",
            "url": "https://youtu.be/aaaaaaaaaaa",
            "upload_date": "20240701", "timestamp": 1719853200,   # 17:00 UTC
            "duration": 100.0,
        },
    }, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


def test_audit_khong_ghi_gi_va_phan_loai_dung(tmp_path):
    kho = _lap_kho(tmp_path)
    truoc = (tmp_path / "clips_meta.json").read_text(encoding="utf-8")

    tk = kiem_ngay_dang.audit(kho, VN)

    assert tk.tong == 2
    assert tk.co_provenance == 0
    assert tk.chi_upload_date == 1          # chỉ TEN_CU
    assert tk.co_epoch_luu_san == 1         # chỉ TEN_MOI
    assert tk.thieu_ngay == 0
    # TEN_MOI có epoch 17:00 UTC -> giờ VN sang hôm sau -> phát hiện sẽ đổi.
    assert [t[0] for t in tk.se_doi] == [TEN_MOI]
    assert (tmp_path / "clips_meta.json").read_text(encoding="utf-8") == truoc


def test_repair_offline_chi_sua_entry_co_epoch_va_dry_run_khong_ghi(tmp_path):
    kho = _lap_kho(tmp_path)
    truoc = (tmp_path / "clips_meta.json").read_text(encoding="utf-8")

    kq = kiem_ngay_dang.repair(kho, VN, dung_mang=False, apply=False, gioi_han=0)

    assert kq["da_doi"] == 1
    assert kq["thay_doi"][0][0] == TEN_MOI
    assert kq["thay_doi"][0][2] == date(2024, 7, 2)
    assert kq["da_ghi"] is False
    assert (tmp_path / "clips_meta.json").read_text(encoding="utf-8") == truoc, \
        "Dry-run tuyệt đối không được ghi"


def test_repair_offline_apply_ghi_va_tao_backup(tmp_path):
    kho = _lap_kho(tmp_path)

    kq = kiem_ngay_dang.repair(kho, VN, dung_mang=False, apply=True, gioi_han=0)

    assert kq["da_ghi"] is True
    meta = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    assert meta[TEN_MOI]["publication_date"] == "20240702"
    assert meta[TEN_MOI]["publication_date_source"] == "timestamp"
    assert meta[TEN_MOI]["upload_date"] == "20240702"      # tương thích bản đọc cũ
    # Entry chỉ có upload_date: ngày giữ nguyên (offline không suy ra được giờ),
    # nhưng được đánh dấu nguồn là upload_date — độ tin cậy thấp.
    assert meta[TEN_CU]["upload_date"] == "20250620"
    assert meta[TEN_CU]["publication_date_source"] == "upload_date"

    backup = list(tmp_path.glob("clips_meta.json.truoc_ngay_dang_*"))
    assert backup, "Phải sao lưu trước khi ghi"


def test_dau_provenance_do_tin_cay_thap_khong_chan_repair_network(tmp_path):
    """Bẫy: chạy offline trước rồi network sau vẫn phải sửa được entry cũ."""
    kho = _lap_kho(tmp_path)
    kiem_ngay_dang.repair(kho, VN, dung_mang=False, apply=True, gioi_han=0)

    da_goi = []

    def fetcher(video_id, timeout=30):
        da_goi.append(video_id)
        return {"id": video_id, "upload_date": "20250620", "timestamp": 1750445139}

    kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=True, gioi_han=0, fetcher=fetcher
    )

    assert "T_mKh8IUpWw" in da_goi, "Entry chỉ dựa upload_date vẫn phải được hỏi lại"
    assert "aaaaaaaaaaa" not in da_goi, "Entry đã có epoch thì không hỏi lại nữa"
    meta = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    assert meta[TEN_CU]["publication_date"] == "20250621"


def test_repair_network_dung_fetcher_va_sua_dung_ngay(tmp_path):
    kho = _lap_kho(tmp_path)
    da_goi = []

    def fetcher(video_id, timeout=30):
        da_goi.append(video_id)
        return {
            "id": video_id,
            "upload_date": "20250620",
            "timestamp": 1750445139,        # UTC 2025-06-20 18:45:39 -> VN 21/06
        }

    kq = kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=True, gioi_han=0, fetcher=fetcher
    )

    assert "T_mKh8IUpWw" in da_goi
    meta = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    assert meta[TEN_CU]["publication_date"] == "20250621"
    assert meta[TEN_CU]["publication_date_source"] == "timestamp"
    assert meta[TEN_CU]["timestamp"] == 1750445139
    assert kq["that_bai"] == 0


def test_repair_network_mot_video_loi_khong_lam_hong_ca_kho(tmp_path):
    kho = _lap_kho(tmp_path)

    def fetcher(video_id, timeout=30):
        raise RuntimeError("Video is private")

    kq = kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=False, gioi_han=0, fetcher=fetcher
    )

    assert kq["that_bai"] == 2
    assert kq["da_doi"] == 0
    assert len(kq["loi"]) == 2
    meta = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    assert meta[TEN_CU]["upload_date"] == "20250620", "Không được đụng khi fetch lỗi"


def test_dung_som_khi_bi_chan_lien_tiep_va_khong_ghi_gi(tmp_path):
    """YouTube chặn chống bot -> mọi request sau đều hỏng; phải dừng sớm."""
    kho = _lap_kho(tmp_path)
    truoc = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    so_goi = []

    def fetcher(video_id, timeout=30):
        so_goi.append(video_id)
        raise RuntimeError("Sign in to confirm you're not a bot")

    kq = kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=True, gioi_han=0,
        fetcher=fetcher, dung_sau_n_loi=1,
    )

    assert kq["dung_som"] is True
    assert len(so_goi) == 1, "Phải dừng ngay sau ngưỡng lỗi, không gọi tiếp"
    assert kq["con_lai"] >= 1
    sau = json.loads((tmp_path / "clips_meta.json").read_text(encoding="utf-8"))
    assert sau == truoc, "Không sửa được gì thì không được ghi đè metadata"


def test_nghi_giua_cac_lan_goi_mang(tmp_path, monkeypatch):
    kho = _lap_kho(tmp_path)
    da_nghi = []
    monkeypatch.setattr(kiem_ngay_dang.time, "sleep", lambda s: da_nghi.append(s))

    kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=False, gioi_han=0,
        fetcher=lambda vid, timeout=30: {"id": vid, "timestamp": 1750445139},
        nghi_giay=1.5,
    )

    # Nghỉ giữa các lần gọi, không nghỉ trước lần đầu.
    assert da_nghi == [1.5]


def test_limit_gioi_han_so_clip_xu_ly(tmp_path):
    kho = _lap_kho(tmp_path)
    da_goi = []

    def fetcher(video_id, timeout=30):
        da_goi.append(video_id)
        return {"id": video_id, "timestamp": 1750445139}

    kiem_ngay_dang.repair(
        kho, VN, dung_mang=True, apply=False, gioi_han=1, fetcher=fetcher
    )

    assert len(da_goi) == 1
