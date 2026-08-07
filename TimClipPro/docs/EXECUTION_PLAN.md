# EXECUTION PLAN — Khôi phục ánh xạ metadata clip gốc theo kho

**Mục tiêu:** sửa lookup metadata bị rỗng mà không thay fingerprint/matching, không tạo lại kho
1.717 clip và không gọi mạng trong lúc xuất báo cáo.

| Task | Target | Phụ thuộc |
|---|---|---|
| 1 | `clip_metadata.py` — model, validation, index, resolver, audit thuần | — |
| 2 | `engine.py` — nguồn metadata theo kho, snapshot, cache/invalidation, API resolver | Task 1 |
| 3 | `bang_ngang.py` — dùng resolver, giữ đúng 34 cột và index match | Task 1–2 |
| 4 | `dossier.py` và CSV dọc trong `engine.py` — cùng resolver, fallback không rỗng | Task 1–2 |
| 5 | `kiem_metadata_kho.py`, `cli.py`, `app.py` — diagnostic/offline repair/UI coverage | Task 1–4 |
| 6 | `tests/` và `docs/` — regression thật, hiệu năng, vận hành | Task 1–5 |

## TASK 1: Resolver metadata thuần và có thể giải thích

### Target File
`clip_metadata.py` — TẠO MỚI.

### Context & Tech Stack
- Python 3.10+, chỉ thư viện chuẩn.
- Đọc `channel.py` schema `clips_meta.json`, `engine.Match` và `.github/copilot-instructions.md`.

### Exact Input / Output
```python
@dataclass(frozen=True)
class ResolvedClipMetadata: ...

@dataclass(frozen=True)
class MetadataAudit: ...

class ClipMetadataResolver:
    def resolve(self, clip_name: str, clip_path: str | None = None) -> ResolvedClipMetadata: ...
    def audit(self, db_clips: list[dict]) -> MetadataAudit: ...
```

### Step-by-step Implementation
1. Validate từng entry nhưng giữ field hợp lệ khi field khác sai.
2. Dựng index exact, exact basename, canonical filename và YouTube ID đúng 11 ký tự.
3. Resolve theo exact → basename → canonical → unique ID → filename fallback → basename fallback.
4. ID có nhiều candidate khác dữ liệu trả `ambiguous`, không chọn tùy ý.
5. Dựng audit/counters O(n), không loop toàn metadata cho từng match.

### Edge Cases & Error Handling
| Tình huống | Hành vi |
|---|---|
| NFC/NFD, hoa/thường, path cũ | canonical resolve |
| Filename không có ID | không tạo URL giả |
| Entry sai schema | warning + giữ field hợp lệ |
| ID trùng | ambiguous |

### Constraints
- Không I/O, không mạng, không Streamlit.
- Không dùng title làm định danh khi có ID.

### Unit Test Criteria
Exact/path/case/NFC/ID/path cũ/schema/fallback/ambiguous/2.000 entry performance.

### Definition of Done
- [ ] Resolver deterministic, gần O(1)/lookup.
- [ ] Test module mới xanh.

## TASK 2: Nguồn metadata và snapshot riêng từng kho

### Target File
`engine.py` — SỬA `clip_meta`, `_ap_dung_kho`, build success boundary; THÊM API audit/snapshot.

### Context & Tech Stack
- Dùng `doc_json_an_toan`/`ghi_json_an_toan` cho đọc và ghi atomic.
- Snapshot nằm dưới `data/metadata/`, tên suy từ slug kho hiện tại.

### Exact Input / Output
```python
def clip_metadata_resolver(self) -> ClipMetadataResolver: ...
def clip_meta(self) -> dict: ...  # compatibility
def kiem_tra_metadata_kho(self) -> MetadataAudit: ...
def khoi_phuc_metadata_offline(self, dry_run: bool = True) -> MetadataRepairResult: ...
```

### Step-by-step Implementation
1. Candidate order deterministic: snapshot đúng kho, `self.kho_thu_muc`, directory clip DB, data dir.
2. Validate JSON/root/entry, warning rõ; không `except Exception: pass`.
3. Không merge metadata kho khác; conflict không ghi đè im lặng.
4. Cache theo kho + path/mtime/size; invalidate khi đổi kho/build/repair.
5. Sau fingerprint commit thành công mới merge và atomic-write snapshot; add không xóa entry cũ.

### Edge Cases & Error Handling
Malformed primary không crash; dùng snapshot hợp lệ. Dry-run không ghi. Snapshot có schema/version/kho.

### Constraints
- Không sửa `.pklz`, `_merge`, threshold, shifts, top-N.
- Không ghi đè `clips_meta.json` thật.

### Unit Test Criteria
Kho directory trực tiếp, path DB cũ, malformed JSON, multi-warehouse, snapshot merge/idempotency.

### Definition of Done
- [ ] Compatibility `clip_meta()` giữ dict.
- [ ] Snapshot chỉ ghi sau build success/offline repair explicit.

## TASK 3: Báo cáo ngang dùng resolver

### Target File
`bang_ngang.py` — SỬA `dung_dong_ngang`.

### Exact Input / Output
Nhận resolver hoặc mapping compatibility; mỗi `matches[i]` resolve độc lập và giữ nguyên index.

### Step-by-step Implementation
1. Không sort/deduplicate matches.
2. Ghi đúng metadata slot của cùng đoạn.
3. Fallback basename cho title khi unresolved.
4. Giữ `HEADER_NGANG` và đúng 34 cột; `so_dat_nguong` không đổi.

### Constraints
- Không đổi `SO_DOAN=5`, header hoặc thứ tự cột.
- Không gọi mạng/I/O.

### Unit Test Criteria
3 matches/12 total, ID lệch filename, 34 cột, duplicate source clip không lệch slot.

### Definition of Done
- [ ] Regression báo cáo ngang có ba metadata group đúng.

## TASK 4: CSV dọc và dossier dùng cùng resolver

### Target File
`dossier.py` — SỬA `dung_ho_so`; `engine.py` — nối resolver vào `to_rows`/export.

### Step-by-step Implementation
1. Cùng một resolver cho `to_rows`, horizontal rows và dossier.
2. CSV dọc dùng resolved title/url/date/duration; fallback basename không để clip gốc biến mất.
3. Tính coverage selected/complete/partial/unresolved/ambiguous và warning.
4. Export không gọi yt-dlp/HTTP.

### Edge Cases & Error Handling
Resolver absent vẫn nhận dict cũ; unresolved hiển thị basename; ambiguous không chọn metadata.

### Constraints
- Không đổi schema 15/34 cột.
- Không lấy metadata video vi phạm làm video gốc.

### Unit Test Criteria
Dossier + CSV dọc + ngang cùng resolve một entry; mock network phải không được gọi.

### Definition of Done
- [ ] Mọi exporter dùng cùng contract.

## TASK 5: Diagnostic, offline repair và UI coverage

### Target File
`kiem_metadata_kho.py` — TẠO MỚI; nối command trong `cli.py`, panel trong `app.py`.

### Exact Input / Output
CLI mặc định chỉ đọc; `--kho`, `--json`, `--repair-offline`, `--apply` là explicit.

### Step-by-step Implementation
1. Dùng Engine API an toàn, không unpickle path chưa validate.
2. In aggregate + tối đa 20 mẫu sạch, hỗ trợ match clip filters.
3. Offline repair mặc định dry-run; apply ghi snapshot atomic, không sửa source metadata.
4. UI “Tình trạng metadata báo cáo” có nút audit; không audit 1.717 clip mỗi rerun.
5. Cảnh báo khi có match nhưng coverage complete bằng 0/fallback/ambiguous.

### Constraints
- Không tự gọi YouTube. Network repair chỉ giữ command/UI explicit nếu source hiện có đủ adapter.
- Không in credential/full paths không cần thiết.

### Unit Test Criteria
CLI read-only, dry-run, AppTest render, warning coverage.

### Definition of Done
- [ ] Diagnostic kho thật chạy read-only.

## TASK 6: Regression, hiệu năng và tài liệu

### Target File
`tests/test_clip_metadata.py`, tests exporter/Engine và `docs/CLIP_METADATA_ARCHITECTURE.md`.

### Step-by-step Implementation
1. Fixture “Cory toàn bộ”: ba match, tổng 12, key lệch tên nhưng cùng ID.
2. Test exact/path/case/NFC/ID/schema/fallback/ambiguous/multi-kho/snapshot.
3. Test 34 cột, dossier, CSV dọc, no-network.
4. Benchmark index 2.000 entry và 1.000 resolve.
5. Chạy diagnostic thật, không tạo lại fingerprint; cập nhật audit/test/runbook/changelog.

### Constraints
- Mọi test data/output dùng `tmp_path`.
- Không gọi mạng hoặc kho fingerprint production trong automated tests.

### Definition of Done
- [ ] Full fast suite xanh; slow relevant được ghi nhận.
- [ ] `git diff --check` sạch.
- [ ] Diagnostic thật có số liệu exact/normalized/ID/fallback/missing/ambiguous.
