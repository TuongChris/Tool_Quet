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

import pandas as pd
import streamlit as st

from engine import Engine, Config, ScanResult, hhmmss
from channel import ChannelSync
from sheets import SheetsExporter

st.set_page_config(page_title="TimClip Pro — Tìm video gốc trong video dài",
                   page_icon="🔎", layout="wide")

# =====================================================================
#  Khởi tạo (giữ nguyên giữa các lần Streamlit vẽ lại màn hình)
# =====================================================================

if "eng" not in st.session_state:
    st.session_state.eng = Engine()
if "kho_dir" not in st.session_state:
    st.session_state.kho_dir = ""
if "sheet_link" not in st.session_state:
    st.session_state.sheet_link = ""
if "sheet_auto" not in st.session_state:
    st.session_state.sheet_auto = True
if "job" not in st.session_state:
    st.session_state.job = {"running": False, "pct": 0.0, "msg": "", "results": [],
                            "error": "", "kind": ""}

eng: Engine = st.session_state.eng
job = st.session_state.job


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


def lay_sheets() -> SheetsExporter:
    return SheetsExporter(sheet=st.session_state.sheet_link)


def day_len_sheets(rows, im_lang=False):
    """Đẩy các dòng kết quả lên Google Sheets. Trả về (ok, thông_báo)."""
    sx = lay_sheets()
    if not sx.san_sang():
        return False, sx.thieu_gi()
    try:
        n = sx.append(eng.HEADER, rows)
        return True, f"Đã ghi {n} dòng lên Google Sheets."
    except Exception as e:  # noqa: BLE001
        return False, f"Lỗi ghi Sheets: {e}"


def bang_ket_qua(results: list[ScanResult]) -> None:
    """Vẽ bảng kết quả + các nút xuất báo cáo và đẩy lên Google Sheets."""
    rows = eng.to_rows(results)
    df = pd.DataFrame(rows, columns=eng.HEADER)
    st.dataframe(df, width="stretch", hide_index=True)
    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")

    # Tự động đẩy lên Google Sheets ngay sau khi quét xong
    if st.session_state.sheet_auto and not job.get("da_day_sheet") and rows:
        ok, tb = day_len_sheets(rows)
        job["da_day_sheet"] = True
        if ok:
            st.success("📊 " + tb)
        elif lay_sheets().sheet_id:
            st.warning("📊 Không đẩy được lên Sheets: " + tb)

    c1, c2, c3, c4 = st.columns(4)
    with c3:
        if st.button("📊 Đẩy lên Google Sheets", width="stretch"):
            ok, tb = day_len_sheets(rows)
            (st.success if ok else st.error)(tb)
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
                                      help="Phải LỚN HƠN thời lượng clip gốc dài nhất, "
                                           "nếu không sẽ sót clip nằm vắt qua ranh giới.")
        c.min_hash = st.slider("Số hash tối thiểu", 5, 100, c.min_hash,
                               help="Bị báo nhầm → tăng lên. Bỏ sót → giảm xuống.")
        c.min_match_s = st.slider("Đoạn khớp tối thiểu (giây)", 1.0, 60.0, c.min_match_s, 1.0)
        c.ncores = st.slider("Số nhân CPU", 1, 8, c.ncores,
                             help="Máy nhiều nhân thì tăng lên để chạy nhanh hơn.")

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
        if c.overlap_s >= c.chunk_s:
            st.error("«Khúc gối nhau» phải NHỎ HƠN «Độ dài mỗi khúc».")

    st.divider()
    st.subheader("📊 Google Sheets")
    with st.expander("Cấu hình", expanded=False):
        st.session_state.sheet_link = st.text_input(
            "Link Google Sheet", st.session_state.sheet_link,
            placeholder="https://docs.google.com/spreadsheets/d/...")
        st.session_state.sheet_auto = st.checkbox(
            "Tự động đẩy sau mỗi lần quét", st.session_state.sheet_auto)
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
    st.caption(f"📂 Dữ liệu: `{eng.data_dir}`")


# =====================================================================
#  Khi có tác vụ đang chạy: chỉ hiện màn hình tiến độ
# =====================================================================

if job["running"]:
    st.header("⏳ Đang xử lý...")
    st.progress(job["pct"], text=f"{job['pct']*100:.0f}%")
    st.info(job["msg"] or "Đang khởi động...")
    if st.button("⏹️ Dừng lại", type="secondary"):
        eng.cancel()
        st.warning("Đã gửi yêu cầu dừng, chờ một chút...")
    st.caption("Cửa sổ này tự cập nhật. Bạn có thể để yên và làm việc khác, "
               "nhưng đừng đóng cửa sổ đen phía sau.")
    time.sleep(1.0)
    st.rerun()

# Tác vụ vừa xong → hiện kết quả
if not job["running"] and (job["results"] or job["error"]):
    if job["error"]:
        st.error(f"Lỗi: {job['error']}")
    elif job["kind"] == "channel":
        r = job["results"]
        st.success(f"✅ Đồng bộ xong: tải mới **{r['moi']}** video, "
                   f"bỏ qua {r['bo_qua']} video đã có. Thư mục: `{r['thu_muc']}`")
        if r["loi"]:
            st.warning("Một số video lỗi:\n\n- " + "\n- ".join(r["loi"][:10]))
        st.info("Bước tiếp theo: sang tab «Kho clip gốc» bấm «Bổ sung clip mới vào kho» "
                "để tạo vân tay cho các video vừa tải.")
    elif job["kind"] == "db":
        r = job["results"]
        st.success(f"✅ Đã xử lý {r.get('da_xu_ly', r['so_clip'])}/{r['so_clip']} clip "
                   f"trong {r['giay']:.0f} giây.")
        if r.get("loi_file"):
            with st.expander(f"⚠️ {len(r['loi_file'])} file có vấn đề — bấm xem"):
                st.code("\n".join(r["loi_file"][:50]))
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

        # An toàn: ngưỡng đặt quá cao sẽ lọc sạch kết quả — phải báo rõ, không im lặng
        if tong_match == 0 and tong_loai:
            cao_nhat = max((m.hashes for x in res for m in getattr(x, "matches_loai", [])),
                           default=0)
            st.warning(
                f"⚠️ Có **{tong_loai}** kết quả nhưng **không cái nào đạt ngưỡng** "
                f"«Loại hẳn nếu dưới {eng.config.min_hash_floor} hash». "
                f"Kết quả mạnh nhất chỉ đạt **{cao_nhat} hash**.\n\n"
                f"Nếu clip gốc của bạn ngắn hoặc ít âm thanh, hãy hạ ngưỡng này xuống "
                f"khoảng **{max(100, int(cao_nhat * 0.6))}** ở thanh bên rồi quét lại.")
            with st.expander(f"Xem {min(tong_loai, 30)} kết quả bị loại"):
                st.dataframe(pd.DataFrame([{
                    "Nguồn": x.source_name, "Clip gốc": m.clip,
                    "Xuất hiện từ": m.start_hhmmss, "Số hash": m.hashes,
                    "Tỷ lệ (%)": m.ty_le,
                } for x in res for m in sorted(getattr(x, "matches_loai", []),
                                               key=lambda z: -z.hashes)[:30]]),
                    width="stretch", hide_index=True)
        elif tong_loai:
            st.caption(f"ℹ️ Đã loại {tong_loai} kết quả yếu (dưới "
                       f"{eng.config.min_hash_floor} hash) khỏi báo cáo.")

        if tong_match:
            st.success(f"✅ Đã chọn **{tong_match}** bằng chứng tốt nhất "
                       f"từ {len(res)} nguồn đã quét.")
        elif not tong_loai:
            st.warning("Không tìm thấy clip gốc nào trong các nguồn đã quét.")
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

    if xem_truoc:
        with st.spinner("Đang lấy danh sách (không tải gì cả)..."):
            try:
                ds = ChannelSync.list_channel(kenh_url.strip(), gioi_han or None)
                st.success(f"Kênh có {len(ds)} video.")
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
        if xoa != "— chọn —" and st.button(f"🗑️ Xoá kho «{xoa}»"):
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
            chay_nen("db", eng.build_database, thumuc.strip('" '), "new")
    with c2:
        if st.button("➕ Bổ sung clip mới vào kho", width="stretch",
                     disabled=not (thumuc and eng.kho_dang_dung)):
            chay_nen("db", eng.build_database, thumuc.strip('" '), "add")

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
        chay_nen("scan", eng.scan_many, links, "youtube")
    if not env["database"]:
        st.warning("Chưa có kho vân tay — hãy làm tab «Kho clip gốc» trước.")

# ---------------------------------------------------------------- TAB 3
with tab3:
    st.subheader("Quét video/audio dài có sẵn trong máy")
    st.caption("Nhập đường dẫn FILE hoặc THƯ MỤC. Không dùng nút upload để tránh "
               "phải copy file hàng chục GB.")

    duong_dan = st.text_input("Đường dẫn file hoặc thư mục",
                              placeholder=r"D:\VideoDai  hoặc  D:\VideoDai\video30h.mp4")
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
        chay_nen("scan", eng.scan_many, ds_file, "file")

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
        if st.button("🗑️ Xóa lần quét này khỏi lịch sử"):
            eng.delete_job(chon)
            st.rerun()
