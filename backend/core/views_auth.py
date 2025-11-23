from django.shortcuts import render, redirect
from django.urls import reverse
from core.models import GiamKhao

def login_view(request):
    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        next_url = request.POST.get("next") or "/"
        judge = GiamKhao.objects.filter(email__iexact=email).first()
        if judge:
            # NEW: login tay => thoát hẳn mọi dấu vết phiên BGD
            for k in ("bgd_token", "bgd_mode", "bgd_ct_id", "bgd_ct_name"):
                request.session.pop(k, None)

            # (tuỳ) dọn alias judge_id nếu có nơi khác dùng
            request.session.pop("judge_id", None)

            # Lưu giám khảo vào session
            request.session["judge_pk"] = judge.pk
            request.session["judge_email"] = judge.email or email

            # (tuỳ) session 8h cho tiện thao tác
            # request.session.set_expiry(60 * 60 * 8)

            return redirect(next_url)
        error = "Email không nằm trong danh sách Giám khảo."

    return render(request, "auth/login.html", {
        "next": request.GET.get("next") or "/",
        "error": error,
    })


def logout_view(request):
    # Dọn nhận diện giám khảo
    for k in ("judge_pk", "judge_email", "judge_id"):
        request.session.pop(k, None)

    # Dọn toàn bộ cờ BGD còn sót từ phiên QR
    for k in ("bgd_token", "bgd_mode", "bgd_ct_id", "bgd_ct_name"):
        request.session.pop(k, None)

    return redirect(reverse("login"))

