(function(){
  const table = document.getElementById('rankTable');
  if(!table) return;

  const tbody = document.getElementById('rankBody');
  const rows  = Array.from(tbody ? tbody.querySelectorAll('tr') : []);
  if(rows.length === 0) return;

  // Có đang lọc theo Tên/Đơn vị hay không
  const IS_FILTERED = table.dataset.filtered === '1';

  // Khi lọc: hiển thị hết tất cả hàng, không phân trang – không auto chạy
  const pageSize     = IS_FILTERED ? rows.length : parseInt(table.dataset.pageSize || '10', 10);
  const intervalMs   = parseInt(table.dataset.intervalMs || '3000', 10);
  const colGroupSize = IS_FILTERED ? 9999 : parseInt(table.dataset.colGroupSize || '5', 10);
  // === Auto-reload khi chạy hết danh sách và quay lại từ đầu ===
  const RELOAD_ON_LOOP = !IS_FILTERED;     // nếu đang lọc thì tắt reload
  const RELOAD_DELAY_MS = 600;             // chờ 0.6s cho mượt
  let _didLoopReload = false;              // chặn reload nhiều lần trong cùng vòng
  const NO_MOVE_RELOAD_TICKS = 1;          // sau bao nhiêu lần advance mà không đổi trạng thái thì reload
  let _noMoveTicks = 0;
  const thead = table.tHead;
  const vtRow = thead.rows[0];                   // hàng Vòng thi
  const btRow = thead.rows[thead.rows.length-1]; // hàng Bài thi

  // Trong BODY: vị trí bắt đầu các cột biến thiên
  // Giờ ta có 5 cột cố định: STT, Mã NV, Họ tên, Đơn vị, Đã hoàn thành
  const fixedPrefixCount = 5;
  const testsStartIndex  = fixedPrefixCount;

  // === Xây mapping header->body bằng cách duyệt tuần tự btRow ===
  const headerCells = Array.from(btRow.cells); // chỉ gồm: [..col-test..][..col-group-total..]
  const sampleCells = Array.from(rows[0].cells);

  // Cột "Đã hoàn thành" nằm ở index 4 (sau 4 cột đầu)
  const doneBodyIndex  = 4;

  // Cột Tổng vẫn là cột cuối cùng
  const totalBodyIndex = sampleCells.length - 1;

  let bodyCursor = testsStartIndex;
  const headerToBodyIndex = headerCells.map(() => 0);
  headerCells.forEach((_, hIdx) => {
    headerToBodyIndex[hIdx] = bodyCursor;
    bodyCursor += 1;
  });

  // Lấy lại các NodeLists cần dùng
  const groupThs      = Array.from(vtRow.querySelectorAll('th.vt-group'));
  const testHeaderThs = headerCells.filter(th => th.classList.contains('col-test'));
  const groupTotalThs = headerCells.filter(th => th.classList.contains('col-group-total'));

  // === Meta cho từng Vòng (tìm đúng body index theo mapping mới) ===
  const groupsMeta = groupThs.map((gth, gi) => {
    const tests = headerCells.filter(th =>
      th.classList.contains('col-test') && parseInt(th.dataset.groupIndex, 10) === gi
    );
    const totalTh = headerCells.find(th =>
      th.classList.contains('col-group-total') && parseInt(th.dataset.groupIndex, 10) === gi
    );

    const headerTestIndexes = tests.map(th => headerCells.indexOf(th));
    const bodyTestIndexes   = headerTestIndexes.map(hIdx => headerToBodyIndex[hIdx]);

    const headerTotalIndex = headerCells.indexOf(totalTh);
    const bodyTotalIndex   = headerToBodyIndex[headerTotalIndex];

    return {
      gi,
      gth,
      tests,
      totalTh,
      bodyTestIndexes,
      bodyTotalIndex,
      collapsed: false,
      originalColspan: parseInt(gth.getAttribute('data-colspan'), 10) || tests.length
    };
  });

  function setGroupCollapsed(meta, collapsed){
    meta.collapsed = collapsed;

    // HEADER: bài thi trong vòng
    meta.tests.forEach(th => {
      if (collapsed) {
        th.classList.add('g-collapsed');   // đánh dấu do gộp
        th.style.display = 'none';
      } else {
        th.classList.remove('g-collapsed');
        th.style.display = '';
      }
    });

    // HEADER: ô "Tổng vòng"
    if (meta.totalTh){
      if (collapsed) {
        meta.totalTh.classList.add('g-total-visible');  // tổng vòng đang hiển thị
        meta.totalTh.style.display = '';
      } else {
        meta.totalTh.classList.remove('g-total-visible');
        meta.totalTh.style.display = 'none';
      }
    }

    // HEADER: Vòng thi (colspan)
    meta.gth.colSpan = collapsed ? 1 : meta.originalColspan;

    // BODY: các ô bài thi trong nhóm
    rows.forEach(tr => {
      const tds = Array.from(tr.cells);
      meta.bodyTestIndexes.forEach(bi => {
        const td = tds[bi];
        if (!td) return;
        if (collapsed) {
          td.classList.add('g-collapsed');
          td.style.display = 'none';
        } else {
          td.classList.remove('g-collapsed');
          td.style.display = '';
        }
      });
      // BODY: ô tổng vòng
      const tdTotal = tds[meta.bodyTotalIndex];
      if (tdTotal){
        if (collapsed) {
          tdTotal.classList.add('g-total-visible');
          tdTotal.style.display = '';
        } else {
          tdTotal.classList.remove('g-total-visible');
          tdTotal.style.display = 'none';
        }
      }
    });
  }

  // Click tiêu đề Vòng để gộp/giãn
  groupThs.forEach((gth, i) => {
    gth.addEventListener('click', () => {
      const meta = groupsMeta[i];
      setGroupCollapsed(meta, !meta.collapsed);
      showRowPage(); // refresh
    });
  });

  // 1) Chỉ QUÉT NGANG theo BÀI THI (không tính cột “Tổng vòng”)
  const btCells = [...testHeaderThs];              // chỉ <th class="col-test">
  const headerVarIdx = btCells.map((_, i) => i);   // 0..testsCount-1
  const varCount = headerVarIdx.length;
  const btToHeaderIndex = btCells.map(th => headerCells.indexOf(th));
  let colGroups = [];
  if (varCount <= colGroupSize) {
    colGroups = [headerVarIdx];                    // không quét ngang khi <= colGroupSize
  } else {
    // Chia liên tiếp 5-5-5…; trang cuối có thể <5
    for (let start = 0; start < varCount; start += colGroupSize) {
      const end = Math.min(start + colGroupSize, varCount);
      colGroups.push(headerVarIdx.slice(start, end));
    }
  }
  const totalColGroups = colGroups.length;

  const totalRowPages  = Math.max(1, Math.ceil(rows.length / pageSize));
  let rowPage = 0;
  let colGroup = 0;

  const pageInfoEl = document.getElementById('pageInfo');

  function applyColumnVisibility(){
    // Xây set "body index" cần hiển thị từ nhóm header đang chọn
    const currentHeaderIdx = new Set(colGroups[colGroup] || headerVarIdx);
    const showBodyIdx = new Set();

    // Giữ 5 cột cố định + cột tổng chung
    for (let i = 0; i < fixedPrefixCount; i++) showBodyIdx.add(i);
    showBodyIdx.add(doneBodyIndex);
    showBodyIdx.add(totalBodyIndex);

    // Thêm các cột bài thi đang active
    (colGroups[colGroup] || headerVarIdx).forEach(hIdx => {
      const headerIndex = btToHeaderIndex[hIdx];           // chuyển chỉ số btCells -> headerCells
      const bIdx = headerToBodyIndex[headerIndex];         // rồi mới map header -> body
      if (typeof bIdx === 'number') showBodyIdx.add(bIdx);
    });

    // Nếu VÒNG nào đang gộp, giữ cột TỔNG-VÒNG luôn hiển thị
    groupsMeta.forEach(meta => {
      if (meta.totalTh && meta.totalTh.classList.contains('g-total-visible')) {
        showBodyIdx.add(meta.bodyTotalIndex);
      }
    });

    // Ẩn/hiện HEADER hàng 2 (chỉ bài thi)
    btCells.forEach((th, i) => {
      if (th.classList.contains('g-collapsed')) { th.style.display = 'none'; return; }
      th.style.display = (totalColGroups <= 1 || currentHeaderIdx.has(i)) ? '' : 'none';
    });

    // CẬP NHẬT HEADER VÒNG: co/giãn theo số bài đang hiển thị
    groupsMeta.forEach(meta => {
      if (meta.collapsed) {
        meta.gth.style.display = '';
        meta.gth.colSpan = 1;
        return;
      }
      let visibleCount = 0;
      meta.tests.forEach(th => {
        const idx = btCells.indexOf(th);
        if (idx !== -1 && (totalColGroups <= 1 || currentHeaderIdx.has(idx)) && th.style.display !== 'none') {
          visibleCount++;
        }
      });
      if (visibleCount > 0) {
        meta.gth.style.display = '';
        meta.gth.colSpan = visibleCount;
      } else {
        meta.gth.style.display = 'none';
        meta.gth.colSpan = meta.originalColspan;
      }
    });

    // Ẩn/hiện BODY theo showBodyIdx (tôn trọng cột đã gộp)
    rows.forEach(tr => {
      const cells = Array.from(tr.cells);
      cells.forEach((td, i) => {
        if (td.classList.contains('g-collapsed')) { td.style.display = 'none'; return; }
        td.style.display = showBodyIdx.has(i) ? '' : 'none';
      });
    });
  } // <--- đóng applyColumnVisibility()

  function showRowPage(){
    // phân trang theo hàng
    rows.forEach(r => r.style.display = 'none');
    const start = rowPage * pageSize;
    const end = Math.min(start + pageSize, rows.length);
    for(let i=start; i<end; i++) rows[i].style.display = '';

    applyColumnVisibility();

    if(pageInfoEl){
      const cg = totalColGroups <= 1 ? 1 : (colGroup + 1);
      pageInfoEl.textContent = `Trang người ${rowPage+1}/${totalRowPages} • Nhóm cột ${cg}/${Math.max(1,totalColGroups)}`;
    }
  }

  function advance(){
    const prevRow = rowPage;
    const prevCol = colGroup;

    // Nếu không có quét ngang (<= colGroupSize) ⇒ chỉ chuyển trang theo hàng
    if(totalColGroups <= 1){
      rowPage = (rowPage + 1) % totalRowPages;
    } else {
      colGroup++;
      if(colGroup >= totalColGroups){
        colGroup = 0;
        rowPage = (rowPage + 1) % totalRowPages;
      }
    }

    showRowPage();

    // 1) Trường hợp "wrap về đầu" (đã khác trước đó) -> reload
    if (
      RELOAD_ON_LOOP &&
      !_didLoopReload &&
      totalRowPages > 0 &&
      rowPage === 0 && colGroup === 0 &&
      (prevRow !== 0 || prevCol !== 0)
    ) {
      _didLoopReload = true;
      setTimeout(() => { location.reload(); }, RELOAD_DELAY_MS);
      return;
    }

    // 2) Trường hợp "không hề di chuyển" (ví dụ chỉ 1 trang/1 nhóm cột) -> đếm tick rồi reload
    const moved = (prevRow !== rowPage) || (prevCol !== colGroup);
    if (RELOAD_ON_LOOP && !_didLoopReload && !moved) {
      _noMoveTicks += 1;
      if (_noMoveTicks >= NO_MOVE_RELOAD_TICKS) {
        _didLoopReload = true;
        setTimeout(() => { location.reload(); }, RELOAD_DELAY_MS);
      }
    } else {
      // Hễ có di chuyển thì reset bộ đếm
      _noMoveTicks = 0;
    }
  }

  // Timer
  let timer = null;
  function startTimer(){ stopTimer(); timer = setInterval(advance, intervalMs); }
  function stopTimer(){ if(timer){ clearInterval(timer); timer = null; } }
  function jumpNext(){ advance(); startTimer(); }

  // Init
  showRowPage();
  if (!IS_FILTERED) {
    startTimer();
  }

  // Click bảng (trừ click vào tiêu đề Vòng) => next
  table.addEventListener('click', (e) => {
    if (IS_FILTERED) return;  // đang lọc thì không cho auto nhảy trang
    if(e.target.closest && e.target.closest('.vt-group')) return;
    jumpNext();
  });

  // Phím điều hướng
  document.addEventListener('keydown', (e) => {
    if (IS_FILTERED) return;  // đang lọc thì không nhảy
    if(e.key === 'ArrowRight'){
      e.preventDefault(); jumpNext();
    } else if(e.key === 'ArrowLeft'){
      e.preventDefault();
      if(totalColGroups <= 1){
        rowPage = (rowPage - 1 + totalRowPages) % totalRowPages;
      } else {
        colGroup--;
        if(colGroup < 0){
          colGroup = totalColGroups - 1;
          rowPage = (rowPage - 1 + totalRowPages) % totalRowPages;
        }
      }
      showRowPage(); startTimer();
    }
  }, { passive: false });

  // Dừng chạy khi rê chuột vùng controls (nếu có)
  const controls = document.querySelector('.controls');
  if(controls && !IS_FILTERED){
    controls.addEventListener('mouseenter', stopTimer);
    controls.addEventListener('mouseleave', startTimer);
  }

  // Toggle gộp/giãn xong thì vẫn giữ logic hiển thị
  window.addEventListener('resize', showRowPage);
})();
