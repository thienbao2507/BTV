from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction

from core.models import ThiSinh, CuocThi, ThiSinhVoting, VotingRecord

ALLOWED_VOTER_DOMAINS = {"fpt.com", "fpt.net", "vienthong.com"}

def _login_email(request) -> str:
    # Ưu tiên judge_email, sau đó đến auth_email (người dùng thường)
    email = (request.session.get("judge_email")
             or request.session.get("auth_email")
             or "").strip().lower()
    return email

def _is_allowed_voter_email(email: str) -> bool:
    if "@" not in email:
        return False
    return email.split("@", 1)[1].lower() in ALLOWED_VOTER_DOMAINS

def voting_home_view(request):
    email = _login_email(request)

    # KHÔNG redirect khi chưa đăng nhập -> cho phép xem tự do
    # if not email:
    #     return redirect(f"/login?next={request.path}")

    # Chọn cuộc thi (giữ nguyên)
    ct_id = request.GET.get("ct")
    if ct_id:
        try:
            ct = CuocThi.objects.get(pk=int(ct_id))
        except Exception:
            ct = None
    else:
        ct = CuocThi.objects.filter(trangThai=True).order_by("id").first()

    # Danh sách ứng viên (giữ nguyên)
    if ct:
        candidates_qs = (ThiSinhVoting.objects
                         .select_related("thiSinh", "cuocThi")
                         .filter(cuocThi=ct)
                         .order_by("thiSinh__maNV"))
    else:
        candidates_qs = (ThiSinhVoting.objects
                         .select_related("thiSinh", "cuocThi")
                         .order_by("thiSinh__maNV"))

    existing = VotingRecord.objects.filter(voter_email=email).first() if email else None

    candidates = []
    for cv in candidates_qs:
        ts = cv.thiSinh
        candidates.append({
            "maNV": ts.maNV,
            "hoTen": ts.hoTen,
            "donVi": ts.donVi or "",
            "image_url": ts.display_image_url,
            "ct_ma": cv.cuocThi.ma,
            "ct_id": cv.cuocThi.id,
        })

    ctx = {
        "login_email": email or "",
        "can_vote": bool(request.session.get("can_vote")) if email else False,
        "contest": ct,
        "candidates": candidates,
        "already_voted": bool(existing),
        "voted_target": {
            "maNV": existing.thiSinh_ma,
            "hoTen": existing.thiSinh_ten
        } if existing else None,
    }
    return render(request, "voting/index.html", ctx)

@require_POST
def voting_submit_api(request):
    email = _login_email(request)
    if not email:
        return JsonResponse({"ok": False, "error": "NOT_LOGGED_IN"}, status=401)

    # Chỉ cho phép domain hợp lệ
    if not _is_allowed_voter_email(email):
        return JsonResponse({"ok": False, "error": "EMAIL_DOMAIN_NOT_ALLOWED"}, status=403)

    import json
    try:
        data = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("BAD_JSON")

    maNV = (data.get("maNV") or "").strip()
    if not maNV:
        return HttpResponseBadRequest("MISSING_maNV")

    if VotingRecord.objects.filter(voter_email=email).exists():
        return JsonResponse({"ok": False, "error": "ALREADY_VOTED"}, status=409)

    ts = ThiSinh.objects.filter(pk=maNV).first()
    if not ts:
        return JsonResponse({"ok": False, "error": "INVALID_CANDIDATE"}, status=404)

    ct = None
    ct_id = data.get("ct_id")
    if ct_id:
        try:
            ct = CuocThi.objects.get(pk=int(ct_id))
        except Exception:
            ct = None

    if ct and not ThiSinhVoting.objects.filter(thiSinh=ts, cuocThi=ct).exists():
        return JsonResponse({"ok": False, "error": "CANDIDATE_NOT_IN_VOTING_LIST"}, status=400)

    with transaction.atomic():
        rec = VotingRecord.objects.create(
            voter_email=email,
            cuocThi=ct,
            thiSinh=ts,
            thiSinh_ma=ts.maNV,
            thiSinh_ten=ts.hoTen,
            count=1,
        )
    return JsonResponse({"ok": True, "maNV": rec.thiSinh_ma, "hoTen": rec.thiSinh_ten})
@require_POST
def voting_revoke_api(request):
    email = _login_email(request)
    if not email:
        return JsonResponse({"ok": False, "error": "NOT_LOGGED_IN"}, status=401)

    # Hủy mọi bản ghi vote của email này (toàn cục)
    deleted_count, _ = VotingRecord.objects.filter(voter_email=email).delete()
    return JsonResponse({"ok": True, "deleted": deleted_count})