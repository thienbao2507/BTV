"""
URL configuration for examsite project.
"""

from django.contrib import admin
from django.urls import path, include

from core.views_home import home_view, manage_view
from core.views_auth import login_view, logout_view
from core.views_organize import organize_view, competition_list_view
from core.views_score import score_view
from core.views_ranking import ranking_view
from core.views_management import management_view, ranking_state
from core.views_export import (
    export_page,
    export_xlsx,
    export_final_page,
    export_final_xlsx,
)
from core import views_score
from core.views_admin import import_view, upload_avatars_view
from core.views_bgd import (
    bgd_qr_index,
    bgd_qr_png,
    bgd_go,
    bgd_go_stars,
    bgd_battle_go,
    score_bgd_view,
    bgd_qr_zip_all,
    bgd_list,
    bgd_save_score,
)
from core.views_battle import (
    battle_view,
    manage_battle_view,
    save_pairing,
    pairing_state,
    submit_vote,
    delete_pair,
)
from django.conf import settings
from django.conf.urls.static import static
from core.views_voting import (
    voting_home_view,
    voting_submit_api,
    voting_revoke_api,
)

urlpatterns = [
    path("", home_view, name="home"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),

    path("score/", score_view),
    path("score/template/<int:btid>/", views_score.score_template_api, name="score_template_api"),
    path("score/bgd/", score_bgd_view, name="score-bgd"),

    path("organize/competitions/", competition_list_view, name="competition-list"),
    path("organize/<int:ct_id>/", organize_view, name="organize-detail"),
    path("organize/", organize_view),

    path("admin/tools/", include("core.urls_admin")),
    path("admin/", admin.site.urls),

    path("ranking/", ranking_view),
    path("management/", management_view, name="management"),
    path("management/ranking-state", ranking_state, name="ranking-state"),

    path("export", export_page, name="export-page"),
    path("export-xlsx", export_xlsx, name="export-xlsx"),
    path("export-final", export_final_page, name="export-final-page"),
    path("export-final-xlsx", export_final_xlsx, name="export-final-xlsx"),

    path("import/", import_view, name="import"),
    path("upload-avatars/", upload_avatars_view, name="upload-avatars"),

    # BGD
    path("bgd/", bgd_list, name="bgd-list"),
    path("bgd/qr/", bgd_qr_index, name="bgd-qr"),
    path("bgd/qr/<str:token>/", bgd_qr_index, name="bgd-qr-one"),
    path("bgd/qr/<int:ct_id>/<int:vt_id>/<str:token>.png", bgd_qr_png, name="bgd-qr-png"),
    path("bgd/qr-all.zip", bgd_qr_zip_all, name="bgd-qr-all"),

    path("bgd/go/<int:ct_id>/<int:vt_id>/<str:token>/", bgd_go, name="bgd-go"),
    path(
        "bgd/go-stars/<int:ct_id>/<int:vt_id>/<str:token>/",
        bgd_go_stars,
        name="bgd-go-stars",
    ),
    path("bgd/battle/<str:token>/", bgd_battle_go, name="bgd-battle-go"),
    path("bgd/api/save-score/", bgd_save_score, name="bgd-save-score"),

    # Battle
    path("battle/", battle_view, name="battle"),
    path("battle/manage/", manage_battle_view, name="manage-battle"),
    path("battle/pairing/save", save_pairing, name="battle-pairing-save"),
    path("battle/pairing/state", pairing_state, name="battle-pairing-state"),
    path("battle/pairing/delete", delete_pair, name="battle-pairing-delete"),
    path("battle/vote", submit_vote, name="battle_submit_vote"),

    # Voting
    path("voting/", voting_home_view, name="voting-home"),
    path("voting/api/revoke", voting_revoke_api, name="voting_revoke_api"),
    path("voting/api/submit", voting_submit_api, name="voting-submit-api"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
