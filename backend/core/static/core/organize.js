// static/core/organize.js
// --- helpers phút/giây ---
function secToParts(total) {
  const t = Math.max(0, parseInt(total, 10) || 0);
  return [Math.floor(t / 60), t % 60];  // [phút, giây]
}
function partsToSec(min, sec) {
  const m = Math.max(0, parseInt(min, 10) || 0);
  const s = Math.max(0, parseInt(sec, 10) || 0);
  return m * 60 + s;
}


document.addEventListener('DOMContentLoaded', function () {
  // ===== Form "Thêm bài" — Ẩn/hiện Điểm tối đa theo phương thức chấm =====
  document.querySelectorAll('form').forEach(function (f) {
    const sel = f.querySelector('select[name="phuongThucCham"]');
    if (!sel) return;
    const maxLabel = f.querySelector('.js-max-label');
    const maxInput = f.querySelector('.js-max-input');
    const fileTemplate = f.querySelector('.js-file-template');

    function sync() {
      if (sel.value === 'POINTS') {
        if (maxLabel) maxLabel.style.display = '';
        if (maxInput) { maxInput.style.display = ''; maxInput.required = true; }
      } else {
        if (maxLabel) maxLabel.style.display = 'none';
        if (maxInput) { maxInput.style.display = 'none'; maxInput.required = false; maxInput.value = ''; }
      }
if (fileTemplate) {
  fileTemplate.style.display = (sel.value === 'TEMPLATE') ? '' : 'none';
}

    }
    sel.addEventListener('change', sync);
    sync();
  });

  // === Kebab (3 chấm) dropdown ===
  (function initKebab(){
    document.body.addEventListener('click', (e) => {
      // đóng tất cả trước
      document.querySelectorAll('.kebab-menu').forEach(m => m.style.display = 'none');

      const toggle = e.target.closest?.('.kebab-toggle');
      if (toggle) {
        const wrap = toggle.closest('.kebab');
        const menu = wrap?.querySelector('.kebab-menu');
        if (menu) { menu.style.display = (menu.style.display === 'block') ? 'none' : 'block'; }
      }
    });

    // // ngăn menu tự tắt khi bấm vào trong
    // document.body.addEventListener('click', (e) => {
    //   if (e.target.closest?.('.kebab-menu')) e.stopPropagation();
    // }, true);
  })();

  // ===== Modal cấu hình THỜI GIAN =====
  const modal = document.getElementById('time-modal');
  const rowsBox = document.getElementById('tm-rows');
  const btnClose = document.getElementById('tm-close');
  const btnAdd = document.getElementById('tm-add');
  const inputBT = document.getElementById('tm-btid');
  const inputJSON = document.getElementById('tm-json');
  const form = document.getElementById('tm-form');
  // === Import Excel cho popup THỜI GIAN ===
  const tmImportForm = document.getElementById('tm-import-form');
  const tmImportBtid = document.getElementById('tm-import-btid');
  const tmFile       = document.getElementById('tm-file');

  // đồng bộ id bài thi cho form import khi mở modal
  function syncTimeImportBtid() {
    if (tmImportBtid && inputBT) tmImportBtid.value = inputBT.value || '';
  }


  // tiện ích lấy CSRF
  function getCsrfToken(formEl) {
    const inp = formEl?.querySelector('input[name="csrfmiddlewaretoken"]');
    return inp ? inp.value : '';
  }

  tmImportForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!tmFile?.files?.length) {
      alert('Vui lòng chọn tệp .xlsx trước khi import.');
      return;
    }
    // bảo đảm btid đã set
    syncTimeImportBtid();

    const fd = new FormData(tmImportForm);
    // gửi tới cùng URL trang organize hiện tại
    const url = window.location.pathname;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(tmImportForm) },
        body: fd
      });
      const data = await res.json();
      if (!data.ok) {
        alert(data.error || 'Import thất bại.');
        return;
      }
      // Xóa tất cả dòng cũ và đổ mới
      rowsBox.innerHTML = '';
      (data.rows || []).forEach(addRowFromObj);
      // Sau khi import, bạn có thể chỉnh sửa tiếp rồi ấn "Lưu cấu hình"
    } catch (err) {
      console.error(err);
      alert('Không thể import. Vui lòng thử lại.');
    }
  });

  function openTimeModal(btid, rules) {
    if (!modal || !rowsBox || !inputBT) {
      console.warn('[time] elements not found');
      return;
    }
    inputBT.value = btid || '';
    rowsBox.innerHTML = '';
    (rules || []).forEach(addRowFromObj);

    // >>> thêm dòng này để form import có đúng bài thi
    syncTimeImportBtid();

    modal.style.display = 'flex';
  }

  function closeTimeModal() { if (modal) modal.style.display = 'none'; }

  function addRowFromObj(obj) {
    const [sm, ss] = secToParts(obj?.start ?? 0);
    const [em, es] = secToParts(obj?.end ?? 0);
    addRow(sm, ss, em, es, obj?.score ?? '');
  }
  function addRow(sMin = '', sSec = '', eMin = '', eSec = '', score = '') {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
    <div class="tm-row">
      <div class="tm-group">
        <label class="tm-label">Thời gian bắt đầu</label>
        <input type="number" min="0" step="1" class="tm-input tm-start-min" placeholder="" style="width:64px">
        <span class="tm-unit" style="color: #989899ff; font-style: italic;">phút</span>
        <input type="number" min="0" max="59" step="1" class="tm-input tm-start-sec" placeholder="" style="width:64px">
        <span class="tm-unit" style="color: #989899ff; font-style: italic;">giây</span>
      </div>
      <div class="tm-group">
        <label class="tm-label">Thời gian kết thúc</label>
        <input type="number" min="0" step="1" class="tm-input tm-end-min" placeholder="" style="width:64px">
        <span class="tm-unit" style="color: #989899ff; font-style: italic;">phút</span>
        <input type="number" min="0" max="59" step="1" class="tm-input tm-end-sec" placeholder="" style="width:64px">
        <span class="tm-unit" style="color: #989899ff; font-style: italic;">giây</span>
      </div>
      <div class="tm-group tm-scorebox">
        <label class="tm-label">Điểm</label>
        <input type="number" step="1" class="tm-input tm-score" value="${score}" style="width:90px">
        <button type="button" class="btn tm-del">Xoá</button>
      </div>
    </div>
    `;
    row.querySelector('.tm-start-min').value = sMin;
    row.querySelector('.tm-start-sec').value = sSec;
    row.querySelector('.tm-end-min').value   = eMin;
    row.querySelector('.tm-end-sec').value   = eSec;
    row.querySelector('.tm-del').addEventListener('click', () => row.remove());
    rowsBox.appendChild(row);
  }

  // mở modal thời gian khi click nút
  document.querySelectorAll('[data-open-time-modal]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const btid = this.getAttribute('data-btid');
      let rules = [];
      try { rules = JSON.parse(this.getAttribute('data-rules') || '[]'); } catch (e) { }
      openTimeModal(btid, rules);
    });
  });

  btnAdd?.addEventListener('click', () => addRow('', '', '', '', ''));
  btnClose?.addEventListener('click', closeTimeModal);
  modal?.addEventListener('click', (e) => { if (e.target === modal) closeTimeModal(); });

  // --- Kiểm tra và gom dữ liệu → JSON ---
  form?.addEventListener('submit', function (e) {
    if (!rowsBox || !inputJSON) return;
    const rows = [];
    let hasError = false;
    let msg = '';

    rowsBox.querySelectorAll('.row').forEach(function (r, i) {
      // Ép kiểu số nguyên, nếu rỗng coi là NaN
      const sm = parseInt(r.querySelector('.tm-start-min')?.value ?? '', 10);
      const ss = parseInt(r.querySelector('.tm-start-sec')?.value ?? '', 10);
      const em = parseInt(r.querySelector('.tm-end-min')?.value ?? '', 10);
      const es = parseInt(r.querySelector('.tm-end-sec')?.value ?? '', 10);
      const sc = parseInt(r.querySelector('.tm-score')?.value ?? '', 10);

      // 1️⃣ Kiểm tra trống
      if (isNaN(sm) || isNaN(ss) || isNaN(em) || isNaN(es)) {
        hasError = true;
        msg = `Dòng ${i + 1}: thời gian không được để trống.`;
      }

      // 2️⃣ Kiểm tra âm
      else if (sm < 0 || ss < 0 || em < 0 || es < 0) {
        hasError = true;
        msg = `Dòng ${i + 1}: thời gian không được âm.`;
      }

      // 3️⃣ Kiểm tra giây vượt 59
      else if (ss > 59 || es > 59) {
        hasError = true;
        msg = `Dòng ${i + 1}: giá trị giây phải trong khoảng 0–59.`;
      }

      // 4️⃣ Tính ra giây để so sánh
      const startSec = partsToSec(sm, ss);
      const endSec   = partsToSec(em, es);

      // 5️⃣ Kiểm tra thời gian kết thúc nhỏ hơn bắt đầu
      if (!hasError && endSec <= startSec) {
        hasError = true;
        msg = `Dòng ${i + 1}: thời gian kết thúc phải lớn hơn thời gian bắt đầu.`;
      }

      // 6️⃣ Kiểm tra điểm âm
      if (!hasError && (isNaN(sc) || sc < 0)) {
        hasError = true;
        msg = `Dòng ${i + 1}: điểm không được âm hoặc bỏ trống.`;
      }

      rows.push({ start: startSec, end: endSec, score: sc || 0 });
    });

    if (hasError) {
      e.preventDefault();
      alert(msg);
      return false;
    }

    inputJSON.value = JSON.stringify(rows);
  });

  // ===== Modal import TEMPLATE =====
  const tplModal = document.getElementById('tpl-modal');
  const tplCloseBtn = document.getElementById('tpl-close');
  const tplForm = document.getElementById('tpl-form');
  const tplBT = document.getElementById('tpl-btid');
  const tplFile = document.getElementById('tpl-file');

  function openTpl(btid) {
    if (!tplModal || !tplBT) {
      console.warn('[tpl] modal elements not found');
      return;
    }
    tplBT.value = btid || '';
    if (tplFile) tplFile.value = '';
    tplModal.style.display = 'flex';
  }
  function closeTpl() { if (tplModal) tplModal.style.display = 'none'; }

  // Delegation: click bất kỳ phần tử có [data-open-tpl-modal]
  document.addEventListener('click', function (e) {
    const btn = e.target.closest && e.target.closest('[data-open-tpl-modal]');
    if (btn) {
      e.preventDefault();
      openTpl(btn.getAttribute('data-btid'));
    }
  });

  tplCloseBtn?.addEventListener('click', closeTpl);
  tplModal?.addEventListener('click', (e) => { if (e.target === tplModal) closeTpl(); });

  // NEW: log khi submit để xác nhận có chạy
  tplForm?.addEventListener('submit', function () {
    console.log('[tpl] submit fired');
  });

  // Debug hooks
  window.__openTimeModal = openTimeModal;
  window.__openTpl = openTpl;

  // ===== Toggle hiện/ẩn form "Thêm Cuộc thi" =====
  const btnShowCreate = document.getElementById('btn-show-create');
  const createCard = document.getElementById('create-card');
  if (btnShowCreate && createCard) {
    btnShowCreate.addEventListener('click', () => {
      const open = createCard.style.display !== 'none';
      createCard.style.display = open ? 'none' : 'block';
      btnShowCreate.textContent = open ? '+ Tạo cuộc thi' : 'Ẩn form';
    });
  }

  // ===== Gợi ý + Tìm kiếm (autocomplete giống index) =====
  const searchBox = document.getElementById('search-ct');
  const suggList  = document.getElementById('ct-suggest');   // dropdown
  const table     = document.querySelector('table');

  // Chuẩn hoá bỏ dấu
  const vnNorm = s => (s || '')
    .toString()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();

  if (table && searchBox) {
    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const takeName = (tr) => {
      const inp = tr.querySelector('input[name="tenCuocThi"]');
      if (inp && inp.value) return inp.value.trim();
      return (tr.cells?.[1]?.innerText || '').trim();
    };
    const data = rows.map(tr => ({ tr, name: takeName(tr) }));

    // Lọc bảng
    function applyFilter(q) {
      const k = vnNorm(q);
      data.forEach(({ tr, name }) => {
        tr.style.display = (!k || vnNorm(name).includes(k)) ? '' : 'none';
      });
    }

    // ----- Dropdown gợi ý -----
    let activeIdx = -1;
    let itemEls = [];

    function closeList() {
      if (!suggList) return;
      suggList.style.display = 'none';
      suggList.innerHTML = '';
      activeIdx = -1;
      itemEls = [];
    }
    function openList() {
      if (!suggList) return;
      suggList.style.display = 'block';
    }
    function highlightFrag(text, q) {
      const tN = vnNorm(text), qN = vnNorm(q);
      const i = tN.indexOf(qN);
      if (i < 0 || !q) return text;
      return text.slice(0, i) + '<strong>' + text.slice(i, i + q.length) + '</strong>' + text.slice(i + q.length);
    }
    function renderList(q) {
      if (!suggList) return;
      const k = vnNorm(q);
      const matches = !k ? [] : data.filter(x => vnNorm(x.name).includes(k)).slice(0, 8);
      if (!matches.length) {
        suggList.innerHTML = `<div class="sugg-empty">Không có gợi ý phù hợp</div>`;
        openList(); activeIdx = -1; itemEls = []; return;
      }
      suggList.innerHTML = matches.map((m, i) => {
        const statusEl = m.tr.querySelector('[data-status]');
        const status = statusEl ? (statusEl.dataset.status || '') :
                      (m.tr.textContent.includes('Đang bật') ? 'Bật' :
                      m.tr.textContent.includes('Đang tắt') ? 'Tắt' : '');
        return `
          <div class="sugg-item" data-idx="${i}">
            <span class="sugg-badge"></span>
            <div class="sugg-name">${highlightFrag(m.name, q)}</div>
            <div class="sugg-status">${status}</div>
          </div>`;
      }).join('');
      itemEls = Array.from(suggList.querySelectorAll('.sugg-item'));
      activeIdx = -1;
      openList();
      itemEls.forEach(el => {
        el.addEventListener('click', () => {
          const i = Number(el.dataset.idx);
          const name = matches[i].name;
          searchBox.value = name;
          applyFilter(name);
          closeList();
          searchBox.focus();
        });
      });
    }

    // Gõ: mở gợi ý + lọc realtime
    let t;
    searchBox.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        const v = searchBox.value;
        if (!v.trim()) { closeList(); applyFilter(''); return; }
        renderList(v);
        applyFilter(v);
      }, 60);
    });

    // Điều hướng: ↑/↓/Enter/Esc
    searchBox.addEventListener('keydown', (e) => {
      if (!suggList || suggList.style.display !== 'block') {
        if (e.key === 'Enter') applyFilter(searchBox.value);
        return;
      }
      if (!itemEls.length) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = (activeIdx + 1) % itemEls.length;
        itemEls.forEach((el,i)=>el.classList.toggle('is-active', i===activeIdx));
        itemEls[activeIdx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = (activeIdx - 1 + itemEls.length) % itemEls.length;
        itemEls.forEach((el,i)=>el.classList.toggle('is-active', i===activeIdx));
        itemEls[activeIdx].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (activeIdx >= 0) itemEls[activeIdx].click();
        else { applyFilter(searchBox.value); closeList(); }
      } else if (e.key === 'Escape') {
        closeList();
      }
    });

    // Click ngoài để đóng
    document.addEventListener('click', (e) => {
      if (suggList && !suggList.contains(e.target) && e.target !== searchBox) closeList();
    });
  }
  const viewModal   = document.getElementById('tpl-view-modal');
  const viewContent = document.getElementById('tplv-content');
  const viewClose   = document.getElementById('tplv-close');

  if (viewModal && viewContent) {
    document.body.addEventListener('click', function (e) {
      const btn = e.target.closest?.('[data-open-tpl-view]');
      if (!btn) return;

      const targetId = btn.getAttribute('data-target');
      const src = document.getElementById(targetId);
      if (!src) return;

      // copy HTML vào modal
      viewContent.innerHTML = src.innerHTML;
  // ===== Làm sạch nội dung bảng trong popup =====
  const rows = viewContent.querySelectorAll('tbody tr');



  function stripCodes(txt) {
    // Bỏ tiền tố "BT123 - ", "VT02 - " ở bất kỳ vị trí nào
    txt = txt.replace(/\b(?:BT|VT)\d+\s*-\s*/gi, '');
    // Bỏ số trong ngoặc vuông: [1], [ 2 ], [10]
    txt = txt.replace(/\[\s*\d+\s*\]\s*/g, '');
    // Gộp dấu cách/thanh nối thừa
    txt = txt.replace(/\s*[-–—]\s*/g, ' - ');
    txt = txt.replace(/\s{2,}/g, ' ').trim();
    // Bỏ " - " ở đầu/cuối nếu lỡ dư
    txt = txt.replace(/^-\s+/, '').replace(/\s+-$/, '').trim();
    return txt;
  }

  rows.forEach(tr => {
    const tdSection = tr.cells?.[0];
    const tdItem    = tr.cells?.[1];

    if (!tdSection || !tdItem) return;

    // Làm sạch chung
    let s = stripCodes(tdSection.textContent || '');
    let i = stripCodes(tdItem.textContent || '');

    // Bỏ phần lặp "Mục lớn" trong "Mục nhỏ" nhưng KHÔNG để trống "Mục nhỏ"
    const sLower = s.toLowerCase();
    let iLower = i.toLowerCase();

    if (sLower) {
      // Các phân cách thường gặp sau phần lặp
      const seps = [' - ', ' — ', ': ', ' – ', ' —', '-', ':'];
      let trimmed = false;

      for (const sep of seps) {
        const prefix = sLower + sep.toLowerCase();
        if (iLower.startsWith(prefix)) {
          const rest = i.slice(prefix.length).trim();
          if (rest) {            // chỉ cắt khi có phần dư
            i = rest;
            iLower = i.toLowerCase();
            trimmed = true;
          }
          break;                  // gặp 1 sep là dừng
        }
      }

      // Nếu chưa cắt bằng sep, xem trường hợp i bắt đầu đúng bằng s (không có sep)
      if (!trimmed && iLower.startsWith(sLower) && iLower.length > sLower.length) {
        const rest = i.slice(s.length).replace(/^[-–—:]\s*/, '').trim();
        if (rest) i = rest;      // chỉ nhận nếu còn nội dung
      }
    }

    // Nếu vì bất kỳ lý do gì i rỗng → giữ nguyên như s để "Mục nhỏ" không bị trống
    if (!i) {
      i = s;
    }

    // Gán lại text đã làm sạch
    tdSection.textContent = s;
    tdItem.textContent    = i;

  });
  // Nếu header dùng đơn vị giây (s) → chuyển sang phút và đổi số
  try {
    const thead = viewContent.querySelector('thead');
    if (thead && thead.textContent && thead.textContent.indexOf('(s)') !== -1) {
      // đổi header từ (s) → (phút)
      thead.querySelectorAll('th').forEach(th => {
        th.textContent = th.textContent.replace(/\(s\)/ig, '(phút)');
      });

      // chuyển các ô cột Từ/Đến từ giây -> phút (làm tròn xuống)
      rows.forEach(tr => {
        for (let ci = 0; ci <= 1; ci++) {
          const cell = tr.cells?.[ci];
          if (!cell) continue;
          const txt = (cell.textContent || '').trim();
          const n = parseInt(txt, 10);
          if (!isNaN(n)) {
            const m = Math.floor(n / 60);
            cell.textContent = String(m);
          }
        }
      });
    }
  } catch (e) { console.warn('[tpl-view] convert seconds->minutes failed', e); }
      // mở modal
      viewModal.style.display = 'flex';
    });
  // ==== Modal: Xem giám khảo chấm ====
  (function initJudgeView() {
    const modal = document.getElementById('judge-view-modal');
    const content = document.getElementById('judgev-content');
    const closeBtn = document.getElementById('judgev-close');
    if (!modal || !content) return;

    function openJudgeModal(btid) {
      const holder = document.getElementById(`assigned-${btid}`);
      const assigned = (holder?.dataset.assigned || '')
                        .split(',').map(s => s.trim()).filter(Boolean);
      const set = new Set(assigned);
      let dirty = false; // whether user changed selection

      const rows = (window.ALL_JUDGES || []).map((j) => {
        const checked = set.has(j.code);
        // make checkbox editable; attach change handler to mark dirty
        const inputId = `chk-${btid}-${j.code}`;
        return `
          <tr>
              <td style="width:40px; text-align:center">
                <input id="${inputId}" type="checkbox" ${checked ? 'checked' : ''}>
              </td>
              <td style="width:140px; font-weight:600">${j.code}</td>
              <td>${j.name || ''}</td>
            </tr>
        `;
      }).join('');

      // Set modal title to the bài thi name when available
      try {
        const titleEl = document.getElementById('judgev-title');
        if (titleEl) titleEl.textContent = holder?.dataset.title || 'Giám khảo chấm';
      } catch (e) { /* ignore */ }

      // Use a colgroup with fixed widths so header and body columns align exactly.
      // First column (checkbox) small, second (code) medium, third (name) flexible.
      content.innerHTML = `
        <table class="table" style="width:100%; table-layout:fixed;">
          <colgroup>
          <col style="width:80px"> 
          <col style="width:140px">
            <col>
          </colgroup>
          <thead>
            <tr>
              <th style="text-align:center">Chọn</th>
              <th style="text-align:left">Mã NV</th>
              <th style="text-align:left">Tên giám khảo</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `;

      // After injecting rows, attach change handlers to checkboxes
      (window.ALL_JUDGES || []).forEach((j) => {
        const inputId = `chk-${btid}-${j.code}`;
        const el = document.getElementById(inputId);
        if (!el) return;
        el.addEventListener('change', () => { dirty = true; });
      });

      // Enable checkboxes (they are editable now) and ensure keyboard focus works
      content.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.removeAttribute('disabled'));

      // Set the close button to either save changes (if any) or just close
      closeBtn.onclick = async function () {
        if (!dirty) {
          modal.style.display = 'none';
          return;
        }

        // build current selection
        const checkedCodes = Array.from(content.querySelectorAll('tbody input[type="checkbox"]:checked'))
          .map(cb => cb.closest('tr').querySelector('td:nth-child(2)').textContent.trim());

        const initial = Array.from(set);
        const same = initial.length === checkedCodes.length && initial.every(v => checkedCodes.includes(v));
        if (same) {
          modal.style.display = 'none';
          return;
        }

        // send update to server
        // helper to read csrf token from cookie
        function getCookie(name) {
          const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
          return v ? v.pop() : '';
        }

        try {
          const payload = { baiThi_id: btid, judges: checkedCodes };
          // send as form-encoded so server can read via request.POST reliably
          const formBody = new URLSearchParams();
          formBody.append('action', 'update_assignments');
          formBody.append('baiThi_id', String(btid));
          // append judges as repeated fields
          checkedCodes.forEach(code => formBody.append('judges', code));

          const res = await fetch(window.location.pathname, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
              'X-CSRFToken': getCookie('csrftoken'),
            },
            body: formBody.toString(),
          });

          const dataText = await res.text();
          let data = {};
          try { data = JSON.parse(dataText); } catch (err) { /* not JSON */ }

          if (res.ok && data.ok) {
            if (holder) holder.dataset.assigned = checkedCodes.join(',');
            modal.style.display = 'none';
          } else {
            alert('Cập nhật phân công thất bại: ' + (data.message || res.statusText || dataText));
          }
        } catch (e) {
          alert('Lỗi khi cập nhật phân công: ' + e.message);
        }
      };
      modal.style.display = 'flex';
    }

    // Xử lý sự kiện khi click vào button "Xem giám khảo chấm"
    document.body.addEventListener('click', (e) => {
      const btn = e.target.closest?.('[data-open-judge-view]');
      if (!btn) return;
      const btid = btn.getAttribute('data-btid');
      openJudgeModal(btid);
      // Đóng menu nếu nó đang mở
      const kebabMenu = btn.closest('.kebab')?.querySelector('.kebab-menu');
      if (kebabMenu) kebabMenu.style.display = 'none';
    });

    closeBtn?.addEventListener('click', () => modal.style.display = 'none');
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.style.display = 'none';
    });
  })();

    viewClose?.addEventListener('click', () => viewModal.style.display = 'none');
    viewModal.addEventListener('click', (e) => {
      if (e.target === viewModal) viewModal.style.display = 'none';
    });
  } else {
    console.warn('[tpl-view] modal elements not found');
  }

    console.log('[organize] JS ready');
  const $modal  = document.getElementById('confirmModal');
  const $msg    = document.getElementById('confirmMessage');
  const $ok     = document.getElementById('confirmOk');
  const $cancel = document.getElementById('confirmCancel');

  if ($modal && $msg && $ok && $cancel) {
    let onOk = null, onCancel = null;

    function openConfirm(message, _onOk, _onCancel) {
      $msg.textContent = message;
      onOk = _onOk; onCancel = _onCancel || null;
      $modal.style.display = 'flex';
    }
    function closeConfirm() {
      $modal.style.display = 'none';
      onOk = null; onCancel = null;
    }
    $ok.addEventListener('click', () => { if (onOk) onOk(); closeConfirm(); });
    $cancel.addEventListener('click', () => { if (onCancel) onCancel(); closeConfirm(); });
    $modal.addEventListener('click', (e) => {
      if (e.target === $modal) { if (onCancel) onCancel(); closeConfirm(); }
    });

    // 1) Đổi tên
  // ===== XÁC NHẬN CHỈ CHO FORM CẬP NHẬT (trong bảng) =====
  document.querySelectorAll('form.js-update-form input[name="tenCuocThi"]').forEach(input => {
    input.addEventListener('change', (e) => {
      const form = e.target.closest('form.js-update-form');
      const init = e.target.dataset.init || '';
      const now  = e.target.value.trim();
      if (now === init) return;
      openConfirm(`Đổi tên cuộc thi từ “${init}” → “${now}”?`,
        () => form.submit(),
        () => { e.target.value = init; }
      );
    });
  });

  document.querySelectorAll('form.js-update-form input[name="trangThai"]').forEach(chk => {
    chk.addEventListener('change', (e) => {
      const form = e.target.closest('form.js-update-form');
      const init = (e.target.dataset.init === '1');
      const now  = e.target.checked;
      if (now === init) return;
      openConfirm(`Xác nhận ${now ? 'BẬT' : 'TẮT'} cuộc thi này?`,
        () => form.submit(),
        () => { e.target.checked = init; }
      );
    });
  });

  // ===== FORM TẠO MỚI: CHỈ HỎI XÁC NHẬN KHI BẤM NÚT "TẠO" =====
  const createForm = document.getElementById('create-form');
  if (createForm) {
    let allowSubmit = false;
    createForm.addEventListener('submit', function (e) {
      if (allowSubmit) return;            // lần 2: cho qua
      e.preventDefault();                 // chặn submit lần đầu để mở popup
      const ten = (createForm.querySelector('input[name="tenCuocThi"]')?.value || '').trim();
      const on  = createForm.querySelector('input[name="trangThai"]')?.checked;
      const msg = `Tạo cuộc thi “${ten || '(không tên)'}”${on ? ' (BẬT ngay)' : ''}?`;
      openConfirm(msg, () => {
        allowSubmit = true;               // bật cờ để submit thật
        createForm.submit();
      });
    });
  }


    // tuỳ chọn: expose nếu muốn gọi tay trong console
    window.openConfirm = openConfirm;
  } else {
    console.warn('[confirm] modal elements not found');
  }

  // === Client-side validate cho form "Thêm bài" ===
  (function initCreateBtValidation() {
    // quét tất cả form có action=create_bt
    document.querySelectorAll('form').forEach(function (f) {
      const act = f.querySelector('input[name="action"]')?.value;
      if (act !== 'create_bt') return;

      const methodSel = f.querySelector('select[name="phuongThucCham"]');
      const maxInput  = f.querySelector('input[name="cachChamDiem"]');

      function clearError(el) {
        if (!el) return;
        el.classList.remove('is-invalid');
        const tip = el.parentElement.querySelector('.error-tip');
        if (tip) tip.remove();
        el.setAttribute('aria-invalid', 'false');
      }
      function addError(el, msg) {
        if (!el) return;
        clearError(el);
        el.classList.add('is-invalid');
        el.setAttribute('aria-invalid', 'true');
        const tip = document.createElement('span');
        tip.className = 'error-tip';
        tip.textContent = msg;
        (el.parentElement || el).appendChild(tip);
        el.focus();
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }

      // gỡ lỗi khi người dùng thay đổi
      ['change','input'].forEach(evt => {
        maxInput && maxInput.addEventListener(evt, () => clearError(maxInput));
        methodSel && methodSel.addEventListener(evt, () => clearError(maxInput));
      });

      f.addEventListener('submit', function (e) {
        let hasErr = false;

        // ✅ CHỈ check thang điểm: bắt buộc nhập max điểm hợp lệ
        if (methodSel && methodSel.value === 'POINTS') {
          const v = (maxInput?.value || '').trim();
          if (!v || isNaN(v) || Number(v) < 1) {
            hasErr = true;
            addError(maxInput, 'Nhập điểm tối đa (≥ 1).');
          }
        }

        if (hasErr) {
          e.preventDefault();
        }
      });
    });
  })();
// ===== Đổi tên VÒNG THI: tự bật popup khi rời input (sự kiện change) =====
(function initRenameVTConfirm() {
  if (typeof window.openConfirm !== 'function') return;

  document.querySelectorAll('form.js-rename-vt-form input[name="tenVongThi"]').forEach((input) => {
    const form = input.closest('form.js-rename-vt-form');
    if (!form) return;

    let lastConfirmed = (input.dataset.init || input.value || '').trim();

    input.addEventListener('change', () => {
      const now = (input.value || '').trim();

      // Không đổi hoặc người dùng xoá trắng -> trả về giá trị đã xác nhận
      if (!now || now === lastConfirmed) {
        input.value = lastConfirmed;
        return;
      }

      const msg = `Bạn có muốn đổi tên vòng thi:\n“${lastConfirmed}” → “${now}”?`;
      openConfirm(
        msg,
        // OK -> submit form rename_vt
        () => {
          lastConfirmed = now;
          form.submit();
        },
        // Cancel -> khôi phục
        () => {
          input.value = lastConfirmed;
        }
      );
    });
  });
})();

  // === Thu gọn / mở rộng Vòng thi ===
  (function initToggleVT() {
    document.body.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-vt-toggle]');
      if (!btn) return;

      const id = btn.getAttribute('data-vt-toggle');
      const body = document.querySelector(`[data-vt-body="${id}"]`);
      if (!body) return;

      const isHidden = body.style.display === 'none';
      body.style.display = isHidden ? '' : 'none';

      // đổi trạng thái mũi tên
      btn.classList.toggle('is-collapsed', !isHidden);
    });
  })();

  // === Xóa Vòng thi ===
  (function initDeleteVT() {
    const modal = document.getElementById("delete-vt-modal");
    const msg = document.getElementById("delete-vt-message");
    const btnOk = document.getElementById("delete-vt-ok");
    const btnCancel = document.getElementById("delete-vt-cancel");

    let currentId = null;

    // Mở modal khi click nút x vòng thi
    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-delete-vt]");
      if (!btn) return;

      currentId = btn.getAttribute("data-vtid");
      const name = btn.getAttribute("data-vtname") || "";

      msg.textContent = `Bạn có muốn xóa vòng thi “${name}”?`;
      modal.style.display = "flex";
    });

    btnCancel.addEventListener("click", () => {
      modal.style.display = "none";
      currentId = null;
    });

    btnOk.addEventListener("click", async () => {
      if (!currentId) return;

      try {
        const form = new FormData();
        form.append("action", "delete_vt");
        form.append("vongThi_id", currentId);

        const res = await fetch(window.location.pathname, {
          method: "POST",
          body: form,
          headers: {
            "X-CSRFToken": document.cookie.match(/csrftoken=([^;]+)/)[1]
          }
        });

        const txt = await res.text();
        console.log(txt);
        location.reload();
      } catch (err) {
        alert("Không thể xóa vòng thi: " + err.message);
      }
    });

    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.style.display = "none";
    });
  })();

  // === Xóa bài thi ===
  (function initDeleteBT() {
    const modal = document.getElementById("delete-bt-modal");
    const msg = document.getElementById("delete-bt-message");
    const btnOk = document.getElementById("delete-bt-ok");
    const btnCancel = document.getElementById("delete-bt-cancel");

    let currentId = null;

    // Mở modal khi click xoá
    document.body.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-delete-bt]");
      if (!btn) return;

      currentId = btn.getAttribute("data-btid");
      const name = btn.getAttribute("data-btname");

      msg.textContent = `Bạn có muốn xóa bài thi “${name}”?`;
      modal.style.display = "flex";

      // đóng menu 3 chấm
      const menu = btn.closest(".kebab")?.querySelector(".kebab-menu");
      if (menu) menu.style.display = "none";
    });

    // Hủy
    btnCancel.addEventListener("click", () => {
      modal.style.display = "none";
      currentId = null;
    });

    // Đồng ý
    btnOk.addEventListener("click", async () => {
      if (!currentId) return;

      try {
        const form = new FormData();
        form.append("action", "delete_bt");
        form.append("baiThi_id", currentId);

        const res = await fetch(window.location.pathname, {
          method: "POST",
          body: form,
          headers: {
            "X-CSRFToken": document.cookie.match(/csrftoken=([^;]+)/)[1]
          }
        });

        const txt = await res.text();
        console.log(txt);

        location.reload();  
      } catch (err) {
        alert("Không thể xóa bài thi: " + err.message);
      }
    });

    // Click nền để đóng
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.style.display = "none";
    });
  })();
});


