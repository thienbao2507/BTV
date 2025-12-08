document.addEventListener("DOMContentLoaded", function () {
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
                            var msg = data && data.message ? data.message : "Lỗi " + res.status;
                            throw new Error(msg);
                        }
                        return data;
                    });
                })
                .then(function (data) {
                    btn.textContent = "Đã lưu";
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
