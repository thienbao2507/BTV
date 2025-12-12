/* Build bảng, filter/sort, sticky 3 cột trái + AUTO-FIT WIDTH THEO NỘI DUNG */

(function () {
  const columns = window.EXPORT_COLUMNS || [];
  const rows = window.EXPORT_ROWS || [];
  const FROZEN = window.FROZEN_COUNT || 3;
  const SPECIAL_GROUPS = window.SPECIAL_GROUPS || [];
  // ==== Cột Tổng + Tổng thời gian (export thường) ====
  const TOTAL_IDX = columns.indexOf('Tổng');
  const TOTAL_TIME_IDX = columns.indexOf('Tổng thời gian');

  // ==== Cột đặc biệt cho Chung Kết ====
  const FINAL_STARS_IDX = columns.indexOf('Đối kháng'); // cột sao
  const FINAL_HEART_IDX = columns.indexOf('Tim');       // cột tim

  const head = document.getElementById('head-row');
  const filter = document.getElementById('filter-row');
  const body = document.getElementById('body-rows');
  const table = document.getElementById('exportTable');
  // ===== CẤU HÌNH WIDTH CỐ ĐỊNH CHO CỘT "BÀI THI" =====
  const SCORE_COL_WIDTH = 100;   // px. Có thể chỉnh 96 / 110 tùy ý.
  const SCORE_COL_MIN = 90;    // px. Sàn để tránh hẹp quá.
  const SCORE_COL_MAX = 140;   // px. Trần nếu bạn muốn nới.
  function normalizeSttStr(s) {
    const t = String(s ?? '').trim();
    if (!t) return '';
    // bỏ 0 ở đầu nhưng giữ lại "0"
    return t.replace(/^0+(?=\d)/, '');
  }
  // --- Utilities ---
  const fmtHeader = (title) => (title ?? '').toString().replace(/\n/g, '<br>');

  // CỘT ĐIỂM = tiêu đề có xuống dòng "Vòng\nBài thi" (và không phải chữ "Thời gian")
  const isScoreCol = (title) => !!title && title.includes('\n') && title !== 'Thời gian';

  // CỘT THỜI GIAN: là "Thời gian" và đứng NGAY SAU một cột điểm
  const isTimeColAt = (idx) => {
    const t = columns[idx];
    if (t === 'Tổng thời gian') return true;
    return t === 'Thời gian' && idx > 0 && isScoreCol(columns[idx - 1]);
  };


  // --- Render header + filter ---
  columns.forEach((name, i) => {
    const th = document.createElement('th');
    th.innerHTML = fmtHeader(name);
    th.dataset.index = i;

    const isHeartCol = (i === FINAL_HEART_IDX);

    // sort
    // - Tắt sort ở cột Thời gian (export thường)
    // - Và tắt luôn sort ở cột "Tim" (Chung Kết)
    if (isTimeColAt(i) || isHeartCol) {
      th.style.cursor = 'default';
      th.title = isHeartCol
        ? 'Sắp xếp theo Tim đã tắt'
        : 'Sắp xếp theo thời gian đã tắt';
    } else {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => toggleSort(i));
    }

    head.appendChild(th);


    // filter inputs
    const fh = document.createElement('th');
    const ip = document.createElement('input');
    ip.placeholder = 'Lọc...';
    ip.dataset.index = i;
    ip.addEventListener('input', applyFilters);
    fh.appendChild(ip);
    filter.appendChild(fh);
  });

  // --- Render body ---
  let viewRows = rows.map((r, idx) => ({ r, _i: idx }));
  window.viewRows = viewRows;
  function renderBody(data = viewRows) {
    body.innerHTML = '';
    const frag = document.createDocumentFragment();
    data.forEach(({ r }, rowIdx) => {
      const tr = document.createElement('tr');
      r.forEach((cell, i) => {
        const td = document.createElement('td');
        if (i === 0) {
          td.textContent = rowIdx + 1;
        } else {
          td.textContent = (cell === null || cell === undefined) ? '' : cell;
        }
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    });
    body.appendChild(frag);
    window.viewRows = data;
    autoFit();
    applySticky();
  }


  renderBody();

  function applyFilters() {
    const inputs = Array.from(document.querySelectorAll('#filter-row input, #filter-row select'));
    const queries = inputs.map(el => (el.value || '').toString().trim());

    const filtered = [];
    for (const obj of rows.map((r, idx) => ({ r, _i: idx }))) {
      let ok = true;
      for (let j = 0; j < queries.length; j++) {
        const qRaw = queries[j];
        if (!qRaw) continue;

        const cellRaw = (obj.r[j] ?? '').toString().trim();

        if (j === 0) {
          // ===== CỘT STT =====
          const cellNorm = normalizeSttStr(cellRaw);  // "01" -> "1"
          const qNorm = normalizeSttStr(qRaw);

          const typedHasLeadingZero = /^0+\d+$/.test(qRaw);  // gõ "01", "0007", ...

          let hit;
          if (typedHasLeadingZero) {
            // Người dùng cố ý gõ 0 ở đầu => so sánh số CHÍNH XÁC
            const a = Number.parseInt(cellNorm || '0', 10);
            const b = Number.parseInt(qNorm || '0', 10);
            hit = (a === b);
          } else {
            // Gõ bình thường (vd "1") => substring (bao gồm 1, 10, 21, ...)
            hit = cellNorm.includes(qNorm) || cellRaw.toLowerCase().includes(qRaw.toLowerCase());
          }

          if (!hit) { ok = false; break; }
        } else {
          // ===== CỘT KHÁC =====
          if (!cellRaw.toLowerCase().includes(qRaw.toLowerCase())) { ok = false; break; }
        }

      }
      if (ok) filtered.push(obj);
    }
    viewRows = filtered;
    window.viewRows = viewRows;     // để nút Export lấy đúng phần đang xem
    renderBody(filtered);
  }


  // --- Sorting ---
  const sortState = { index: null, dir: 1 }; // 1=asc, -1=desc
function toggleSort(i) {
  if (sortState.index === i) {
    sortState.dir *= -1;
  } else {
    sortState.index = i;
    sortState.dir = (i === TOTAL_IDX ? -1 : 1);
  }

  viewRows.sort(compare(i, sortState.dir));
  window.viewRows = viewRows;
  renderBody(viewRows);

  // UI cue
  Array.from(head.children).forEach((th, j) => {
    const base = columns[j] || '';
    th.innerHTML = fmtHeader(base + (j === sortState.index ? (sortState.dir === 1 ? ' ▲' : ' ▼') : ''));
  });
}


  function parseTimeToSec(v) {
    if (v === null || v === undefined) return Infinity;
    const s = String(v).trim();
    // mm:ss
    const m = s.match(/^(\d+):(\d{2})$/);
    if (m) return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
    // fallback: nếu là số (giây)
    const f = parseFloat(s);
    return Number.isFinite(f) ? f : Infinity;
  }

function compare(i, dir) {
  return (a, b) => {
    const va = a.r[i], vb = b.r[i];
    const na = parseFloat(va), nb = parseFloat(vb);
    const bothNum = Number.isFinite(na) && Number.isFinite(nb);

    // === ƯU TIÊN NHÓM CHO CỘT "Tổng": Winner(2) > Loser(1) > None(0) ===
    if (i === TOTAL_IDX) {
      const gA = Number.isFinite(SPECIAL_GROUPS[a._i]) ? SPECIAL_GROUPS[a._i] : 0;
      const gB = Number.isFinite(SPECIAL_GROUPS[b._i]) ? SPECIAL_GROUPS[b._i] : 0;
      if (gA !== gB) {
        // Luôn ép Winner > Loser > None, độc lập với dir
        return gB - gA;
      }
    }

    // So sánh chính theo cột đang chọn (giữ hành vi cũ)
    let primary = 0;
    if (bothNum) primary = (na - nb) * dir;
    else primary = (String(va ?? '')).localeCompare(String(vb ?? ''), 'vi', { numeric: true }) * dir;
    if (primary !== 0) return primary;

    // === TIE-BREAK riêng cho cột "Tổng": dùng "Tổng thời gian" ===
    if (i === TOTAL_IDX && TOTAL_TIME_IDX !== -1) {
      const ta = parseTimeToSec(a.r[TOTAL_TIME_IDX]);
      const tb = parseTimeToSec(b.r[TOTAL_TIME_IDX]);
      if (ta !== tb) return ta - tb; // thời gian ít hơn đứng trên
    }

      // === TIE-BREAK cho Export thường: cột điểm -> thời gian ===
      if (isScoreCol(columns[i])) {
        const timeIdx = i + 1;
        const ta = parseTimeToSec(a.r[timeIdx]);
        const tb = parseTimeToSec(b.r[timeIdx]);
        if (ta !== tb) return ta - tb;
      }

      // === TIE-BREAK cho Chung Kết: sort Đối kháng thì so tiếp Tim ===
      if (i === FINAL_STARS_IDX && FINAL_HEART_IDX !== -1) {
        const ha = parseFloat(a.r[FINAL_HEART_IDX]) || 0;
        const hb = parseFloat(b.r[FINAL_HEART_IDX]) || 0;
        const heartDiff = (ha - hb) * dir;   // cùng chiều với sao: dir= -1 → nhiều Tim đứng trên
        if (heartDiff !== 0) return heartDiff;
      }

      // Cuối cùng: giữ thứ tự ổn định
      return a._i - b._i;
    };
  }



  // --- Auto-fit width theo nội dung ---
  function autoFit() {
    // Tạo/đảm bảo colgroup
    let colgroup = table.querySelector('colgroup');
    if (!colgroup) {
      colgroup = document.createElement('colgroup');
      for (let i = 0; i < columns.length; i++) colgroup.appendChild(document.createElement('col'));
      table.insertBefore(colgroup, table.firstChild);
    } else {
      // sync số col
      const diff = columns.length - colgroup.children.length;
      if (diff > 0) for (let i = 0; i < diff; i++) colgroup.appendChild(document.createElement('col'));
      if (diff < 0) for (let i = 0; i < -diff; i++) colgroup.lastElementChild.remove();
    }



    // Measurer
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    // Lấy style để biết font & padding
    const anyTH = head.children[0];
    const anyTD = body.querySelector('td');
    const thStyle = anyTH ? getComputedStyle(anyTH) : null;
    const tdStyle = anyTD ? getComputedStyle(anyTD) : null;

    const thPadX = thStyle ? (parseFloat(thStyle.paddingLeft) + parseFloat(thStyle.paddingRight)) : 16;
    const tdPadX = tdStyle ? (parseFloat(tdStyle.paddingLeft) + parseFloat(tdStyle.paddingRight)) : 16;

    const thFont = thStyle ? `${thStyle.fontWeight} ${thStyle.fontSize} ${thStyle.fontFamily}` : '700 16px system-ui';
    const tdFont = tdStyle ? `${tdStyle.fontWeight} ${tdStyle.fontSize} ${tdStyle.fontFamily}` : '400 14px system-ui';

    const buffer = 18;           // đệm thêm cho dễ thở
    const MAX_COL = 480;         // trần cho cột auto-fit
    const MIN_DEFAULT = 60;      // sàn cho cột auto-fit

    // Sàn riêng cho 3 cột trái (STT/Mã NV/Họ tên)
    const minFor = (i) => (i === 0 ? 36 : i === 1 ? 70 : i === 2 ? 150 : i === 3 ? 110 : MIN_DEFAULT);

    for (let i = 0; i < columns.length; i++) {
      const header = columns[i] ? String(columns[i]) : '';

      // ===== Nếu là cột "BÀI THI": set cố định và bỏ đo =====
      if (isScoreCol(header, i)) {
        const fixed = Math.max(SCORE_COL_MIN, Math.min(SCORE_COL_MAX, SCORE_COL_WIDTH));
        colgroup.children[i].style.width = `${fixed}px`;
        continue;
      }

      // ===== Ngược lại (meta/info): auto-fit như cũ =====
      let maxW = 0;

      // đo header (2 dòng tách bằng \n)
      const headerLines = header.split('\n');
      ctx.font = thFont;
      headerLines.forEach(line => {
        const w = ctx.measureText(line).width;
        if (w > maxW) maxW = w;
      });
      maxW += thPadX;

      // đo body cells (giới hạn 200 hàng cho nhanh)
      ctx.font = tdFont;
      const limit = Math.min(viewRows.length, 200);
      for (let r = 0; r < limit; r++) {
        const val = viewRows[r].r[i];
        const text = (val === null || val === undefined) ? '' : String(val);
        const w = ctx.measureText(text).width + tdPadX;
        if (w > maxW) maxW = w;
      }

      const final = Math.max(minFor(i), Math.min(MAX_COL, Math.ceil(maxW + buffer)));
      colgroup.children[i].style.width = `${final}px`;
    }
  }


  function applySticky() {
    // gỡ class cũ
    table.querySelectorAll('.sticky-col,.sticky-shadow').forEach(el => {
      el.classList.remove('sticky-col', 'sticky-shadow');
      el.style.left = '';
    });

    // đo width từng cột header (đã autoFit bằng <colgroup>)
    const colWidths = Array.from(head.children).map(th => th.getBoundingClientRect().width);

    // tính left offset tích luỹ cho FROZEN cột
    const lefts = [];
    let acc = 0;
    for (let k = 0; k < Math.min(FROZEN, colWidths.length); k++) {
      lefts[k] = acc;
      acc += (colWidths[k] || 0);
    }
    const LAST = Math.min(FROZEN, colWidths.length) - 1;

    const stickRow = (rowEl) => {
      const cells = rowEl.children;
      for (let k = 0; k <= LAST; k++) {
        const td = cells[k];
        if (!td) break;
        td.classList.add('sticky-col');
        td.style.left = lefts[k] + 'px';
        if (k === LAST) td.classList.add('sticky-shadow'); // chỉ cột ngoài cùng có bóng ranh giới
      }
    };
    stickRow(head);
    stickRow(filter);
    body.querySelectorAll('tr').forEach(stickRow);
  }


  // Re-calc khi resize/zoom
  window.addEventListener('resize', () => { autoFit(); applySticky(); });

  // fonts có thể load chậm → đo lại sau một vòng frame
  requestAnimationFrame(() => { autoFit(); applySticky(); });


  function buildVisiblePayload() {
    const colKinds = (window.EXPORT_COLUMNS || []).map(h => isScoreCol(h) ? 'score' : 'info');
    const rows = (window.viewRows || []).map(obj => obj.r);  // đúng thứ tự đang hiển thị
    return { columns: window.EXPORT_COLUMNS || [], rows, col_kinds: colKinds };
  }

  async function exportVisible(e) {
    e.preventDefault();
    const a = e.currentTarget;
    const url = a.getAttribute('href');
    const payload = buildVisiblePayload();

    // CSRF (nếu dùng Django CSRF cookie)
    const csrftoken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];

    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(csrftoken ? { 'X-CSRFToken': csrftoken } : {})
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) { alert('Xuất XLSX thất bại.'); return; }

    const blob = await res.blob();
    const dl = document.createElement('a');
    dl.href = URL.createObjectURL(blob);
    // lấy filename từ header nếu có
    const dispo = res.headers.get('Content-Disposition') || '';
    const m = dispo.match(/filename="([^"]+)"/i);
    dl.download = m ? m[1] : 'export.xlsx';
    document.body.appendChild(dl);
    dl.click();
    dl.remove();
  }

  document.getElementById('exportVisibleBtn')?.addEventListener('click', exportVisible);

})();
