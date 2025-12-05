// navbar.js
(function () {
    // ======================
    // DROPDOWN USER (GMAIL)
    // ======================
    const btn  = document.getElementById('navUserBtn');
    const menu = document.getElementById('navDropdown');

    function syncWidth() {
        if (!btn || !menu) return;
        // đặt chiều rộng dropdown = bề ngang nút gmail (pill)
        menu.style.width = btn.offsetWidth + 'px';
    }

    function openMenu() {
        if (!btn || !menu) return;
        syncWidth();
        menu.classList.remove('hidden');
    }

    function closeMenu() {
        if (!menu) return;
        menu.classList.add('hidden');
    }

    function toggleMenu() {
        if (!menu) return;
        if (menu.classList.contains('hidden')) openMenu();
        else closeMenu();
    }

    if (btn && menu) {
        // click vào nút → toggle
        btn.addEventListener('click', toggleMenu);

        // click ra ngoài → đóng
        document.addEventListener('click', (e) => {
            if (menu.classList.contains('hidden')) return;
            if (e.target === btn || btn.contains(e.target)) return;
            if (menu.contains(e.target)) return;
            closeMenu();
        });

        // nhấn ESC → đóng
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeMenu();
        });

        // resize: lên desktop thì đóng, mobile thì giữ width khớp nút nếu đang mở
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                // đổi lên desktop → đóng dropdown
                closeMenu();
            } else {
                // vẫn ở mobile và menu đang mở → cập nhật lại width
                if (!menu.classList.contains('hidden')) syncWidth();
            }
        });
    }

    // ======================
    // NAVBAR SLIDE TRONG TRANG RANKING
    // ======================
    // Cần trong HTML:
    // <nav id="mainNavbar" class="... transform transition-transform ... -translate-y-full (ở trang ranking) ...">
    // <button id="rankingNavToggle">...</button>
    // <svg id="rankingNavToggleIcon" class="transition-transform">...</svg>
    const nav       = document.getElementById('mainNavbar');
    const toggleBtn = document.getElementById('rankingNavToggle');
    const icon      = document.getElementById('rankingNavToggleIcon');

    if (nav && toggleBtn && icon) {
        // navbar mở hay ẩn hiện tại?
        let isOpen = !nav.classList.contains('-translate-y-full');

        function updateIcon() {
            // dùng class rotate-180 của Tailwind để xoay mũi tên
            if (isOpen) {
                // navbar đang MỞ → icon quay lên
                icon.classList.add('rotate-180');
            } else {
                // navbar đang ẨN → icon quay xuống
                icon.classList.remove('rotate-180');
            }
        }

        updateIcon();

        toggleBtn.addEventListener('click', () => {
            isOpen = !isOpen;
            // ẩn: thêm -translate-y-full; hiện: bỏ nó đi
            nav.classList.toggle('-translate-y-full', !isOpen);
            updateIcon();
        });
    }
})();
// ==== Global guard: chặn mọi đường dẫn /ranking khi đang TẮT (áp dụng toàn site)
(function(){
  async function fetchRankingState(){
    try{
      const r = await fetch("/management/ranking-state", {credentials:"same-origin"});
      const j = await r.json();
      return !!j.enabled;
    }catch(e){ return true; }
  }
document.addEventListener('click', async (e) => {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const href = a.getAttribute('href') || '';
  if (!/^\/ranking(\/|$|\?)/.test(href)) return;
  const on = await fetchRankingState();
  if (!on) {
    e.preventDefault();   // im lặng
  }
}, {capture:true});

})();
