document.addEventListener("DOMContentLoaded", function () {
  const numberInputs = document.querySelectorAll('input[data-role="score-input"]');
  const sliders = document.querySelectorAll('input[data-role="score-slider"]');

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
      if (val > 10) val = 10;
      input.value = val;
      slider.value = val;
    });

    slider.addEventListener("input", function () {
      input.value = slider.value;
    });
  });
});
