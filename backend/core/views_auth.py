from django.shortcuts import render, redirect
from django.urls import reverse
from core.models import GiamKhao
from .views_voting import _is_allowed_voter_email
def login_view(request):
    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        next_url = request.POST.get("next") or "/"

        # 1) Chặn ngay nếu email không thuộc domain được phép
        if not _is_allowed_voter_email(email):
            return render(
                request,
                "auth/login.html",
                {
                    "next": next_url,
                    "error": "Email của bạn không thuộc domain được phép. Vui lòng dùng email công ty (ví dụ: @fpt.com, @fpt.net, @vienthong.com).",
                    "email": email,  # prefill lại cho tiện sửa
                },
                status=400,
            )

        # 2) Xóa cờ BGD trước khi set session đăng nhập
        for k in ("bgd_token", "bgd_mode", "bgd_ct_id", "bgd_ct_name"):
            request.session.pop(k, None)

        # 3) Đăng nhập hợp lệ
        request.session["auth_email"] = email
        request.session["can_vote"] = True  # vì đã pass domain

        # 4) Xét role giám khảo như logic hiện có
        judge = GiamKhao.objects.filter(email__iexact=email).first()
        if judge:
            request.session["judge_pk"] = judge.pk
            request.session["judge_email"] = judge.email or email
        else:
            for k in ("judge_pk", "judge_email", "judge_id"):
                request.session.pop(k, None)

        return redirect(next_url)

    return render(
        request,
        "auth/login.html",
        {"next": request.GET.get("next") or "/", "error": None},
    )

def logout_view(request):
    # Dọn nhận diện giám khảo & người dùng thường
    for k in ("judge_pk", "judge_email", "judge_id", "auth_email"):
        request.session.pop(k, None)

    # Dọn cờ BGD
    for k in ("bgd_token", "bgd_mode", "bgd_ct_id", "bgd_ct_name"):
        request.session.pop(k, None)

    return redirect(reverse("login"))
