document.addEventListener("DOMContentLoaded", function () {
    // Đồng bộ ô số <-> slider, thang 0–100
    const numberInputs = document.querySelectorAll('input[data-role="score-input"]');

    numberInputs.forEach(function (input) {
        const index = input.dataset.tsIndex;
        const slider = document.querySelector(
            'input[data-role="score-slider"][data-ts-index="' + index + '"]'
        );
        if (!slider) return;

        // từ ô số -> slider
        input.addEventListener("input", function () {
            let val = parseFloat(input.value);
            if (isNaN(val)) val = 0;
            if (val < 0) val = 0;
            if (val > 100) val = 100;
            input.value = val;
            slider.value = val;
        });

        // từ slider -> ô số
        slider.addEventListener("input", function () {
            input.value = slider.value;
        });
    });

    // --- Carousel: vuốt 1 lần qua 1 thí sinh + dots ---
    const track = document.querySelector('[data-role="carousel-track"]');
    const slides = track ? Array.from(track.querySelectorAll('[data-slide-index]')) : [];
    const dots = Array.from(document.querySelectorAll('[data-role="carousel-dot"]'));

    if (track && slides.length > 0) {
        let current = 0;
        let ignoreSwipe = false;

        function updateCarousel() {

            const offset = -current * 100;
            track.style.transform = "translateX(" + offset + "%)";

            dots.forEach(function (dot, idx) {
                if (idx === current) {
                    dot.classList.add("bg-white");
                    dot.classList.remove("bg-slate-500/40");
                } else {
                    dot.classList.remove("bg-white");
                    dot.classList.add("bg-slate-500/40");
                }

            });
        }

        // Vuốt 1 lần -> move +/-1
        let startX = null;

        function onTouchStart(e) {
            if (!e.touches || e.touches.length === 0) return;

            const target = e.target;
            if (target.closest('input[data-role="score-slider"], input[data-role="score-input"]')) {
                // Vuốt bắt đầu trên thanh điểm hoặc ô điểm -> không dùng cho carousel
                ignoreSwipe = true;
                startX = null;
                return;
            }

            ignoreSwipe = false;
            startX = e.touches[0].clientX;
        }


        function onTouchEnd(e) {
            if (ignoreSwipe) {
                // Vuốt xuất phát từ slider / ô điểm -> không đổi thí sinh
                ignoreSwipe = false;
                startX = null;
                return;
            }

            if (startX === null) return;
            const touch = e.changedTouches && e.changedTouches[0];
            const endX = touch ? touch.clientX : startX;
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

        // Click vào dot để nhảy trực tiếp
        dots.forEach(function (dot, idx) {
            dot.addEventListener("click", function () {
                current = idx;
                updateCarousel();
            });
        });

        // Khởi tạo vị trí ban đầu
        // Khởi tạo vị trí ban đầu
        updateCarousel();
    }

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

    // --- Lưu điểm cho từng thí sinh ---
    const saveButtons = document.querySelectorAll('button[data-role="save-score"]');


    saveButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            const tsId = btn.getAttribute("data-ts-id");
            const index = btn.getAttribute("data-ts-index");
            if (!tsId) return;

            const input = document.querySelector(
                'input[data-role="score-input"][data-ts-index="' + index + '"]'
            );
            if (!input) return;

            let val = parseFloat(input.value);
            if (isNaN(val)) val = 0;
            if (val < 0) val = 0;
            if (val > 100) val = 100;
            input.value = val;

            btn.disabled = true;
            const oldText = btn.textContent;
            btn.textContent = "Đang lưu...";

            fetch("/bgd/api/save-score/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    thiSinh_id: tsId,
                    score: val,
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

