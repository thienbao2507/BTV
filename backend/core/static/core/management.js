const card = document.getElementById('contestCard');
const modal = document.getElementById('contestModal');
const closeBtn = document.getElementById('closeModal');

if (card && modal && closeBtn) {
    card.addEventListener('click', () => modal.classList.remove('hidden'));
    closeBtn.addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', e => {
        if (e.target === modal) modal.classList.add('hidden');
    });
}
// Ngăn không cho cuộn cả trang khi đang cuộn trong bảng xếp hạng
const rankingWrapper = document.querySelector('.ranking-table-wrapper');

if (rankingWrapper) {
    rankingWrapper.addEventListener('wheel', (e) => {
        const deltaY = e.deltaY;
        const scrollTop = rankingWrapper.scrollTop;
        const height = rankingWrapper.clientHeight;
        const scrollHeight = rankingWrapper.scrollHeight;

        const atTop = scrollTop === 0;
        const atBottom = scrollTop + height >= scrollHeight - 1;

        // Nếu đã tới đầu hoặc cuối bảng thì chặn không cho sự kiện “lọt” ra ngoài
        if ((deltaY < 0 && atTop) || (deltaY > 0 && atBottom)) {
            e.preventDefault();
            e.stopPropagation();
        }
    }, { passive: false });
}
// ========== RANKING TOGGLE + CSRF + CHẶN NHẢY TRANG TẠI MANAGEMENT ==========

// Lấy CSRF cookie (Django)
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

async function fetchRankingState() {
  try{
    const r = await fetch("/management/ranking-state", {credentials:"same-origin"});
    const j = await r.json();
    return !!j.enabled;
  }catch(e){ return true; }
}

async function setRankingState(enabled) {
  try{
    const csrftoken = getCookie('csrftoken');
    const r = await fetch("/management/ranking-state", {
      method: "POST",
      headers: {
        "Content-Type":"application/json",
        "X-CSRFToken": csrftoken || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials:"same-origin",
      body: JSON.stringify({enabled: !!enabled})
    });
    const j = await r.json();
    return !!j.enabled;
  }catch(e){ return enabled; }
}

(async () => {
  const toggle = document.getElementById('toggleRanking');
  const hint   = document.getElementById('rankingStateHint');
  if (!toggle) return;

  const syncHint = (on) => {
    hint.textContent = on ? "Ranking đang MỞ — bấm để TẮT." : "Ranking đang TẮT — bấm để MỞ.";
  };

  const init = await fetchRankingState();
  toggle.checked = init;
  syncHint(init);

  toggle.addEventListener('change', async () => {
    const after = await setRankingState(toggle.checked);
    toggle.checked = after;
    syncHint(after);
  });

document.addEventListener('click', async (e) => {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const href = a.getAttribute('href') || '';
  if (!/^\/ranking(\/|$|\?)/.test(href)) return;

  const on = await fetchRankingState();
  if (!on) {
    e.preventDefault();   // không hiện alert
  }
}, {capture:true});

})();
