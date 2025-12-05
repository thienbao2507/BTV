
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db import transaction
from django.db.models import Avg, Q, Max
from core.decorators import judge_required
from .models import (
    CuocThi,
    VongThi,
    BaiThi,
    ThiSinh,
    GiamKhao,
    PhieuChamDiem,
    ThiSinhCuocThi,
    BaiThiTemplateItem,
    BaiThiTemplateSection,
    GiamKhaoBaiThi,
    BanGiamDoc,
    SpecialRoundPairMember,
    SpecialRoundScoreLog,
)

import json
import unicodedata     # 👈 thêm dòng này

BGD_SESSION_KEYS = ("bgd_mode", "bgd_ct_id", "bgd_ct_name", "bgd_token")

def _bgd_active(request) -> bool:
    """Chỉ true khi có cờ session và ĐANG ở route score-bgd (đi từ QR)."""
    return (
        request.session.get("bgd_mode") == "score"
        and getattr(request, "resolver_match", None)
        and request.resolver_match.url_name == "score-bgd"
    )

def _pick_competition(preferred_id: int | None):
    """
    Chọn cuộc thi dùng cho chấm điểm:
    1) Nếu preferred_id được truyền và tồn tại → dùng.
    2) Nếu có cuộc thi đang bật và có ít nhất 1 bài → dùng.
    3) Nếu không, lấy cuộc thi gần nhất có ít nhất 1 bài.
    4) Nếu vẫn không có → None.
    """
    qs = CuocThi.objects.all().order_by("-trangThai", "-id")
    if preferred_id:
        ct = qs.filter(id=preferred_id).first()
        if ct:
            return ct
    active = qs.filter(trangThai=True).first()
    if active and BaiThi.objects.filter(vongThi__cuocThi=active).exists():
        return active
    fallback = qs.filter(vong_thi__bai_thi__isnull=False).distinct().first()
    return fallback
def _session_judge(request):
    """Lấy giám khảo từ session (ưu tiên)."""
    jid = request.session.get("judge_pk") or request.session.get("judge_id")
    if jid:
        return GiamKhao.objects.filter(pk=jid).first()
    return None

def _current_judge(request):
    """
    Lấy giám khảo đang đăng nhập để ghi vào phiếu.
    - Ưu tiên lấy từ session: request.session['judge_id'].
    - Nếu không có session, chỉ THỬ khớp tài khoản hiện tại với GiamKhao đã tồn tại
      (email hoặc username). Tuyệt đối KHÔNG tự tạo mới.
    - Nếu vẫn không có -> trả None để view báo 401.
    """
    # 1) Ưu tiên giám khảo đang chọn trong session
    gk = _session_judge(request)
    if gk:
        return gk

    # 2) Thử map từ user hiện tại sang GiamKhao có sẵn (không tạo mới)
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        email = (getattr(user, "email", "") or "").strip()
        username = (getattr(user, "username", "") or "").strip()

        if email:
            gk = GiamKhao.objects.filter(email__iexact=email).first()
            if gk:
                return gk
        if username:
            gk = GiamKhao.objects.filter(maNV__iexact=username).first()
            if gk:
                return gk
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            gk = (
                GiamKhao.objects.filter(role="ADMIN")
                .filter(Q(email__iexact=email) | Q(maNV__iexact=username))
                .first()
                or GiamKhao.objects.filter(role="ADMIN").order_by("maNV").first()
            )
            if gk:
                return gk

    # 3) Không tìm thấy -> để view xử lý (401)
    return None


def _active_competition():
    """
    Lấy 'Cuộc thi đang bật' ưu tiên trangThai=True; nếu không có, trả None.
    """
    return CuocThi.objects.filter(trangThai=True).order_by("-id").first()

def _judge_is_admin(judge: GiamKhao | None) -> bool:
    return bool(judge and str(getattr(judge, "role", "")).upper() == "ADMIN")
def _normalize_no_diacritics(s: str) -> str:
    """
    Bỏ dấu + lowercase + bỏ khoảng trắng để so sánh tên cuộc thi.
    'Chung Kết' -> 'chungket', 'CK' -> 'ck'
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower().strip().replace(" ", "")


def _is_chung_ket(ct: CuocThi | None) -> bool:
    """
    Kiểm tra 1 Cuộc thi có phải 'Chung Kết' / 'Chung Ket' / 'CK' (không phân biệt hoa/thường, có/không dấu).
    """
    if not ct:
        return False
    norm = _normalize_no_diacritics(getattr(ct, "tenCuocThi", ""))
    return norm in {"chungket", "ck"}


def _judge_is_bgd(judge: GiamKhao | None) -> bool:
    """
    Giám khảo đồng thời là BGD nếu:
      - có bản ghi BanGiamDoc trùng maBGD = maNV
      - ưu tiên khớp thêm họ tên (không phân biệt hoa/thường).
    """
    if not judge:
        return False
    try:
        qs = BanGiamDoc.objects.filter(maBGD=judge.maNV)
        if not qs.exists():
            return False
        if qs.filter(ten__iexact=judge.hoTen).exists():
            return True
        # fallback: chỉ cần đúng mã
        return True
    except Exception:
        return False

def _assigned_bai_qs(ct: CuocThi, judge: GiamKhao | None, vt: VongThi | None = None, bgd_active: bool = False):
    """
    Trả về queryset BaiThi theo cuộc thi/vòng thi.
    - ADMIN: thấy tất cả.
    - BGD: CHỈ khi bgd_active=True (đi từ QR) VÀ cuộc thi là 'Chung Kết' → thấy tất cả.
    - JUDGE thường: chỉ thấy những bài được phân công (GiamKhaoBaiThi).
    """
    base = BaiThi.objects.filter(vongThi__cuocThi=ct)
    if vt:
        base = base.filter(vongThi=vt)

    if not judge:
        return base.none()

    if _judge_is_admin(judge):
        return base

    # 🔒 Chỉ nới quyền BGD khi vào đúng luồng QR và là cuộc thi Chung Kết
    if bgd_active and _judge_is_bgd(judge) and _is_chung_ket(ct):
        return base

    return base.filter(giam_khao_duoc_chi_dinh__giamKhao=judge)


# after
def _load_form_data(selected_ts, ct, request):
    """
    Trả về (structure, total_max) để render form chấm điểm.
    structure: [{vong, bai_list:[{id, code, ten, max, type, current}]}]
    total_max: int
    """
    if not ct:
        return [], 0
    
    judge = _current_judge(request)
    vongs = list(VongThi.objects.filter(cuocThi=ct).order_by("id"))
    bai_by_vong = []
    total_max = 0

    # điểm hiện có của thí sinh (ưu tiên GK hiện tại)
    score_map = {}
    if selected_ts:
        judge = _current_judge(request)
        qs = PhieuChamDiem.objects.filter(thiSinh=selected_ts, cuocThi=ct)
        score_map_avg = {
            r["baiThi_id"]: float(r["avg"])
            for r in qs.values("baiThi_id").annotate(avg=Avg("diem"))
        }
        score_map_gk = {
            p.baiThi_id: p.diem
            for p in qs
            if judge and p.giamKhao_id == getattr(judge, "pk", None)
        }
        score_map.update(score_map_avg)
        score_map.update(score_map_gk)

        time_map = {p.baiThi_id: getattr(p, "thoiGian", 0) for p in qs}

    for vt in vongs:
        bais = []
        
        bgd_on = _bgd_active(request)
        for bt in (
            _assigned_bai_qs(ct, judge, vt=vt, bgd_active=bgd_on)
            .order_by("id")
            .prefetch_related("time_rules", "template_sections__items")
        ):

            if _is_time(bt):
                rules = list(bt.time_rules.all()) if hasattr(bt, "time_rules") else []
                this_max = 20
                b_type = "TIME"
                rules_payload = [{"s": r.start_seconds, "e": r.end_seconds, "score": r.score} for r in rules]
                rules_json = json.dumps(rules_payload, ensure_ascii=False)
            else:
                # TEMPLATE: tổng điểm = tổng item.max_score
                if _is_template(bt):
                    this_max = sum(
                        i.max_score
                        for s in bt.template_sections.all()
                        for i in s.items.all()
                    )
                    b_type = "TEMPLATE"
                else:  # POINTS
                    this_max = bt.cachChamDiem
                    b_type = "POINTS"
                rules_json = "[]"


            # ➕ QUAN TRỌNG: cộng vào tổng tối đa
            total_max += this_max

            bais.append({
                "id": bt.id,
                "code": bt.ma,
                "ten": f"{vt.tenVongThi} – {bt.tenBaiThi}",
                "max": this_max,
                "type": b_type,
                "rules": rules_json,
                "current": score_map.get(bt.id, 0.0) if selected_ts else None,
                "time_current": (time_map.get(bt.id) if selected_ts and _is_time(bt) else None),
            })
        bai_by_vong.append({"vong": vt, "bai_list": bais})


    # 🔒 luôn trả về tuple
    return bai_by_vong, total_max

# ==== Helpers xác định loại chấm ====
def _score_type(bt) -> str:
    v = getattr(bt, "phuongThucCham", None)
    if v is None:
        return "POINTS"
    s = str(v).strip().upper()
    # Nếu model lưu dạng số: 0=POINTS, 1=TEMPLATE, 2=TIME (bạn có thể đổi nếu mapping khác)
    if s in {"TIME", "2"}:
        return "TIME"
    if s in {"TEMPLATE", "1"}:
        return "TEMPLATE"
    return "POINTS"

def _is_template(bt) -> bool:
    return _score_type(bt) == "TEMPLATE"


def _is_time(bt) -> bool:
    return _score_type(bt) == "TIME"


def _is_points(bt) -> bool:
    return _score_type(bt) == "POINTS"

def _parse_seconds(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if ":" in s:
        try:
            m, sec = s.split(":")
            return int(m)*60 + int(sec)
        except Exception:
            return None
    try:
        return int(float(s))
    except Exception:
        return None

def _resolve_thi_sinh_from_query(q: str):
    if not q:
        return None
    raw = q.strip()
    # Nếu người dùng chọn từ suggestion kiểu "TS001 — Nguyễn Văn A"
    if "—" in raw:
        maybe_code = raw.split("—", 1)[0].strip()
        ts = ThiSinh.objects.filter(maNV__iexact=maybe_code).first()
        if ts:
            return ts
    # Thử mã NV (tách token đầu)
    token = raw.split()[0]
    ts = ThiSinh.objects.filter(maNV__iexact=token).first()
    if ts:
        return ts
    # Cuối cùng thử khớp tên (exact trước)
    ts = ThiSinh.objects.filter(hoTen__iexact=raw).first()
    if ts:
        return ts
    # Cho “tên chứa” để tăng độ linh hoạt (lấy người đầu)
    return ThiSinh.objects.filter(hoTen__icontains=raw).order_by("maNV").first()



@ensure_csrf_cookie
@judge_required
@require_http_methods(["GET", "POST"])
def score_view(request):
    # Xử lý AJAX lưu điểm (không reload)
    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return HttpResponseBadRequest("Invalid JSON")

        ts_code   = (payload.get("thiSinh") or "").strip()
        ct_id     = payload.get("ct_id")
        vt_id     = payload.get("vt_id")
        bt_id     = payload.get("bt_id")
        scores    = payload.get("scores") or {}
        done      = payload.get("done")   or {}
        times     = payload.get("times")  or {}
        tpl_times = payload.get("tpl_times") or {}

        thi_sinh = ThiSinh.objects.filter(
            Q(maNV__iexact=ts_code) | Q(hoTen__iexact=ts_code)
        ).first()
        if not thi_sinh:
            return JsonResponse({"ok": False, "message": "Không tìm thấy thí sinh."}, status=400)

        ct = _pick_competition(int(ct_id)) if ct_id else _active_competition()
        if not ct:
            return JsonResponse({"ok": False, "message": "Chưa có cuộc thi hợp lệ."}, status=400)

        judge = _current_judge(request)
        if not judge:
            return JsonResponse({"ok": False, "message": "Bạn chưa đăng nhập giám khảo."}, status=401)

        # 🔒 BẮT BUỘC phải có vt_id & bt_id
        if not (vt_id and bt_id):
            return JsonResponse({
                "ok": False,
                "message": "Vui lòng chọn Vòng thi và đúng 1 Bài thi trước khi lưu điểm."
            }, status=400)

        try:
            vt_obj = VongThi.objects.get(pk=int(vt_id), cuocThi=ct)
        except VongThi.DoesNotExist:
            return JsonResponse({
                "ok": False,
                "message": "Vòng thi không hợp lệ trong cuộc thi này."
            }, status=400)

        try:
            bt_obj = BaiThi.objects.get(pk=int(bt_id), vongThi=vt_obj)
        except BaiThi.DoesNotExist:
            return JsonResponse({
                "ok": False,
                "message": "Bài thi không hợp lệ trong vòng đã chọn."
            }, status=400)

        bai_qs = (
            _assigned_bai_qs(ct, judge, vt=vt_obj, bgd_active=_bgd_active(request))
            .filter(pk=bt_obj.pk)
            .prefetch_related("time_rules", "template_sections__items")
        )

        if not bai_qs.exists():
            return JsonResponse({
                "ok": False,
                "message": "Bạn không được phân công chấm bài thi này."
            }, status=403)

        bai_map = {b.id: b for b in bai_qs}

        def _tpl_max(b):
            return sum(i.max_score for s in b.template_sections.all() for i in s.items.all())

        limit_map = {}
        for b in bai_qs:
            if _is_template(b):
                limit_map[b.id] = _tpl_max(b)
            elif _is_points(b):
                limit_map[b.id] = b.cachChamDiem
            else:  # TIME
                limit_map[b.id] = 0



        created = updated = 0
        errors = []
        saved_scores = {}  # {bt_id: điểm_đã_lưu}

        force = bool(payload.get("force"))
        incoming_ids = set()

        incoming_ids.update(int(k) for k in (scores or {}).keys() if str(k).isdigit())
        incoming_ids.update(int(k) for k in (done or {}).keys()   if str(k).isdigit())
        incoming_ids.update(int(k) for k in (times or {}).keys()  if str(k).isdigit())

        if incoming_ids:
            existed_qs = PhieuChamDiem.objects.filter(
                thiSinh=thi_sinh, cuocThi=ct, baiThi_id__in=list(incoming_ids)
            ).values_list("baiThi__ma", flat=True)
            existed_codes = list(existed_qs)

            if existed_codes and not force:
                return JsonResponse({
                    "ok": False,
                    "code": "already_scored",
                    "message": "Thí sinh này đã được chấm điểm. Bạn có chắc chắn muốn chấm lại không?",
                    "existed_tests": existed_codes,
                }, status=409)


        with transaction.atomic():
            # 1) POINTS
            for s_id, raw in scores.items():
                try:
                    btid = int(s_id)
                except ValueError:
                    continue

                bt = bai_map.get(btid)
                # Cho phép nhập điểm cho cả POINTS và TEMPLATE (điểm tổng)
                if not bt or not (_is_points(bt) or _is_template(bt)):
                    continue

                diem = None
                try:
                    diem = int(raw)
                except (TypeError, ValueError):
                    errors.append(f"Bài {bt.ma}: điểm không hợp lệ.")
                    continue

                maxp = limit_map.get(btid, 0)
                if diem is None or diem < 0 or diem > maxp:
                    errors.append(f"Bài {bt.ma}: 0..{maxp}.")
                    continue

                extra = {}
                if _is_template(bt):
                    t = tpl_times.get(str(btid)) or tpl_times.get(btid)
                    sec = _parse_seconds(t)
                    if sec is not None and sec >= 0:
                        extra["thoiGian"] = int(sec)

                obj, was_created = PhieuChamDiem.objects.update_or_create(
                    thiSinh=thi_sinh, baiThi=bt, cuocThi=ct,
                    defaults=dict(vongThi=bt.vongThi, diem=diem, giamKhao=judge, **extra)
                )
                created += int(was_created)
                updated += int(not was_created)
                saved_scores[btid] = diem

                # Áp dụng bonus 100/0 cho vòng đặc biệt (nếu đủ 2 người trong cặp đã chấm)
                _apply_special_round_bonus_if_ready(
                    bt=bt,
                    thi_sinh=thi_sinh,
                    judge=judge,
                    raw_total=diem,
                    raw_time=int(extra.get("thoiGian", 0)) if extra.get("thoiGian") is not None else 0,
                )




            # 2) TIME (chuẩn hóa theo yêu cầu)
            for bt in bai_qs:
                if not _is_time(bt):
                    continue
                btid = bt.id
                has_input = (
                    str(btid) in (done or {}) or btid in (done or {}) or
                    str(btid) in (times or {}) or btid in (times or {})
                )
                if not has_input:
                    continue
                is_done = bool(done.get(str(btid)) or done.get(btid))

                if not is_done:
                    obj, was_created = PhieuChamDiem.objects.update_or_create(
                        thiSinh=thi_sinh, baiThi=bt, cuocThi=ct,
                        defaults=dict(
                            vongThi=bt.vongThi,
                            diem=0,
                            thoiGian=0,
                            giamKhao=judge
                        )
                    )
                    created += int(was_created); updated += int(not was_created)
                    saved_scores[btid] = 0

                    # Thử áp dụng bonus nếu đây là vòng đặc biệt
                    _apply_special_round_bonus_if_ready(
                        bt=bt,
                        thi_sinh=thi_sinh,
                        judge=judge,
                        raw_total=0,
                        raw_time=0,
                    )
                    continue


                # ĐANG TICK → LƯU thời gian + điểm
                # Cho phép "00:00" (seconds = 0) là hợp lệ
                raw_t = times.get(str(btid)) or times.get(btid)
                seconds = _parse_seconds(raw_t)
                if seconds is None or seconds < 0:
                    errors.append(f"Bài {bt.ma}: thời gian không hợp lệ (mm:ss hoặc giây).")
                    continue

                try:
                    seconds = int(seconds or 0)
                except Exception:
                    seconds = 0

                # bonus theo rule; không match thì bonus = 0
                bonus = 0
                for r in bt.time_rules.all():
                    if r.start_seconds <= seconds <= r.end_seconds:
                        bonus = int(r.score)
                        break
                diem = min(20, 10 + bonus)   # tổng = 10 + bonus (kẹp 20)

                obj, was_created = PhieuChamDiem.objects.update_or_create(
                    thiSinh=thi_sinh, baiThi=bt, cuocThi=ct,
                    defaults=dict(
                        vongThi=bt.vongThi,
                        diem=diem,
                        thoiGian=seconds,
                        giamKhao=judge
                    )
                )
                created += int(was_created); updated += int(not was_created)
                saved_scores[btid] = diem

                # Thử áp dụng bonus 100/0 cho vòng đặc biệt
                _apply_special_round_bonus_if_ready(
                    bt=bt,
                    thi_sinh=thi_sinh,
                    judge=judge,
                    raw_total=diem,
                    raw_time=int(seconds or 0),
                )

        if errors:
            return JsonResponse({
                "ok": False,
                "message": f"Điểm số không hợp lệ ở {len(errors)} mục.",
                "errors": errors,
                "saved_scores": saved_scores,
            }, status=400)
        else:
            return JsonResponse({
                "ok": True,
                "message": f"Đã lưu điểm số thí sinh.",
                "errors": errors,
                "saved_scores": saved_scores,
                "debug": {
                    "count_all": len(bai_qs),
                    "count_points": sum(1 for b in bai_qs if _is_points(b)),
                    "count_time": sum(1 for b in bai_qs if _is_time(b)),
                }
            })

    # GET: render trang
    query = (request.GET.get("q") or "").strip()
    selected_code = (request.GET.get("ts") or "").strip()
    ct_param = request.GET.get("ct")
    vt_param = request.GET.get("vt")
    bt_param = request.GET.get("bt")
    # Nếu vào trang chấm thường → tắt dấu vết BGD từ QR
    if getattr(request, "resolver_match", None) and request.resolver_match.url_name == "score":
        for k in BGD_SESSION_KEYS:
            request.session.pop(k, None)

    # === BGD MODE: chỉ bật khi vào /score/bgd/ (đi từ QR) ===
    is_bgd_score = _bgd_active(request)
    ck_candidates = []
    if is_bgd_score:
        ck_id = request.session.get("bgd_ct_id")
        if ck_id:
            ct_param = str(ck_id)  # ép về CK (dù người dùng sửa URL)
            ck_candidates = list(
                ThiSinh.objects.filter(cuocThi__id=ck_id)
                .order_by("maNV").values("maNV", "hoTen", "donVi")[:1000]
            )



    # AJAX gợi ý: chỉ trả JSON {maNV, hoTen}; bắt buộc phải chọn Cuộc thi đang bật
    if request.GET.get("ajax") in ("suggest", "1"):
        query = (request.GET.get("q") or "").strip()
        if not query:
            return JsonResponse([], safe=False)

        ct_id = request.GET.get("ct")
        ct = CuocThi.objects.filter(trangThai=True, id=ct_id).first()
        if not ct:
            # Chưa chọn CT hoặc CT không hợp lệ/không bật -> không gợi ý
            return JsonResponse([], safe=False)

        qs = (
            ThiSinh.objects
            .filter(cuocThi=ct)
            .filter(Q(maNV__icontains=query) | Q(hoTen__icontains=query))
            .order_by("maNV")
            .values("maNV", "hoTen")[:20]
        )
        return JsonResponse(list(qs), safe=False)




    # gợi ý thí sinh (server-render) — lọc theo CT đang bật nếu có ct_param
    suggestions = []
    if query:
        ct_for_suggest = CuocThi.objects.filter(trangThai=True, id=ct_param).first() if ct_param else None
        base_qs = ThiSinh.objects.all()
        if ct_for_suggest:
            base_qs = base_qs.filter(cuocThi=ct_for_suggest)  # ← lọc theo mact ở ThiSinh
        suggestions = list(
            base_qs.filter(
                Q(maNV__icontains=query) | Q(hoTen__icontains=query)
            ).order_by("maNV").values("maNV", "hoTen")[:20]
        )




    selected_ts = None
    if selected_code:
        selected_ts = ThiSinh.objects.filter(
            Q(maNV__iexact=selected_code) | Q(hoTen__iexact=selected_code)
        ).first()
    elif query:
        # Người dùng bấm Tìm với ô textfield "q"
        selected_ts = _resolve_thi_sinh_from_query(query)

    # Chỉ lấy danh sách CT đang bật...
    cuoc_this_active = CuocThi.objects.filter(trangThai=True).order_by("-id")
    ct = cuoc_this_active.filter(id=ct_param).first() if ct_param else None

   # ✅ Nếu thí sinh không thuộc cuộc thi đang chọn → bỏ chọn
    if ct and selected_ts:

        if not ThiSinhCuocThi.objects.filter(thiSinh=selected_ts, cuocThi=ct).exists():
            selected_ts = None
    # === NEW: cung cấp danh sách Vòng thi theo CT, và Bài thi theo Vòng ===
    rounds = []
    tests = []
    selected_vt = None
    selected_bt = None

    judge_for_render = _current_judge(request)
    if ct:
        # Chỉ vòng có bài hợp lệ với judge
        vt_qs = VongThi.objects.filter(cuocThi=ct).order_by("id")
        rounds = []
        for vt in vt_qs:
            if _judge_is_admin(judge_for_render) or _assigned_bai_qs(ct, judge_for_render, vt=vt, bgd_active=_bgd_active(request)).exists():
                rounds.append({"id": vt.id, "tenVongThi": vt.tenVongThi})
        if vt_param:
            selected_vt = VongThi.objects.filter(cuocThi=ct, id=vt_param).first()
            if selected_vt:
                tests_qs = _assigned_bai_qs(ct, judge_for_render, vt=selected_vt, bgd_active=_bgd_active(request)).order_by("id")
                tests = list(tests_qs.values("id", "ma", "tenBaiThi"))
                if bt_param:
                    selected_bt = BaiThi.objects.filter(vongThi=selected_vt, id=bt_param).first()


    # === Chỉ load form khi đã có thí sinh, CT và ĐÃ chọn đúng 1 Bài thi ===
    structure, total_max = [], 0
    if ct and selected_ts and bt_param:
        structure, total_max = _load_form_data(selected_ts, ct, request)

        # lọc theo vòng nếu có
        if selected_vt:
            structure = [
                blk for blk in structure
                if getattr(blk.get("vong"), "id", None) == selected_vt.id
            ]

        # lọc đúng 1 bài thi
        if selected_bt:
            new_structure = []
            for blk in structure:
                filtered = [b for b in blk.get("bai_list", []) if b.get("id") == selected_bt.id]
                if filtered:
                    new_structure.append({"vong": blk.get("vong"), "bai_list": filtered})
            structure = new_structure

        # Tính lại tổng tối đa đúng với 1 bài đang chấm
        total_max = sum(
            b.get("max", 0)
            for blk in structure
            for b in blk.get("bai_list", [])
        )
    else:
        # không có bt_param -> không hiển thị gì để chấm
        structure, total_max = [], 0


    # --- AJAX: meta cho dropdown động ---
    if request.GET.get("ajax") == "meta":
        ct_id = request.GET.get("ct")
        vt_id = request.GET.get("vt")
        data = {"rounds": [], "tests": []}

        if ct_id:
            ct_obj = CuocThi.objects.filter(trangThai=True, id=ct_id).first()
            if ct_obj:
                judge = _current_judge(request)
                # Chỉ những vòng có ít nhất 1 bài hợp lệ với judge
                vt_qs = (VongThi.objects
                         .filter(cuocThi=ct_obj)
                         .order_by("id"))
                rounds = []
                for vt in vt_qs:
                    if _judge_is_admin(judge) or _assigned_bai_qs(ct_obj, judge, vt=vt, bgd_active=_bgd_active(request)).exists():
                        rounds.append({"id": vt.id, "tenVongThi": vt.tenVongThi})
                data["rounds"] = rounds

                if vt_id:
                    vt_obj = VongThi.objects.filter(cuocThi=ct_obj, id=vt_id).first()
                    if vt_obj:
                        tests_qs = _assigned_bai_qs(ct_obj, judge, vt=vt_obj, bgd_active=_bgd_active(request)).order_by("id")
                        data["tests"] = list(
                            tests_qs.values("id", "ma", "tenBaiThi")
                        )
        return JsonResponse(data)

    return render(request, "score/index.html", {
        "ct": ct,
        "selected_ct_id": int(ct_param) if ct_param else None,
        "structure": structure,
        "total_max": total_max,
        "query": query,
        "suggestions": suggestions,
        "selected_ts": selected_ts,
        # chỉ hiển thị các cuộc thi đang bật
        "competitions": list(
            CuocThi.objects.filter(trangThai=True).order_by("-id")
            .values("id","ma","tenCuocThi","trangThai")
        ),
        # NEW: dữ liệu cho dropdown phụ thuộc
        "rounds": rounds,
        "tests": tests,
        "selected_vt_id": selected_vt.id if selected_vt else None,
        "selected_bt_id": selected_bt.id if selected_bt else None,
        "is_bgd_score": is_bgd_score,
        "locked_ct_name": request.session.get("bgd_ct_name") if is_bgd_score else None,
        "bgd_candidates": ck_candidates,  # list dict {maNV, hoTen, donVi}

        "range60": range(60),
    })


    
@judge_required
@require_http_methods(["GET", "POST"])
def score_template_api(request, btid: int):
    bt = get_object_or_404(BaiThi.objects.prefetch_related("template_sections__items"), pk=btid)
    if str(bt.phuongThucCham).upper() != "TEMPLATE":
        return JsonResponse({"ok": False, "message": "Bài thi này không phải chấm theo mẫu."}, status=400)

    judge = _current_judge(request)
    if not judge:
        return JsonResponse({"ok": False, "message": "Bạn chưa đăng nhập giám khảo."}, status=401)

    # Xác định cuộc thi của bài thi này
    ct_of_bt = getattr(bt.vongThi, "cuocThi", None)

    # Admin: luôn được
    # BGD (đồng thời là Giám khảo) trong 'Chung Kết': cũng luôn được
    # Admin: luôn được
    # BGD: CHỈ khi đi từ QR (/score/bgd/) và là 'Chung Kết'
    bgd_on = _bgd_active(request)
    if not (_judge_is_admin(judge) or (bgd_on and _judge_is_bgd(judge) and _is_chung_ket(ct_of_bt))):
        if not GiamKhaoBaiThi.objects.filter(giamKhao=judge, baiThi=bt).exists():
            return JsonResponse({"ok": False, "message": "Bạn không được phân công chấm bài này."}, status=403)


    if request.method == "GET":
        try:
            # kiểm tra loại bài là TEMPLATE 
            if not _is_template(bt):
                return JsonResponse({"ok": False, "message": "Bài thi này không phải chấm theo mẫu."}, status=400)

            sections = []
            total_max = 0

            # Lấy danh sách section theo 2 cách để tránh lệ thuộc related_name
            try:
                sec_qs = bt.template_sections.all().order_by("stt", "id")
            except Exception:
                try:
                    sec_qs = BaiThiTemplateSection.objects.filter(baiThi=bt).order_by("stt", "id")
                except Exception:
                    return JsonResponse({"ok": False, "message": "Không tìm thấy quan hệ sections cho bài thi này."}, status=500)

            for s in sec_qs:
                # Lấy danh sách item theo 2 cách (an toàn với related_name)
                try:
                    item_qs = s.items.all().order_by("stt", "id")
                except Exception:
                    try:

                        item_qs = BaiThiTemplateItem.objects.filter(section=s).order_by("stt", "id")
                    except Exception:
                        return JsonResponse({"ok": False, "message": f"Không tìm thấy items cho section {getattr(s,'id','?')}."}, status=500)

                items = []
                for i in item_qs:
                    items.append({
                        "id": i.id,
                        "stt": getattr(i, "stt", None),
                        "content": getattr(i, "content", ""),
                        "max": int(getattr(i, "max_score", 0) or 0),
                        "note": getattr(i, "note", "") or "",
                    })
                    total_max += int(getattr(i, "max_score", 0) or 0)

                sections.append({
                    "id": s.id,
                    "stt": getattr(s, "stt", None),
                    "title": getattr(s, "title", ""),
                    "note": getattr(s, "note", "") or "",
                    "items": items,
                })

            return JsonResponse({
                "ok": True,
                "bt": {"id": bt.id, "code": bt.ma, "name": bt.tenBaiThi},
                "total_max": total_max,
                "sections": sections,
            })

        except Exception as e:
            # tránh 500 trả HTML → trả JSON để frontend hiển thị rõ lỗi
            return JsonResponse({"ok": False, "message": f"Server error: {e.__class__.__name__}: {e}"}, status=500)


    # POST: nhận điểm từng item, tính tổng và lưu vào Phiếu chấm (mức tổng)
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    ts_code = (payload.get("thiSinh") or "").strip()
    ct_id   = payload.get("ct_id")
    item_scores = payload.get("items") or {}   # {"<item_id>": <điểm số>}

    # 1) Ưu tiên Mã NV
    thi_sinh = ThiSinh.objects.filter(maNV__iexact=ts_code).first()

    # 2) Nếu không có, cho phép gõ tên để lưu
    if not thi_sinh:
        # Ưu tiên trong cuộc thi hiện tại (nếu có)
        by_name_qs = ThiSinh.objects.filter(hoTen__iexact=ts_code)
        if ct_id:
            ct_obj = _pick_competition(int(ct_id))
            if ct_obj:
                by_name_qs = by_name_qs.filter(phieuchamdiem__cuocThi=ct_obj).distinct() or by_name_qs
        thi_sinh = by_name_qs.first()

    if not thi_sinh:
        return JsonResponse({"ok": False, "message": "Không tìm thấy thí sinh theo tên đã nhập."}, status=400)


    # Chỉ chấm vào CT đang bật
    ct = CuocThi.objects.filter(trangThai=True, id=ct_id).first() if ct_id else _active_competition()
    if not ct:
        return JsonResponse({"ok": False, "message": "Chưa có cuộc thi hợp lệ (chỉ chấm vào cuộc thi đang bật)."}, status=400)


    judge = _current_judge(request)
    if not judge:
        return JsonResponse({"ok": False, "message": "Bạn chưa đăng nhập giám khảo."}, status=401)

    # Map max cho từng item
    max_map = {}
    for s in bt.template_sections.all():
        for i in s.items.all():
            max_map[i.id] = int(i.max_score or 0)

    errors = []
    total = 0
    normalized = {}
    for raw_id, raw_val in item_scores.items():
        try:
            iid = int(raw_id)
        except Exception:
            continue
        if iid not in max_map:
            continue
        try:
            val = int(float(raw_val))
        except Exception:
            errors.append(f"Mục {iid}: điểm không hợp lệ.")
            continue

        max_allowed = max_map[iid]
        if val < 0 or val > max_allowed:
            errors.append(f"Mục {iid}: chỉ cho phép 0..{max_allowed}.")
            continue

        normalized[iid] = val
        total += val

    if errors:
        return JsonResponse({
            "ok": False,
            "message": "Có điểm không hợp lệ trong phiếu chấm theo mẫu.",
            "errors": errors
        }, status=400)


    # 👇 parse "mm:ss" về giây, trước khi lưu
    time_str = payload.get("time")
    total_seconds = 0
    if time_str and ":" in time_str:
        try:
            m, s = map(int, time_str.split(":"))
            total_seconds = m * 60 + s
        except ValueError:
            total_seconds = 0

    with transaction.atomic():
        obj, created = PhieuChamDiem.objects.update_or_create(
            thiSinh=thi_sinh, giamKhao=judge, baiThi=bt,
            defaults=dict(
                cuocThi=ct,
                vongThi=bt.vongThi,
                diem=total,
                thoiGian=total_seconds,  # 👈 lưu thời gian hoàn thành (raw để so sánh)
            )
        )

        # Nếu là vòng đặc biệt, thử áp dụng điểm thưởng (special_bonus_score) 100/0
        _apply_special_round_bonus_if_ready(
            bt=bt,
            thi_sinh=thi_sinh,
            judge=judge,
            raw_total=total,
            raw_time=total_seconds,
        )

    return JsonResponse({
        "ok": True,
        "saved_total": total,
        "message": f"Đã lưu {total} điểm cho {bt.ma} (TEMPLATE).",
    })
    
# def _apply_special_round_bonus_if_ready(bt, thi_sinh, judge, raw_total, raw_time):
    """
    Nếu bài thi thuộc vòng đặc biệt:
    - Tìm cặp SpecialRoundPairMember của thí sinh trong vòng đó
    - Kiểm tra người còn lại trong cặp đã có phiếu chấm TEMPLATE cùng bài thi, cùng giám khảo chưa
    - Nếu cả 2 đã chấm:
        • So sánh raw_total
        • Nếu bằng nhau, so sánh raw_time (ít thời gian hơn thắng)
        • Người thắng: nhận vt.special_bonus_score
        • Người thua: nhận 0
    Lưu trực tiếp vào PhieuChamDiem (field diem).
    """
    vt = getattr(bt, "vongThi", None)
    if not vt or not getattr(vt, "is_special_bonus_round", False):
        return  # không phải vòng đặc biệt → bỏ qua

    bonus = getattr(vt, "special_bonus_score", 100) or 100

    # Xác định entry cặp của thí sinh trong vòng này
    try:
        member = SpecialRoundPairMember.objects.select_related("pair", "thiSinh").get(
            pair__vongThi=vt,
            thiSinh=thi_sinh,
        )
    except SpecialRoundPairMember.DoesNotExist:
        return  # thí sinh này không nằm trong top 20/cặp đặc biệt → bỏ qua

    # Lấy đối thủ trong cùng cặp
    opponent_member = (
        SpecialRoundPairMember.objects.select_related("thiSinh")
        .filter(pair=member.pair)
        .exclude(thiSinh=thi_sinh)
        .first()
    )
    if not opponent_member:
        return  # cặp không đủ 2 người → không so sánh được

    opponent = opponent_member.thiSinh

    # Lấy phiếu chấm của cả 2 cho bài thi này, cùng giám khảo
    from .models import PhieuChamDiem  # đảm bảo import an toàn nếu file thay đổi

    try:
        phieu_self = PhieuChamDiem.objects.get(
            thiSinh=thi_sinh,
            giamKhao=judge,
            baiThi=bt,
        )
    except PhieuChamDiem.DoesNotExist:
        return

    phieu_opp = PhieuChamDiem.objects.filter(
        thiSinh=opponent,
        giamKhao=judge,
        baiThi=bt,
    ).first()

    # Nếu đối thủ chưa được chấm → chưa đủ 2 điểm để so sánh
    if not phieu_opp:
        return

    # Điểm & thời gian raw dùng để so sánh
    score_self = float(raw_total)
    time_self = int(raw_time or 0)

    score_opp = float(phieu_opp.diem or 0)
    time_opp = int(phieu_opp.thoiGian or 0)

    # Xác định người thắng
    winner = None
    loser = None

    if score_self > score_opp:
        winner, loser = phieu_self, phieu_opp
    elif score_self < score_opp:
        winner, loser = phieu_opp, phieu_self
    else:
        # Điểm bằng nhau → so sánh thời gian
        if time_self < time_opp:
            winner, loser = phieu_self, phieu_opp
        elif time_self > time_opp:
            winner, loser = phieu_opp, phieu_self
        else:
            # Hoà tuyệt đối → tạm thời cho cả 2 = 0 (tuỳ bạn muốn xử lý sao thêm)
            PhieuChamDiem.objects.filter(pk=phieu_self.pk).update(diem=0)
            PhieuChamDiem.objects.filter(pk=phieu_opp.pk).update(diem=0)
            return

    # Áp dụng điểm thưởng: thắng = bonus, thua = 0
    if winner and loser:
        PhieuChamDiem.objects.filter(pk=winner.pk).update(diem=bonus)
        PhieuChamDiem.objects.filter(pk=loser.pk).update(diem=0)
        
        
def _apply_special_round_bonus_if_ready(bt, thi_sinh, judge, raw_total, raw_time):
    """
    Logic vòng đặc biệt:
    - Chỉ chạy nếu vongThi.is_special_bonus_round == True
    - Tìm cặp SpecialRoundPairMember của thí sinh trong vòng đó
    - Khi cả 2 người trong cặp đã có Phiếu chấm (cùng bài, cùng GK):
        + Ghi log điểm raw của cả 2 vào SpecialRoundScoreLog
        + So sánh raw_score (nếu bằng thì so raw_time, ít hơn thắng)
        + Cập nhật PhieuChamDiem:
              người thắng  = bonus (special_bonus_score)
              người thua   = 0
    """

    vt = getattr(bt, "vongThi", None)
    if not vt or not getattr(vt, "is_special_bonus_round", False):
        return  # không phải vòng đặc biệt

    ct = getattr(vt, "cuocThi", None)
    if not ct or not judge or not thi_sinh:
        return

    bonus = int(getattr(vt, "special_bonus_score", 100) or 100)

    # 1. Lấy member của thí sinh trong cặp
    try:
        member = SpecialRoundPairMember.objects.select_related("pair", "thiSinh").get(
            pair__vongThi=vt,
            thiSinh=thi_sinh,
        )
    except SpecialRoundPairMember.DoesNotExist:
        return  # không nằm trong cặp đặc biệt

    pair = member.pair

    # 2. Tìm đối thủ trong cùng cặp
    opponent_member = (
        SpecialRoundPairMember.objects
        .select_related("thiSinh")
        .filter(pair=pair)
        .exclude(pk=member.pk)
        .first()
    )
    if not opponent_member:
        return

    opponent = opponent_member.thiSinh

    # 3. Lấy 2 phiếu chấm (cùng bài, cùng vòng, cùng GK)
    sheets = list(
        PhieuChamDiem.objects.filter(
            cuocThi=ct,
            vongThi=vt,
            baiThi=bt,
            giamKhao=judge,
            thiSinh__in=[thi_sinh, opponent],
        )
    )
    if len(sheets) < 2:
        # mới chấm xong 1 người → chưa so sánh
        return

    sheet_self = next((s for s in sheets if s.thiSinh_id == thi_sinh.pk), None)
    sheet_opp  = next((s for s in sheets if s.thiSinh_id == opponent.pk), None)

    if not sheet_self or not sheet_opp:
        return

    # 4. Ghi log raw cho cả 2
    SpecialRoundScoreLog.objects.create(
        cuocThi=ct,
        vongThi=vt,
        baiThi=bt,
        pair_member=member,
        giamKhao=judge,
        raw_score=int(sheet_self.diem or 0),
        raw_time=int(getattr(sheet_self, "thoiGian", 0) or 0),
    )
    SpecialRoundScoreLog.objects.create(
        cuocThi=ct,
        vongThi=vt,
        baiThi=bt,
        pair_member=opponent_member,
        giamKhao=judge,
        raw_score=int(sheet_opp.diem or 0),
        raw_time=int(getattr(sheet_opp, "thoiGian", 0) or 0),
    )

    # 5. So sánh để tìm winner / loser (dùng raw điểm + thời gian)
    score_self = int(sheet_self.diem or 0)
    score_opp  = int(sheet_opp.diem or 0)
    time_self  = int(getattr(sheet_self, "thoiGian", 0) or 0)
    time_opp   = int(getattr(sheet_opp, "thoiGian", 0) or 0)

    if score_self > score_opp:
        winner_sheet, loser_sheet = sheet_self, sheet_opp
    elif score_opp > score_self:
        winner_sheet, loser_sheet = sheet_opp, sheet_self
    else:
        # điểm bằng nhau → so thời gian, ít hơn thắng
        if time_self < time_opp:
            winner_sheet, loser_sheet = sheet_self, sheet_opp
        elif time_opp < time_self:
            winner_sheet, loser_sheet = sheet_opp, sheet_self
        else:
            # điểm & thời gian đều bằng nhau → hòa, cả 2 = 0
            PhieuChamDiem.objects.filter(
                pk__in=[sheet_self.pk, sheet_opp.pk]
            ).update(diem=0)
            return

    # 6. Ghi điểm final 100 / 0 vào Phiếu chấm
    PhieuChamDiem.objects.filter(pk=winner_sheet.pk).update(diem=bonus)
    PhieuChamDiem.objects.filter(pk=loser_sheet.pk).update(diem=0)
