# -*- coding: utf-8 -*-
"""
app.py — GIAO DIỆN của TimClip Pro (Streamlit, chạy 100% trên máy bạn).

Đây chỉ là lớp áo mỏng: mọi xử lý thật đều nằm trong engine.py.
Muốn đổi sang giao diện khác (CLI, desktop, API) thì thay file này, engine giữ nguyên.

Chạy: double-click ChayTool.bat  (hoặc: streamlit run app.py)
Dữ liệu KHÔNG đi đâu cả — server chỉ lắng nghe ở localhost trên máy bạn.
"""

import os
import threading
import time
from datetime import datetime

import pandas as pd
import streamlit as st

import bang_ngang
from cau_hinh import GIA_TRI_GIAO_DIEN_MAC_DINH
from clip_metadata import configure_metadata_logging
from engine import Engine, ScanResult, hhmmss, o_bang_tinh_an_toan
from fingerprint_progress import FingerprintJobController
from scan_jobs import ScanJobController, ScanLaunchConfig
from scan_ui import build_scan_status_dataframe
from sheet_delivery import SheetDelivery, SheetDeliveryWorker, khoa_giao_hang
from channel import ChannelSync
from sheets import SheetsExporter

st.set_page_config(page_title="TimClip Pro — Tìm video gốc trong video dài",
                   page_icon="🔎", layout="wide")
configure_metadata_logging()

# =====================================================================
#  Khởi tạo (giữ nguyên giữa các lần Streamlit vẽ lại màn hình)
# =====================================================================

if "eng" not in st.session_state:
    st.session_state.eng = Engine(
        data_dir=os.environ.get("TIMCLIP_DATA_DIR") or None,
        out_dir=os.environ.get("TIMCLIP_OUTPUT_DIR") or None,
    )
du_lieu_giao_dien = st.session_state.eng.cau_hinh_da_luu
for khoa, mac_dinh in GIA_TRI_GIAO_DIEN_MAC_DINH.items():
    if khoa not in st.session_state:
        gia_tri = du_lieu_giao_dien.get(khoa, mac_dinh)
        st.session_state[khoa] = (
            gia_tri if type(gia_tri) is type(mac_dinh) else mac_dinh
        )
if "job" not in st.session_state:
    st.session_state.job = {"running": False, "pct": 0.0, "msg": "", "results": [],
                            "error": "", "kind": ""}

eng: Engine = st.session_state.eng
job = st.session_state.job
if "fingerprint_controller" not in st.session_state:
    st.session_state.fingerprint_controller = FingerprintJobController(eng)
fingerprint_controller: FingerprintJobController = (
    st.session_state.fingerprint_controller
)


def _dong_bo_job_van_tay() -> None:
    """Chỉ main Streamlit thread đọc controller và cập nhật session_state."""
    if job.get("kind") != "db" or not job.get("fingerprint_job_id"):
        return
    fingerprint_controller.drain()
    if job.get("running") and not fingerprint_controller.running:
        job["running"] = False
        job["results"] = fingerprint_controller.result or []
        job["error"] = fingerprint_controller.error


_dong_bo_job_van_tay()


if "scan_sheet_worker" not in st.session_state:
    # sender nhận sheet_link kèm theo công việc nên chạy được ở thread nền:
    # nó KHÔNG đọc st.session_state, nơi thread nền chỉ thấy proxy rỗng.
    st.session_state.scan_sheet_worker = SheetDeliveryWorker(
        sender=lambda sheet_link, header, rows:
            tao_sheets_exporter(sheet_link).append(header, rows)
    )
if "scan_controller" not in st.session_state:
    st.session_state.scan_controller = ScanJobController(
        eng, sheet_worker=st.session_state.scan_sheet_worker
    )
scan_sheet_worker: SheetDeliveryWorker = st.session_state.scan_sheet_worker
scan_controller: ScanJobController = st.session_state.scan_controller


def chay_quet(nguon: list, source_type: str) -> None:
    """Khởi động batch quét. Kết quả hiện ngay từng video; Sheets gửi song song."""
    if job.get("running") or scan_controller.running:
        st.warning("Đang có tác vụ chạy; không tạo job trùng.")
        return
    # SNAPSHOT toàn bộ cấu hình NGAY TẠI ĐÂY, trên main thread. Thread nền không
    # có ScriptRunContext nên đọc st.session_state từ đó chỉ nhận proxy rỗng —
    # đó chính là nguyên nhân của «missing ScriptRunContext» và KeyError sheet_link.
    # Snapshot cũng khiến batch đang chạy không bị đổi đích khi người dùng sửa
    # link Sheet giữa chừng; batch sau mới dùng cấu hình mới.
    cau_hinh_quet = ScanLaunchConfig(
        auto_sheet=bool(st.session_state.sheet_auto),
        sheet_link=str(st.session_state.sheet_link or ""),
        dang_ngang=bool(st.session_state.sheet_dang_ngang),
    )
    if cau_hinh_quet.auto_sheet:
        scan_sheet_worker.start()

    def sau_moi_video(index: int, tong: int, ket_qua) -> None:
        """Chạy trong SCAN WORKER — chỉ dùng cau_hinh_quet, không chạm Streamlit."""
        if not cau_hinh_quet.auto_sheet or ket_qua.status != "ok":
            return
        if cau_hinh_quet.dang_ngang:
            header, rows = bang_ngang.HEADER_NGANG, eng.to_rows_ngang([ket_qua])
        else:
            header, rows = eng.HEADER, eng.to_rows([ket_qua])
        if not rows:
            return
        rows = [[o_bang_tinh_an_toan(o) for o in dong] for dong in rows]
        khoa = khoa_giao_hang(
            cau_hinh_quet.sheet_id, "",
            "ngang" if cau_hinh_quet.dang_ngang else "doc",
            ket_qua.job_id, ket_qua.source_id, rows,
        )
        scan_sheet_worker.enqueue(SheetDelivery(
            delivery_key=khoa,
            source_id=ket_qua.source_id or "",
            source_name=ket_qua.source_name or "",
            header=header, rows=rows,
            sheet_link=cau_hinh_quet.sheet_link,
        ))
        scan_controller.ghi_nhan_giao_hang(index, khoa)

    batch_id = scan_controller.start(nguon, source_type, on_result=sau_moi_video)
    job.update({
        "running": True, "pct": 0.0, "msg": "Đang chuẩn bị...", "results": [],
        "error": "", "kind": "scan", "da_day_sheet": True, "scan_batch_id": batch_id,
    })
    st.rerun()


def chay_nen(kind: str, ham, *args, **kwargs):
    """Chạy một tác vụ dài trong luồng nền để giao diện không bị đơ và nút Dừng vẫn bấm được."""
    job.update({"running": True, "pct": 0.0, "msg": "Đang khởi động...",
                "results": [], "error": "", "kind": kind, "da_day_sheet": False})
    eng.cancel_event.clear()

    def bao_tien_do(pct, msg):
        job["pct"], job["msg"] = pct, msg

    def target():
        try:
            job["results"] = ham(*args, progress=bao_tien_do, **kwargs)
        except Exception as e:  # noqa: BLE001
            job["error"] = str(e)
        finally:
            job["running"] = False

    t = threading.Thread(target=target, daemon=True)
    t.start()
    st.rerun()


def chay_van_tay(thumuc: str, mode: str) -> None:
    """Khởi động đúng một controller; worker không gọi API Streamlit."""
    if job.get("running") or fingerprint_controller.running:
        st.warning("Đang có tác vụ chạy; không tạo thêm job trùng.")
        return
    eng.cancel_event.clear()
    job_id = fingerprint_controller.start(thumuc, mode)
    job.update({
        "running": True,
        "pct": 0.0,
        "msg": "Đang chuẩn bị danh sách clip...",
        "results": [],
        "error": "",
        "kind": "db",
        "da_day_sheet": False,
        "fingerprint_job_id": job_id,
    })
    st.rerun()


def _thoi_luong(giay: float | None) -> str:
    if giay is None:
        return "Đang tính..."
    giay = max(0, int(giay))
    return f"{giay // 3600:02d}:{(giay % 3600) // 60:02d}:{giay % 60:02d}"


TEN_PHASE = {
    "discovering": "Đang chuẩn bị danh sách clip",
    "validating": "Đang kiểm tra kho hiện có",
    "probing": "Đang đọc thông tin media",
    "decoding": "Đang giải mã bằng FFmpeg",
    "fingerprinting": "Đang chạy audfprint",
    "saving": "Đang ghi database vân tay",
    "completed": "Hoàn tất",
    "cancelled": "Đã dừng",
    "failed": "Thất bại",
}

TEN_PHASE_QUET = {
    "queued": "Đang chờ",
    "fetching_metadata": "Đang lấy thông tin video",
    "downloading": "Đang tải audio",
    "chunking": "Đang cắt khúc",
    "matching": "Đang so khớp vân tay",
    "merging": "Đang tổng hợp kết quả",
    "completed": "Hoàn tất",
    "failed": "Lỗi",
    "cancelled": "Đã dừng",
}
# Tên hiển thị của trạng thái quét/Sheets nằm trong scan_ui.py, cạnh builder
# DataFrame, để bảng và schema không bao giờ lệch nhau.


def tao_sheets_exporter(sheet_link: str) -> SheetsExporter:
    """Hàm THUẦN — gọi được từ thread nền vì không chạm Streamlit."""
    return SheetsExporter(sheet=sheet_link)


def lay_sheets() -> SheetsExporter:
    """Bản tiện dụng cho MAIN THREAD; đọc cấu hình từ session state."""
    return tao_sheets_exporter(st.session_state.sheet_link)


def day_len_sheets(results: list[ScanResult]) -> tuple[bool, str]:
    """Đẩy các dòng kết quả lên Google Sheets. Trả về (ok, thông_báo)."""
    if not results:
        return False, "Không có dữ liệu để ghi."

    if st.session_state.sheet_dang_ngang:
        header = bang_ngang.HEADER_NGANG
        rows = eng.to_rows_ngang(results)
    else:
        header = eng.HEADER
        rows = eng.to_rows(results)
    if not rows:
        return False, "Không có dữ liệu để ghi."

    sx = lay_sheets()
    if not sx.san_sang():
        return False, sx.thieu_gi()
    try:
        n = sx.append(header, rows)
        return True, f"Đã ghi {n} dòng lên Google Sheets."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi ghi Sheets: {e}"


def bao_cao_khong_co_ket_qua(results: list[ScanResult]) -> None:
    """Giải thích một lượt quét 0 kết quả MẤT Ở TẦNG NÀO, thay vì chỉ nói không thấy.

    Năm tình huống dưới đây trước kia hiện ra y hệt nhau nên người dùng không phân
    biệt được âm tính đúng với lỗi phần mềm: audfprint không ra dòng nào; ra dòng
    nhưng parser đọc không được; bằng chứng quá yếu; không đạt tiêu chí chấp nhận;
    chọn lọc bỏ hết. Giờ mỗi tình huống có câu trả lời riêng.
    """
    ok = [x for x in results if x.status == "ok"]
    if not ok:
        return

    for x in ok:
        cd = getattr(x, "chan_doan", None)
        tieu_de = x.source_name or x.source_ref
        if cd is None:
            st.warning(f"**{tieu_de}** — không tìm thấy clip gốc nào.")
            continue

        st.warning(f"**{tieu_de}** — không có đoạn nào đạt tiêu chí.\n\n"
                   f"{cd.mat_o_dau()}")
        with st.expander("🔎 Chi tiết chẩn đoán"):
            st.markdown(
                f"- Số khúc đã cắt: **{cd.so_khuc}**\n"
                f"- Dòng khớp thô từ audfprint: **{cd.dong_co_matched}**\n"
                f"- Đọc ra được: **{cd.parse_duoc}**\n"
                f"- Qua lọc số hash tối thiểu: **{cd.qua_min_hash}**\n"
                f"- Qua lọc độ dài tối thiểu: **{cd.qua_min_match_s}**\n"
                f"- Ứng viên sau khi gộp: **{cd.gop_lai}**\n"
                f"- Đạt tiêu chí chấp nhận: **{cd.duoc_chap_nhan}**\n"
                f"- Bằng chứng thô mạnh nhất: **{cd.hash_tho_lon_nhat} hash**, "
                f"đoạn dài nhất **{cd.khop_tho_dai_nhat:.1f}s**"
            )
            u = cd.manh_nhat_bi_loai
            if u is not None:
                st.markdown("**Ứng viên mạnh nhất đã bị loại**")
                st.code(u.mo_ta(), language=None)
                # Giúp người dùng tự phân biệt reup thật với nhạc hiệu dùng chung.
                if u.ty_le < 5 and u.matched_s < 30:
                    st.caption(
                        "Dấu hiệu này (phủ vân tay rất thấp, đoạn khớp chỉ vài giây) "
                        "thường là nhạc hiệu/nhạc nền dùng chung giữa nhiều clip gốc, "
                        "không phải một bản reup. Hạ ngưỡng lúc này sẽ tạo báo cáo sai."
                    )
            # Giữ khả năng soi toàn bộ ứng viên bị loại như bản cũ, chỉ đổi chỗ đặt
            # và bổ sung cột mật độ — cột này mới là thứ phân biệt reup với nhiễu.
            bi_loai = sorted(getattr(x, "matches_loai", []),
                             key=lambda z: -z.hashes)[:30]
            if bi_loai:
                st.markdown(f"**{len(bi_loai)} ứng viên bị loại mạnh nhất**")
                st.dataframe(pd.DataFrame([{
                    "Clip gốc": m.clip,
                    "Xuất hiện từ": m.start_hhmmss,
                    "Số hash": m.hashes,
                    "Phủ (%)": m.ty_le,
                    "Khớp (giây)": round(m.matched_s, 1),
                    "Mật độ (hash/giây)": round(m.hashes / m.matched_s, 1)
                    if m.matched_s else 0.0,
                } for m in bi_loai]), width="stretch", hide_index=True)
            if cd.da_thu_toc_do:
                st.markdown(
                    f"**Đã thử bù tốc độ {len(cd.da_thu_toc_do)} lượt** "
                    "(phòng trường hợp video bị tăng/giảm tốc để né nhận dạng)")
                for x in cd.da_thu_toc_do:
                    st.caption(f"• {x}")
            for canh in cd.canh_bao:
                st.caption(f"⚠️ {canh}")
            st.caption(cd.tom_tat())


def bang_ket_qua(results: list[ScanResult]) -> None:
    """Vẽ bảng kết quả + các nút xuất báo cáo và đẩy lên Google Sheets."""
    matches = [
        match
        for result in results
        if result.status == "ok"
        for match in result.matches
    ]
    if matches:
        coverage = eng.metadata_coverage(matches)
        if coverage.resolved_complete == 0:
            st.warning(
                "⚠️ Đã phát hiện đoạn vi phạm nhưng không clip gốc nào có đủ "
                "metadata chính thức (ID, tên, link, ngày đăng và thời lượng). "
                "Báo cáo vẫn hiển thị dữ liệu phục hồi an toàn và đánh dấu phần thiếu."
            )
        if coverage.filename_fallbacks:
            st.warning(
                f"⚠️ {coverage.filename_fallbacks}/{coverage.selected_matches} video gốc "
                "được phục hồi từ filename. Tiêu đề có thể đã được rút gọn; "
                "ngày đăng/thời lượng chỉ hiện khi có bằng chứng."
            )
        if coverage.unresolved or coverage.ambiguous:
            st.error(
                f"Metadata chưa ánh xạ: {coverage.unresolved}; "
                f"mơ hồ (không tự chọn): {coverage.ambiguous}."
            )
        tong_dat_nguong = sum(
            result.so_dat_nguong for result in results if result.status == "ok"
        )
        if tong_dat_nguong != len(matches):
            st.caption(
                f"Có {tong_dat_nguong} đoạn đạt ngưỡng trước bước chọn lọc; "
                f"{len(matches)} đoạn được chọn để xuất. Hai số này có chủ đích khác nhau."
            )
    rows = eng.to_rows(results)
    df = pd.DataFrame(rows, columns=eng.HEADER)
    st.dataframe(df, width="stretch", hide_index=True)
    df_csv = pd.DataFrame(
        [[o_bang_tinh_an_toan(o) for o in dong] for dong in rows],
        columns=eng.HEADER,
    )
    csv_bytes = df_csv.to_csv(index=False).encode("utf-8-sig")

    # Tự động đẩy lên Google Sheets ngay sau khi quét xong
    if st.session_state.sheet_auto and not job.get("da_day_sheet") and rows:
        ok, tb = day_len_sheets(results)
        job["da_day_sheet"] = True
        if ok:
            st.success("📊 " + tb)
        elif tb == "Không có dữ liệu để ghi.":
            st.info("📊 " + tb)
        elif lay_sheets().sheet_id:
            st.warning("📊 Không đẩy được lên Sheets: " + tb)

    c1, c2, c3, c4 = st.columns(4)
    with c3:
        if st.button("📊 Đẩy lên Google Sheets", width="stretch"):
            ok, tb = day_len_sheets(results)
            if ok:
                st.success(tb)
            elif tb == "Không có dữ liệu để ghi.":
                st.info(tb)
            else:
                st.error(tb)
    with c1:
        st.download_button("⬇️ Tải báo cáo CSV", csv_bytes,
                           file_name=f"ketqua_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                           mime="text/csv", width="stretch")
    with c2:
        if st.button("💾 Lưu CSV vào thư mục ketqua\\", width="stretch"):
            st.success(f"Đã lưu: {eng.export_csv(results)}")
    with c4:
        if st.button("📄 Xuất hồ sơ khiếu nại", width="stretch"):
            try:
                fs = eng.export_ho_so(results)
                if not fs:
                    st.info("Không có kết quả nào đủ điều kiện lập hồ sơ.")
                else:
                    st.success(f"Đã tạo {len(fs)} hồ sơ trong ketqua\\")
                    st.code("\n".join(fs))
            except Exception as e:  # noqa: BLE001
                st.error(str(e))


# =====================================================================
#  Thanh bên: tình trạng hệ thống + tham số
# =====================================================================

with st.sidebar:
    st.title("🔎 TimClip Pro")
    st.caption("Tìm video gốc bên trong video dài — chạy hoàn toàn trên máy bạn.")
    thong_bao_cau_hinh = st.session_state.pop("thong_bao_cau_hinh", "")
    if thong_bao_cau_hinh:
        st.success(thong_bao_cau_hinh)
    for canh_bao in eng.canh_bao_khoi_dong:
        st.warning(canh_bao)

    st.subheader("Tình trạng hệ thống")
    env = eng.check_env()
    dong = {"ffmpeg": "FFmpeg", "ffprobe": "FFprobe", "yt_dlp": "yt-dlp",
            "audfprint": "audfprint", "database": "Kho vân tay clip gốc"}
    for k, ten in dong.items():
        st.write(("✅ " if env[k] else "❌ ") + ten +
                 (f" `{env['yt_dlp_version']}`" if k == "yt_dlp" and env[k] else ""))
    if not all(env[k] for k in ("ffmpeg", "ffprobe", "audfprint")):
        st.error("Thiếu công cụ — hãy chạy lại `cai_dat.bat`.")

    st.subheader("🗄️ Kho đang dùng")
    khos = eng.list_khos()
    if khos:
        tens = [k["ten"] for k in khos]
        hien_tai = eng.kho_dang_dung if eng.kho_dang_dung in tens else tens[0]
        chon = st.selectbox("Chọn kho để quét", tens, index=tens.index(hien_tai),
                            label_visibility="collapsed")
        if chon != eng.kho_dang_dung:
            eng.use_kho(chon)
            st.rerun()
    else:
        st.warning("Chưa có kho nào — tạo ở tab «Kho clip gốc».")

    clips = eng.db_clips()
    if clips:
        st.info(f"Kho «{eng.kho_dang_dung}» có **{len(clips)}** clip gốc.")
    elif khos:
        st.warning(f"Kho «{eng.kho_dang_dung}» chưa có vân tay.")

    st.divider()
    st.subheader("⚙️ Tham số")
    with st.expander("Mở để tinh chỉnh", expanded=False):
        c = eng.config
        c.chunk_s = st.number_input("Độ dài mỗi khúc (giây)", 300, 7200, c.chunk_s, 300,
                                    help="Máy yếu RAM thì giảm xuống 1800.")
        c.overlap_s = st.number_input("Khúc gối nhau (giây)", 60, 3600, c.overlap_s, 60,
                                      help="Giá trị đề xuất khi thiếu metadata. Giá trị hiệu lực "
                                           "luôn bị giới hạn bởi trần khúc gối "
                                           f"({c.overlap_max_s} giây).")
        c.min_hash = st.slider("Số hash tối thiểu", 5, 100, c.min_hash,
                               help="Bị báo nhầm → tăng lên. Bỏ sót → giảm xuống.")
        c.min_match_s = st.slider("Đoạn khớp tối thiểu (giây)", 1.0, 60.0, c.min_match_s, 1.0)
        c.ncores = st.slider(
            "Số nhân CPU", 0, 8, c.ncores,
            help="Đặt 0 để tự dò, chừa một nhân cho hệ thống và dùng tối đa 8 nhân.")
        c.shifts_kho = st.number_input(
            "Subframe shifts khi tạo kho", 0, 8, max(0, c.shifts_kho), 1,
            help="Cao hơn giúp bắt vân tay chính xác hơn nhưng tạo kho chậm và tốn "
                 "dung lượng hơn. Đặt 0 để dùng hành vi cũ.")
        c.shifts_quet = st.number_input(
            "Subframe shifts khi quét", 0, 8, max(0, c.shifts_quet), 1,
            help="Cao hơn giúp chịu nén và lệch pha tốt hơn nhưng quét chậm hơn. "
                 "Đặt 0 để dùng hành vi cũ.")

        st.markdown("**Chọn lọc kết quả**")
        c.top_n = st.number_input("Chỉ lấy bao nhiêu kết quả tốt nhất", 1, 50, c.top_n)
        c.min_hash_floor = st.number_input(
            "Loại hẳn nếu dưới (hash)", 0, 100000, c.min_hash_floor, 100,
            help="Kết quả yếu hơn ngưỡng này bị vứt bỏ, không đưa vào báo cáo.")
        c.min_hash_strong = st.number_input(
            "Coi là bằng chứng mạnh từ (hash)", 0, 200000, c.min_hash_strong, 500,
            help="Những kết quả đạt ngưỡng này được ưu tiên chọn trước.")
        c.phan_bo_deu = st.checkbox(
            "Phân bổ đều đầu / giữa / cuối video", c.phan_bo_deu,
            help="Chia video vi phạm thành N vùng, mỗi vùng lấy 1 bằng chứng mạnh nhất — "
                 "hồ sơ khiếu nại chứng minh được vi phạm trải dài cả video.")
        c.uu_tien_clip_khac_nhau = st.checkbox(
            "Ưu tiên các clip gốc khác nhau", c.uu_tien_clip_khac_nhau)
        c.keep_downloads = st.checkbox("Giữ lại audio đã tải", c.keep_downloads,
                                       help="Bỏ tick để tiết kiệm ổ cứng (lần sau phải tải lại).")
        st.caption(
            f"Khúc gối hiệu lực tối đa hiện tại: {c.overlap_max_s} giây; "
            "clip dài có thể được ghép lại từ nhiều mảnh ở ranh giới."
        )

    st.divider()
    st.subheader("📊 Google Sheets")
    with st.expander("Cấu hình", expanded=False):
        st.session_state.sheet_link = st.text_input(
            "Link Google Sheet", st.session_state.sheet_link,
            placeholder="https://docs.google.com/spreadsheets/d/...")
        st.session_state.sheet_auto = st.checkbox(
            "Tự động đẩy sau mỗi lần quét", st.session_state.sheet_auto)
        lua_chon_dinh_dang = st.radio(
            "Định dạng đẩy lên Sheets",
            ("Ngang (khớp bảng 34 cột)", "Dọc (chi tiết, 15 cột)"),
            index=0 if st.session_state.sheet_dang_ngang else 1,
        )
        st.session_state.sheet_dang_ngang = (
            lua_chon_dinh_dang == "Ngang (khớp bảng 34 cột)"
        )
        sx_tmp = SheetsExporter(sheet=st.session_state.sheet_link)
        em = sx_tmp.email_service_account()
        if em:
            st.caption("Nhớ chia sẻ Sheet (quyền Người chỉnh sửa) cho:")
            st.code(em, language=None)
        if st.button("🔌 Kiểm tra kết nối", width="stretch"):
            ok, tb = sx_tmp.kiem_tra()
            (st.success if ok else st.error)(tb)
        if not sx_tmp.co_key():
            st.caption("Chưa có `google_key.json` — xem hướng dẫn ở đầu file `sheets.py`.")

    st.divider()
    c_luu, c_mac_dinh = st.columns(2)
    with c_luu:
        if st.button(
            "💾 Lưu cấu hình",
            width="stretch",
            disabled=job["running"],
        ):
            try:
                eng.luu_cau_hinh({
                    khoa: st.session_state[khoa]
                    for khoa in GIA_TRI_GIAO_DIEN_MAC_DINH
                })
                st.success("Đã lưu cấu hình.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Không lưu được cấu hình: {e}")
    with c_mac_dinh:
        if st.button(
            "↩️ Khôi phục mặc định",
            width="stretch",
            disabled=job["running"],
        ):
            try:
                eng.khoi_phuc_cau_hinh_mac_dinh()
            except Exception as e:  # noqa: BLE001
                st.error(f"Không khôi phục được cấu hình: {e}")
            else:
                st.session_state.clear()
                st.session_state.thong_bao_cau_hinh = (
                    "Đã khôi phục cấu hình mặc định."
                )
                st.rerun()

    st.divider()
    st.caption(f"📂 Dữ liệu: `{eng.data_dir}`")


# =====================================================================
#  Khi có tác vụ đang chạy: chỉ hiện màn hình tiến độ
# =====================================================================

if job["running"]:
    if job.get("kind") == "db":
        fingerprint_controller.drain()
        fp = fingerprint_controller.snapshot()
        now = time.time()
        progress_slot = st.empty()
        status_slot = st.empty()
        metrics_slot = st.empty()
        file_slot = st.empty()
        heartbeat_slot = st.empty()
        log_slot = st.empty()

        st.header("🔊 Đang tạo vân tay clip gốc")
        progress_slot.progress(
            fp.percent,
            text=(
                f"Đã hoàn tất {fp.processed_count} / {fp.total} — "
                f"{fp.percent * 100:.1f}%"
                if fp.total
                else "Đang chuẩn bị danh sách clip..."
            ),
        )
        status_slot.info(
            f"**Công đoạn:** {TEN_PHASE.get(fp.phase, fp.phase)}  \n"
            f"{fp.message}"
        )
        if fp.file_name:
            file_slot.markdown(
                f"**Clip hiện tại ({fp.current}/{fp.total}):** `{fp.file_name}`"
            )
        else:
            file_slot.markdown("**Clip hiện tại:** đang xác định...")

        with metrics_slot.container():
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Đã tính xong", fp.success_count)
            m2.metric("Đã tồn tại", fp.skipped_count)
            m3.metric("Lỗi", fp.failed_count)
            m4.metric("Đã xử lý", f"{fp.processed_count}/{fp.total}")
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Đã chạy", _thoi_luong(fp.elapsed_seconds))
            t2.metric(
                "Tốc độ trung bình",
                f"{fp.rate_per_minute:.1f} clip/phút"
                if fp.rate_per_minute is not None
                else "Đang tính...",
            )
            t3.metric("ETA", _thoi_luong(fp.eta_seconds))
            t4.metric(
                "Worker",
                "Đang hoạt động" if fp.worker_alive else "Đã dừng",
            )

        cap_nhat = datetime.fromtimestamp(fp.updated_at).strftime("%H:%M:%S")
        clip_elapsed = (
            now - fp.current_clip_started_at
            if fp.current_clip_started_at is not None
            else None
        )
        pid = fp.active_subprocess_pid or "—"
        heartbeat_slot.caption(
            f"Cập nhật gần nhất: {cap_nhat} · PID audfprint: {pid} · "
            f"Clip hiện tại đã chạy: {_thoi_luong(clip_elapsed)} · "
            f"Queue: {fp.queue_size}/256"
        )
        if clip_elapsed is not None and clip_elapsed >= 120:
            st.warning(
                "Clip hiện tại đang xử lý lâu hơn bình thường. "
                "Worker/subprocess vẫn hoạt động; phần trăm không được tăng giả."
            )
        elif now - fp.last_progress_at >= 15 and fp.worker_alive:
            st.warning(
                "Chưa có event mới trong 15 giây, nhưng worker vẫn sống. "
                "Đang chờ subprocess hoặc thao tác ghi file."
            )

        recent = fingerprint_controller.recent()[-20:]
        if recent:
            log_slot.code("\n".join(
                f"{datetime.fromtimestamp(event.updated_at):%H:%M:%S} "
                f"{event.status:<16} {event.message}"
                for event in recent
            ))

        if st.button(
            "⏹️ Dừng lại",
            type="secondary",
            disabled=fp.status == "cancel_requested",
        ):
            fingerprint_controller.cancel()
            st.warning("Đang yêu cầu dừng; chưa đánh dấu đã dừng cho tới khi worker xác nhận.")
        st.caption(
            "Trang tự làm mới từ queue bounded; worker không gọi Streamlit trực tiếp. "
            "Log kỹ thuật: `ketqua/fingerprint.log`."
        )
    elif job.get("kind") == "scan":
        anh = scan_controller.snapshot()
        if not scan_controller.running:
            job["running"] = False
            job["results"] = scan_controller.results()
            job["error"] = scan_controller.error

        st.header("🔍 Đang quét video")
        st.progress(
            anh.batch_progress,
            text=f"{anh.completed + anh.failed} / {anh.total} video — "
                 f"{anh.batch_progress * 100:.0f}%",
        )
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Hoàn tất", anh.completed)
        b2.metric("Lỗi", anh.failed)
        b3.metric("Đã chạy", _thoi_luong(anh.elapsed_seconds))
        b4.metric("ETA", _thoi_luong(anh.eta_seconds))

        if 0 < anh.current_index <= len(anh.videos):
            v = anh.videos[anh.current_index - 1]
            st.info(
                f"**[{v.index}/{anh.total}] {v.title or v.nguon[:70]}**  \n"
                f"Công đoạn: {TEN_PHASE_QUET.get(v.phase, v.phase)} · "
                f"Đã chạy video: {_thoi_luong(v.elapsed)}  \n"
                f"{v.message}"
            )

        st.dataframe(
            build_scan_status_dataframe(anh.videos, scan_sheet_worker.snapshot()),
            width="stretch", hide_index=True, height=260,
        )

        tom_tat = scan_sheet_worker.tom_tat()
        if tom_tat["tong"]:
            st.caption(
                f"Google Sheets — đã gửi {tom_tat['da_gui']}, "
                f"đang chờ {tom_tat['cho_gui']}, lỗi {tom_tat['that_bai']}. "
                "Quét không chờ Sheets."
            )
        if st.button("⏹️ Dừng lại", type="secondary", disabled=anh.cancelled):
            scan_controller.cancel()
            st.warning("Đã gửi yêu cầu dừng; kết quả đã xong vẫn được giữ.")
    else:
        st.header("⏳ Đang xử lý...")
        st.progress(job["pct"], text=f"{job['pct']*100:.0f}%")
        st.info(job["msg"] or "Đang khởi động...")
        if st.button("⏹️ Dừng lại", type="secondary"):
            eng.cancel()
            st.warning("Đã gửi yêu cầu dừng, chờ một chút...")
        st.caption("Cửa sổ này tự cập nhật. Bạn có thể để yên và làm việc khác, "
                   "nhưng đừng đóng cửa sổ đen phía sau.")
    time.sleep(0.75)
    st.rerun()

# Tác vụ vừa xong → hiện kết quả
if not job["running"] and (job["results"] or job["error"]):
    if job["error"]:
        st.error(f"Lỗi: {job['error']}")
    elif job["kind"] == "channel":
        r = job["results"]
        thong_bao = st.warning if r.get("da_huy") else st.success
        tien_to = "⏹️ Đã dừng đồng bộ" if r.get("da_huy") else "✅ Đồng bộ xong"
        thong_bao(f"{tien_to}: tải mới **{r['moi']}** video, "
                  f"bỏ qua {r['bo_qua']} video đã có. Thư mục: `{r['thu_muc']}`")
        if r["loi"]:
            st.warning("Một số video lỗi:\n\n- " + "\n- ".join(r["loi"][:10]))
        st.info("Bước tiếp theo: sang tab «Kho clip gốc» bấm «Bổ sung clip mới vào kho» "
                "để tạo vân tay cho các video vừa tải.")
    elif job["kind"] == "db":
        r = job["results"]
        thong_bao = st.warning if r.get("da_huy") else st.success
        thong_bao(
            f"{'⏹️ Đã dừng' if r.get('da_huy') else '✅ Hoàn tất tạo vân tay'}: "
            f"đã xử lý {r.get('da_xu_ly', r['so_clip'])}/{r['so_clip']} clip "
            f"trong {r['giay']:.0f} giây."
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Tạo mới", r.get("thanh_cong", r.get("da_xu_ly", 0)))
        m2.metric("Đã tồn tại", r.get("bo_qua", 0))
        m3.metric("Lỗi", r.get("that_bai", len(r.get("loi_file", []))))
        if r.get("canh_bao"):
            st.warning("\n\n".join(r["canh_bao"]))
        if r.get("loi_file"):
            with st.expander(f"⚠️ {len(r['loi_file'])} file có vấn đề — bấm xem"):
                st.code("\n".join(r["loi_file"][:50]))
    elif job["kind"] == "metadata_network":
        r = job["results"]
        st.success(
            f"Đã vá metadata snapshot cho {r['da_va']}/{r['tong']} clip; "
            f"không đổi {r['bo_qua']}, lỗi {len(r['loi'])}."
        )
        if r["loi"]:
            with st.expander(f"⚠️ {len(r['loi'])} clip chưa vá được"):
                st.code("\n".join(r["loi"][:50]))
        st.caption(f"Snapshot: `{r['snapshot_path']}`")
    elif job["kind"] == "sua":
        r = job["results"]
        st.success(f"✅ Đã dựng lại danh sách: {r['tren_dia']} video thực có trên đĩa "
                   f"(trước đó archive ghi {r['archive_cu']}).")
        if r["ma_bi_thieu"]:
            st.info(f"Bổ sung {len(r['ma_bi_thieu'])} video có file nhưng archive quên ghi.")
        if r["ma_bi_ghi_thua"]:
            st.warning(f"Có {len(r['ma_bi_ghi_thua'])} mã trong archive nhưng KHÔNG thấy file "
                       "— chúng sẽ được tải lại ở lần đồng bộ tới.")
    else:
        res = job["results"]
        tong_match = sum(len(x.matches) for x in res)
        tong_loai = sum(len(getattr(x, "matches_loai", [])) for x in res)
        loi = [x for x in res if x.status != "ok"]

        # Không có kết quả thì PHẢI nói mất ở tầng nào. Trước đây chỗ này chỉ nói
        # "không tìm thấy" và khuyên hạ ngưỡng xuống 60% của kết quả mạnh nhất —
        # lời khuyên đó tạo dương tính giả: với video chỉ chứa nhạc hiệu dùng chung
        # của kênh, hạ ngưỡng sẽ biến một đoạn 9 giây thành "bằng chứng vi phạm".
        if tong_match == 0:
            bao_cao_khong_co_ket_qua(res)
        elif tong_loai:
            st.caption(f"ℹ️ Đã loại {tong_loai} ứng viên chưa đạt tiêu chí chấp nhận "
                       "khỏi báo cáo.")

        if tong_match:
            st.success(f"✅ Đã chọn **{tong_match}** bằng chứng tốt nhất "
                       f"từ {len(res)} nguồn đã quét.")
            # Bị đổi tốc độ là dấu hiệu né nhận dạng có chủ ý — người dùng cần biết
            # để đưa vào hồ sơ khiếu nại, và để hiểu vì sao mốc thời gian hơi lệch.
            for x in res:
                cd = getattr(x, "chan_doan", None)
                if cd is not None and cd.toc_do_tim_duoc:
                    st.info(
                        f"🔎 **{x.source_name}** chỉ khớp sau khi bù tốc độ — "
                        f"{cd.toc_do_tim_duoc}. Video này nhiều khả năng đã bị "
                        "chỉnh tốc độ để né nhận dạng bản quyền.")
        if loi:
            st.error("Có nguồn bị lỗi: " + "; ".join(f"{x.source_name} ({x.note})" for x in loi))
        bang_ket_qua(res)
    if st.button("🧹 Xóa kết quả, làm việc khác"):
        job.update({"results": [], "error": "", "kind": ""})
        st.rerun()
    st.divider()


# =====================================================================
#  Các tab chức năng
# =====================================================================

tab0, tab1, tab2, tab3, tab4 = st.tabs(
    ["📥 Đồng bộ kênh gốc", "🎬 Kho clip gốc", "▶️ Quét YouTube",
     "📁 Quét file trong máy", "📜 Lịch sử"])

# ---------------------------------------------------------------- TAB 0
with tab0:
    st.subheader("Tự động tải toàn bộ video từ kênh YouTube gốc của bạn")
    st.caption("Chỉ tải phần tiếng, nén còn opus mono 64 kbps — đã đo thực nghiệm là "
               "cho độ chính xác đối chiếu NGANG BẰNG video gốc, nhưng nhẹ hơn ~100 lần.")

    kenh_url = st.text_input("Link kênh YouTube của bạn",
                             placeholder="https://www.youtube.com/@TenKenh")
    st.session_state.kho_dir = st.text_input(
        "Thư mục kho clip gốc (ổ D, E... tùy bạn)", st.session_state.kho_dir,
        placeholder=r"D:\KhoClipGoc")

    c1, c2 = st.columns([1, 1])
    with c1:
        gioi_han = st.number_input("Chỉ lấy N video mới nhất (0 = toàn bộ kênh)",
                                   0, 5000, 0, 10)
    with c2:
        st.write("")
        st.write("")
        xem_truoc = st.button("👀 Xem danh sách video của kênh", width="stretch",
                              disabled=not kenh_url)

    lay_ngay = st.checkbox(
        "Lấy cả ngày đăng chính xác (chậm: thêm 1 lượt hỏi mỗi video)",
        value=False,
        help="YouTube không trả ngày đăng ở chế độ liệt kê nhanh. Bật khi bạn cần "
             "xem ngày đăng ngay tại đây. Việc đồng bộ kho KHÔNG cần bật: ngày đăng "
             "thật được lấy sẵn trong lượt tải của từng video.",
    )

    if xem_truoc:
        with st.spinner("Đang lấy danh sách (không tải gì cả)..."):
            try:
                ds = ChannelSync.list_channel(
                    kenh_url.strip(), gioi_han or None, lay_ngay_dang=lay_ngay
                )
                st.success(f"Kênh có {len(ds)} video.")
                thieu_ngay = sum(1 for v in ds if not v.upload_date)
                if thieu_ngay:
                    st.caption(
                        f"{thieu_ngay}/{len(ds)} video chưa có ngày đăng trong danh "
                        "sách nhanh. Ngày đăng thật vẫn được ghi đúng khi đồng bộ kho."
                    )
                st.dataframe(pd.DataFrame([{
                    "Ngày đăng": v.upload_date, "Tiêu đề": v.title,
                    "Thời lượng": hhmmss(v.duration), "ID": v.id} for v in ds]),
                    width="stretch", hide_index=True, height=280)
                tong_phut = sum(v.duration for v in ds) / 60
                st.caption(f"Tổng {tong_phut:,.0f} phút → ước tính kho audio khoảng "
                           f"**{tong_phut * 0.48:,.0f} MB** "
                           f"(nếu tải cả video sẽ là ~{tong_phut * 30:,.0f} MB).")
            except Exception as e:  # noqa: BLE001
                st.error(f"Lỗi: {e}")

    if st.button("⬇️ Bắt đầu đồng bộ kênh", type="primary",
                 disabled=not (kenh_url and st.session_state.kho_dir)):
        cs = ChannelSync(st.session_state.kho_dir.strip('" '))
        chay_nen("channel", cs.sync, kenh_url.strip(), gioi_han or None,
                 cancel_check=lambda: eng.cancel_event.is_set())

    if st.session_state.kho_dir and os.path.isdir(st.session_state.kho_dir.strip('" ')):
        tk = ChannelSync(st.session_state.kho_dir.strip('" ')).thong_ke()
        st.info(f"Kho hiện có **{tk['so_file']}** file audio gốc "
                f"({tk['dung_luong_mb']:,.0f} MB).")

    st.caption("Chạy lại bất cứ lúc nào — hệ thống ghi nhớ trong `downloaded.txt` "
               "nên chỉ tải video MỚI, không tải trùng.")

    st.divider()
    st.markdown("#### 🔧 Bị mất mạng giữa chừng? Xử lý ở đây")
    st.caption("Không cần tải lại từ đầu. Hệ thống đối chiếu file THỰC TẾ trên đĩa "
               "(đọc mã ID trong tên file) nên không bao giờ tải trùng.")
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("🔍 Kiểm tra còn thiếu video nào", width="stretch",
                     disabled=not (kenh_url and st.session_state.kho_dir)):
            with st.spinner("Đang đối chiếu kênh với thư mục kho..."):
                try:
                    cs = ChannelSync(st.session_state.kho_dir.strip('" '))
                    r = cs.kiem_tra_thieu(kenh_url.strip(), gioi_han or None)
                    st.success(f"Kênh có {r['tong_kenh']} video — đã có **{r['co_roi']}**, "
                               f"còn thiếu **{len(r['thieu'])}**.")
                    if r["thieu"]:
                        st.dataframe(pd.DataFrame([{
                            "Ngày đăng": v.upload_date, "Tiêu đề": v.title,
                            "Thời lượng": hhmmss(v.duration), "ID": v.id}
                            for v in r["thieu"]]), width="stretch", hide_index=True)
                        st.info("Bấm «Bắt đầu đồng bộ kênh» ở trên — chỉ những video này "
                                "được tải, các video đã có sẽ bỏ qua.")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Lỗi: {e}")
    with cc2:
        if st.button("🛠️ Dựng lại danh sách đã tải", width="stretch",
                     disabled=not st.session_state.kho_dir,
                     help="Dùng khi downloaded.txt bị mất/hỏng, hoặc bạn tự chép file vào kho. "
                          "Chỉ ghi lại file text, KHÔNG đụng vào file audio."):
            try:
                cs = ChannelSync(st.session_state.kho_dir.strip('" '))
                job.update({"kind": "sua", "results": cs.sua_archive(),
                            "error": "", "running": False, "da_day_sheet": True})
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Lỗi: {e}")

# ---------------------------------------------------------------- TAB 1
with tab1:
    st.subheader("Quản lý các kho clip gốc")
    st.caption("Mỗi kho là một bộ vân tay RIÊNG (ví dụ: Ẩm thực, Du lịch, Review). "
               "Khi quét video vi phạm, chọn đúng kho tương ứng — vừa nhanh vừa ít báo nhầm.")

    with st.expander("➕ Tạo kho mới", expanded=not khos):
        n1, n2 = st.columns([2, 1])
        with n1:
            ten_moi = st.text_input("Tên kho", placeholder="Ví dụ: Ẩm thực")
        with n2:
            st.write("")
            st.write("")
            if st.button("Tạo kho", width="stretch", disabled=not ten_moi):
                try:
                    eng.add_kho(ten_moi)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(str(e))

    if khos:
        st.dataframe(pd.DataFrame([{
            "Đang dùng": "✅" if k["dang_dung"] else "",
            "Tên kho": k["ten"],
            "Thư mục": k["thu_muc"] or "(chưa đặt)",
            "Đã có vân tay": "✅" if k["co_van_tay"] else "—",
        } for k in khos]), width="stretch", hide_index=True)

        xoa = st.selectbox("Xoá kho (chỉ xoá vân tay, KHÔNG xoá file video của bạn)",
                           ["— chọn —"] + [k["ten"] for k in khos])
        xac_nhan_xoa_kho = st.checkbox(
            "Tôi xác nhận muốn xóa vân tay của kho đã chọn",
            disabled=xoa == "— chọn —",
        )
        if xoa != "— chọn —" and st.button(
            f"🗑️ Xoá kho «{xoa}»",
            disabled=not xac_nhan_xoa_kho,
        ):
            eng.delete_kho(xoa)
            st.rerun()

    st.divider()
    st.markdown(f"#### Nạp clip vào kho đang dùng: **{eng.kho_dang_dung or '(chưa có kho)'}**")

    thumuc = st.text_input("Đường dẫn thư mục chứa video gốc của kho này",
                           value=eng.kho_thu_muc,
                           placeholder=r"D:\ClipGocSML",
                           help="Copy đường dẫn từ thanh địa chỉ của File Explorer.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Tạo lại kho từ đầu", type="primary", width="stretch",
                     disabled=not (thumuc and eng.kho_dang_dung)):
            chay_van_tay(thumuc.strip('" '), "new")
    with c2:
        if st.button("➕ Bổ sung clip mới vào kho", width="stretch",
                     disabled=not (thumuc and eng.kho_dang_dung)):
            chay_van_tay(thumuc.strip('" '), "add")

    st.divider()
    st.markdown("#### Tình trạng metadata báo cáo")
    st.caption(
        "Kiểm tra chỉ đọc mối liên hệ giữa clip trong fingerprint DB và metadata. "
        "Khôi phục offline chỉ tạo/cập nhật snapshot riêng của kho; không sửa "
        "`clips_meta.json`, không gọi mạng và không tạo lại fingerprint."
    )
    mc1, mc2 = st.columns(2)
    with mc1:
        if st.button(
            "🔍 Kiểm tra metadata báo cáo",
            width="stretch",
            disabled=not bool(clips),
        ):
            try:
                audit = eng.kiem_tra_metadata_kho()
                st.session_state.metadata_audit = audit.to_dict()
                st.session_state.metadata_audit_kho = eng.kho_dang_dung
            except Exception as e:  # noqa: BLE001
                st.error(f"Không kiểm tra được metadata: {e}")
    with mc2:
        if st.button(
            "🧪 Xem trước khôi phục offline",
            width="stretch",
            disabled=not bool(clips),
        ):
            try:
                preview = eng.khoi_phuc_metadata_offline(dry_run=True)
                st.session_state.metadata_repair_preview = preview.to_dict()
                st.session_state.metadata_repair_preview_kho = eng.kho_dang_dung
                st.session_state.metadata_audit = preview.audit.to_dict()
                st.session_state.metadata_audit_kho = eng.kho_dang_dung
            except Exception as e:  # noqa: BLE001
                st.error(f"Không lập được dry-run: {e}")

    audit_data = st.session_state.get("metadata_audit")
    if (
        audit_data
        and st.session_state.get("metadata_audit_kho") == eng.kho_dang_dung
    ):
        a1, a2, a3 = st.columns(3)
        a1.metric("Clip trong fingerprint DB", audit_data["total_db_clips"])
        a2.metric("Metadata đầy đủ", audit_data["complete"])
        a3.metric("Metadata một phần", audit_data["partial"])
        a4, a5, a6 = st.columns(3)
        a4.metric("Phục hồi từ filename", audit_data["filename_fallbacks"])
        a5.metric("Chưa ánh xạ", audit_data["missing"])
        a6.metric("Mơ hồ / xung đột", audit_data["ambiguous"])
        st.caption(
            "Nguồn đang dùng: "
            + (", ".join(audit_data.get("source_files") or []) or "chưa có")
            + f" · Snapshot cập nhật: {audit_data.get('updated_at') or 'chưa có'}"
        )
        if audit_data.get("complete", 0) == 0 and audit_data.get("total_db_clips", 0):
            st.warning(
                "Kho có fingerprint nhưng chưa clip nào có đủ toàn bộ metadata báo cáo. "
                "Có thể xuất dữ liệu fallback, nhưng báo cáo chưa được xem là đầy đủ."
            )
        if audit_data.get("samples"):
            with st.expander("Mẫu metadata thiếu/mơ hồ (tối đa 20)"):
                st.dataframe(
                    pd.DataFrame(audit_data["samples"]),
                    width="stretch",
                    hide_index=True,
                )

    preview_data = st.session_state.get("metadata_repair_preview")
    if (
        preview_data
        and st.session_state.get("metadata_repair_preview_kho") == eng.kho_dang_dung
    ):
        st.info(
            f"Dry-run: {preview_data['updated']} entry sẽ được cập nhật, "
            f"{preview_data['unchanged']} không đổi, "
            f"{preview_data['skipped_ambiguous']} mơ hồ bị bỏ qua."
        )
    confirm_offline = st.checkbox(
        "Tôi xác nhận chỉ tạo/cập nhật snapshot metadata offline của kho đang dùng",
        key="confirm_metadata_offline",
    )
    if st.button(
        "🛠️ Khôi phục metadata offline",
        disabled=not (confirm_offline and bool(clips)),
    ):
        try:
            repaired = eng.khoi_phuc_metadata_offline(dry_run=False)
            if repaired.errors:
                st.error("; ".join(repaired.errors))
            else:
                st.success(
                    f"Đã cập nhật snapshot: {repaired.updated} entry; "
                    f"không đổi {repaired.unchanged}."
                )
                st.caption(f"Snapshot: `{repaired.snapshot_path}`")
                st.session_state.metadata_audit = eng.kiem_tra_metadata_kho().to_dict()
                st.session_state.metadata_audit_kho = eng.kho_dang_dung
        except Exception as e:  # noqa: BLE001
            st.error(f"Không khôi phục được metadata: {e}")

    with st.expander("🌐 Vá metadata thiếu từ YouTube (tác vụ mạng riêng)"):
        st.warning(
            "Chỉ dùng khi bạn chủ động cần ngày đăng/thời lượng chính thức. "
            "Tác vụ không tải audio/video, có timeout và retry hữu hạn, nhưng có thể "
            "mất nhiều thời gian với kho lớn."
        )
        confirm_network = st.checkbox(
            "Tôi xác nhận cho phép gọi YouTube để vá các entry còn thiếu",
            key="confirm_metadata_network",
        )
        if st.button(
            "Bắt đầu vá metadata thiếu",
            disabled=not (
                confirm_network
                and bool(clips)
                and eng.kho_thu_muc
                and not job.get("running")
            ),
        ):
            chay_nen("metadata_network", eng.va_metadata_thieu)

    if clips:
        st.divider()
        st.write(f"**Kho «{eng.kho_dang_dung}» hiện có {len(clips)} clip:**")
        st.dataframe(pd.DataFrame(
            [{"Tên clip": x["ten"], "Số hash": x["so_hash"], "Đường dẫn": x["duong_dan"]}
             for x in clips]), width="stretch", hide_index=True, height=300)
    elif eng.kho_dang_dung:
        st.info("Kho này đang trống. Nhập đường dẫn thư mục rồi bấm «Tạo lại kho từ đầu».")

# ---------------------------------------------------------------- TAB 2
with tab2:
    st.subheader("Quét video YouTube dài")
    st.caption("Hệ thống chỉ tải RIÊNG phần audio (video 30 tiếng ≈ 1–2 GB thay vì vài chục GB). "
               "Đứt mạng cứ chạy lại — sẽ tải tiếp từ chỗ dừng.")

    links_text = st.text_area("Dán link YouTube — mỗi dòng một link", height=160,
                              placeholder="https://www.youtube.com/watch?v=xxxxxxxxxxx\n"
                                          "https://youtu.be/yyyyyyyyyyy")
    links = [x.strip() for x in links_text.splitlines()
             if x.strip() and not x.strip().startswith("#")]
    if links:
        st.caption(f"Đã nhận {len(links)} link.")
    if st.button("🚀 Bắt đầu quét", type="primary", disabled=not links or not env["database"]):
        chay_quet(links, "youtube")
    if not env["database"]:
        st.warning("Chưa có kho vân tay — hãy làm tab «Kho clip gốc» trước.")

# ---------------------------------------------------------------- TAB 3
with tab3:
    st.subheader("Quét video/audio dài có sẵn trong máy")
    st.caption("Nhập đường dẫn FILE hoặc THƯ MỤC. Không dùng nút upload để tránh "
               "phải copy file hàng chục GB.")

    st.session_state.thu_muc_quet_gan_nhat = st.text_input(
        "Đường dẫn file hoặc thư mục",
        st.session_state.thu_muc_quet_gan_nhat,
        placeholder=r"D:\VideoDai  hoặc  D:\VideoDai\video30h.mp4",
    )
    duong_dan = st.session_state.thu_muc_quet_gan_nhat
    ds_file = []
    if duong_dan:
        dd = duong_dan.strip('" ')
        if os.path.isdir(dd):
            from engine import liet_ke_media
            ds_file = liet_ke_media(dd)
            st.caption(f"Tìm thấy {len(ds_file)} file media trong thư mục.")
        elif os.path.isfile(dd):
            ds_file = [dd]
        else:
            st.error("Không tìm thấy đường dẫn này.")
    if st.button("🚀 Bắt đầu quét", key="quet_file", type="primary",
                 disabled=not ds_file or not env["database"]):
        chay_quet(ds_file, "file")

# ---------------------------------------------------------------- TAB 4
with tab4:
    st.subheader("Lịch sử các lần quét")
    jobs = eng.list_jobs()
    if not jobs:
        st.info("Chưa có lần quét nào.")
    else:
        st.dataframe(pd.DataFrame([{
            "ID": j["id"], "Thời điểm": j["created_at"], "Loại": j["source_type"],
            "Nguồn": j["source_name"], "Thời lượng": hhmmss(j["duration_s"] or 0),
            "Kết quả": j["n_matches"], "Trạng thái": j["status"],
        } for j in jobs]), width="stretch", hide_index=True)

        chon = st.selectbox("Xem chi tiết lần quét số",
                            [j["id"] for j in jobs],
                            format_func=lambda i: f"#{i} — " +
                            next(j["source_name"] for j in jobs if j["id"] == i))
        ms = eng.job_matches(chon)
        if ms:
            df = pd.DataFrame([{
                "Clip gốc": m["clip"], "Xuất hiện từ": hhmmss(m["start_s"]),
                "Đến": hhmmss(m["end_s"]), "Đoạn khớp (giây)": round(m["matched_s"]),
                "Khớp từ giây thứ (của clip)": round(m["clip_offset_s"]),
                "Số hash": m["hashes"], "Đánh giá": m["confidence"],
            } for m in ms])
            st.dataframe(df, width="stretch", hide_index=True)
            st.download_button("⬇️ Tải CSV lần quét này",
                               df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"ketqua_job{chon}.csv", mime="text/csv")
        else:
            st.info("Lần quét này không có kết quả nào.")
        xac_nhan_xoa_lich_su = st.checkbox(
            "Tôi xác nhận muốn xóa lần quét đã chọn khỏi lịch sử"
        )
        if st.button(
            "🗑️ Xóa lần quét này khỏi lịch sử",
            disabled=not xac_nhan_xoa_lich_su,
        ):
            eng.delete_job(chon)
            st.rerun()
