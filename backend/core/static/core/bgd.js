// static/core/bgd.js
document.addEventListener("DOMContentLoaded", function () {
    console.log("[BGD] bgd.js loaded");
    // ================== ĐỒNG BỘ Ô SỐ <-> SLIDER (giữ nguyên cho trang go cũ) ==================
    const numberInputs = document.querySelectorAll('input[data-role="score-input"]');

    numberInputs.forEach(function (input) {
        const index = input.dataset.tsIndex;
        const slider = document.querySelector(
            'input[data-role="score-slider"][data-ts-index="' + index + '"]'
        );
        if (!slider) return;

        input.addEventListener("input", function () {
            let val = parseFloat(input.value);
            if (isNaN(val)) val = 0;
            if (val < 0) val = 0;
            if (val > 100) val = 100;
            input.value = val;
            slider.value = val;
        });

        slider.addEventListener("input", function () {
            input.value = slider.value;
        });
    });
    

    // --- Chấm điểm bằng sao: 1–5 sao, mỗi sao = 20 điểm ---
    const starGroups = document.querySelectorAll('[data-role="star-group"]');

    starGroups.forEach(function (group) {
        const idx = group.getAttribute("data-ts-index");
        const stars = group.querySelectorAll('[data-role="star"]');
        const input = document.querySelector(
            'input[data-role="score-input"][data-ts-index="' + idx + '"]'
        );
        if (!input) return;

        function syncStarsFromScore() {
            let val = parseFloat(input.value);
            if (isNaN(val) || val < 0) val = 0;
            if (val > 100) val = 100;
            const starCount = Math.round(val / 20); // 0..5

            stars.forEach(function (star, i) {
                if (i < starCount) {
                    star.classList.add("bgd-star-on");
                } else {
                    star.classList.remove("bgd-star-on");
                }
            });
        }

        stars.forEach(function (star, index) {
            star.addEventListener("click", function () {
                const starCount = index + 1;     // 1..5
                const score = starCount * 20;    // 20,40,..100
                input.value = String(score);
                syncStarsFromScore();
            });
        });

        // Khởi tạo trạng thái sao theo điểm hiện có (nếu có)
        syncStarsFromScore();
    });


    // --- Carousel: vuốt 1 lần qua 1 thí sinh + dots ---
    const track = document.querySelector('[data-role="carousel-track"]');
    const slides = track ? Array.from(track.querySelectorAll('[data-slide-index]')) : [];
    const dots = Array.from(document.querySelectorAll('[data-role="carousel-dot"]'));

    if (track && slides.length > 0) {
        let current = 0;
        let startX = null;

        function updateCarousel() {
            const pct = -current * 100;
            track.style.transform = "translateX(" + pct + "%)";
            dots.forEach(function (dot, idx) {
                if (idx === current) {
                    dot.classList.add("bg-slate-100");
                    dot.classList.remove("bg-slate-500/40");
                } else {
                    dot.classList.remove("bg-slate-100");
                    dot.classList.add("bg-slate-500/40");
                }
            });
        }

        function onTouchStart(ev) {
            const touch = ev.touches && ev.touches[0]
                ? ev.touches[0]
                : ev.changedTouches
                ? ev.changedTouches[0]
                : null;
            if (!touch) return;
            startX = touch.clientX;
        }

        function onTouchEnd(ev) {
            if (startX == null) return;
            const touch = ev.changedTouches && ev.changedTouches[0] ? ev.changedTouches[0] : null;
            if (!touch) {
                startX = null;
                return;
            }
            const endX = touch.clientX;
            const dx = endX - startX;
            const threshold = 40; // px

            if (Math.abs(dx) > threshold) {
                if (dx < 0 && current < slides.length - 1) {
                    current += 1;
                } else if (dx > 0 && current > 0) {
                    current -= 1;
                }
            }
            updateCarousel();
            startX = null;
        }

        const viewport = document.querySelector(".bgd-carousel") || track;
        viewport.addEventListener("touchstart", onTouchStart, { passive: true });
        viewport.addEventListener("touchend", onTouchEnd);

        // Click vào dot
        dots.forEach(function (dot, idx) {
            dot.addEventListener("click", function () {
                current = idx;
                updateCarousel();
            });
        });

        updateCarousel();
    }

    // ================== TOAST LƯU ĐIỂM ==================
    function showScoreToast() {
        const toastInner = document.querySelector("#bgd-score-toast > div");
        if (!toastInner) {
            return;
        }
        toastInner.classList.remove("hidden");
        if (window.__bgdScoreToastTimeout) {
            clearTimeout(window.__bgdScoreToastTimeout);
        }
        window.__bgdScoreToastTimeout = setTimeout(function () {
            toastInner.classList.add("hidden");
        }, 3000);
    }

    // ================== LƯU ĐIỂM ==================
    const saveButtons = document.querySelectorAll('button[data-role="save-score"]');

    saveButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            const tsId = btn.getAttribute("data-ts-id");
            const index = btn.getAttribute("data-ts-index");
            if (!tsId) return;

            let finalScore = null;

            // ---- MODE CHẤM SAO (Top 10 – go_stars) ----
            const starInput = document.querySelector(
                'input[data-role="star-value"][data-ts-index="' + index + '"]'
            );
            if (starInput) {
                let stars = parseInt(starInput.value);
                if (isNaN(stars)) stars = 0;

                if (stars === 0) {
                    if (!confirm("Bạn chưa chọn sao nào. Bạn có chắc muốn lưu 0 điểm cho thí sinh này?")) {
                        return;
                    }
                }

                if (stars < 0) stars = 0;
                if (stars > STAR_MAX) stars = STAR_MAX;

                // 1★ = 20 điểm
                finalScore = stars * 20;
            } else {
                // ---- MODE ĐIỂM SỐ (go cũ) ----
                const input = document.querySelector(
                    'input[data-role="score-input"][data-ts-index="' + index + '"]'
                );
                if (!input) return;

                let val = parseFloat(input.value);
                if (isNaN(val)) val = 0;
                if (val < 0) val = 0;
                if (val > 100) val = 100;
                input.value = val;

                finalScore = val;
            }

            btn.disabled = true;
            const oldText = btn.textContent;
            btn.textContent = "Đang lưu.";

            fetch("/bgd/api/save-score/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "include",  // để giữ session -> lấy được bgd_token
                body: JSON.stringify({
                    thiSinh_id: tsId,
                    score: finalScore,
                }),
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        if (!res.ok || data.ok === false) {
                            const msg = data && data.message ? data.message : "Lỗi " + res.status;
                            throw new Error(msg);
                        }
                        return data;
                    });
                })
                .then(function () {
                    btn.textContent = "Đã lưu";
                    showScoreToast();
                    setTimeout(function () {
                        btn.textContent = oldText;
                    }, 1500);
                })
                .catch(function (err) {
                    alert("Không lưu được điểm: " + err.message);
                    btn.textContent = oldText;
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    });
});
