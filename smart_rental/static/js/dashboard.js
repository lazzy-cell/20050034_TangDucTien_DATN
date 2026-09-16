(function () {
  const auth = window.firebaseAuth || (window.firebase && firebase.auth ? firebase.auth() : null);
  if (!auth) { location.href = "/login"; return; }

  auth.onAuthStateChanged(async (user) => {
    if (!user) { location.href = "/login"; return; }
    try {
      const claims = (await user.getIdTokenResult()).claims;
      if (claims.role !== "landlord") { await auth.signOut(); location.href="/login"; return; }
    } catch (e) { console.error(e); await auth.signOut(); location.href="/login"; return; }

    const $ = (id) => document.getElementById(id);
    const esc = (v) => String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    const num = (v,d=1) => v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toLocaleString("vi-VN",{maximumFractionDigits:d});
    const money = (v) => v == null ? "—" : Number(v).toLocaleString("vi-VN") + " ₫";
    const parseDate = (v) => {
      if (!v) return null;
      if (v instanceof Date) return v;
      const s=String(v);
      // Legacy backend records used naive UTC datetimes. Treat them as UTC.
      const normalized=/^(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)$/.test(s) ? s+"Z" : s;
      const d=new Date(normalized);
      return Number.isNaN(d.getTime()) ? null : d;
    };
    const time = (v) => { const d=parseDate(v); return d ? d.toLocaleString("vi-VN",{day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"}) : (v ? String(v) : "—"); };
    const periodNow = () => { const d=new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`; };

    let rooms=[], tenants=[], contracts=[], bills=[];
    let powerChart=null, occChart=null, energyChart=null;

    // Occupancy is a live CV signal. The browser must not keep showing the
    // last known value forever when the backend/module stops sending data.
    const OCCUPANCY_STALE_SECONDS = 120;
    let occupancySnapshot = null;
    let occupancyLastServerDataAt = 0;
    let occupancyLastApiOkAt = 0;

    function normalizeUnixSeconds(value){
      if(value == null || value === "") return null;
      if(typeof value === "string"){
        const n=Number(value);
        if(Number.isFinite(n)) value=n;
        else {
          const parsed=Date.parse(value);
          return Number.isFinite(parsed) ? parsed/1000 : null;
        }
      }
      const n=Number(value);
      if(!Number.isFinite(n)) return null;
      return Math.abs(n)>=100000000000 ? n/1000 : n;
    }

    function occupancyIsFresh(item, nowMs=Date.now()){
      const hb=normalizeUnixSeconds(item?.occupancy_heartbeat_at ?? item?.heartbeat_at);
      if(hb == null) return false;
      return (nowMs/1000 - hb) <= OCCUPANCY_STALE_SECONDS;
    }

    function localizeOccupancyItem(item, nowMs=Date.now()){
      const fresh=occupancyIsFresh(item,nowMs);
      if(!fresh){
        return {
          ...item,
          occupied:null,
          status:"unknown",
          person_count:0,
          confidence:null,
          is_stale:true,
          occupancy_is_stale:true
        };
      }
      const status=item.status || item.occupancy_status ||
        (item.occupied===true?"occupied":item.occupied===false?"vacant":"unknown");
      return {...item,status,occupancy_status:status,is_stale:false,occupancy_is_stale:false};
    }

    function localizeOccupancyData(data){
      const now=Date.now();
      if(!data) return data;
      const rooms=(data.rooms||data.data||[]).map(r=>localizeOccupancyItem(r,now));
      const summary={occupied:0,vacant:0,unknown:0,stale:0,total:rooms.length};
      rooms.forEach(r=>{
        if(r.status==="occupied") summary.occupied++;
        else if(r.status==="vacant") summary.vacant++;
        else summary.unknown++;
        if(r.is_stale) summary.stale++;
      });
      return {...data,rooms,summary,occupied:summary.occupied,vacant:summary.vacant,unknown:summary.unknown,total:summary.total};
    }

    function markLocalOccupancyUnknown(){
      if(!occupancySnapshot) return;
      const localized=localizeOccupancyData(occupancySnapshot);
      const changed=JSON.stringify(localized.summary)!==JSON.stringify(occupancySnapshot.summary);
      occupancySnapshot=localized;

      // If overview has a cached dashboard response, invalidate its CV state
      // without requiring another backend request.
      if(occupancySnapshot._overviewData){
        const d=occupancySnapshot._overviewData;
        const cards=(d.room_cards||[]).map(r=>localizeOccupancyItem(r));
        const summary={occupied:0,vacant:0,unknown:0,total:cards.length,stale:0};
        cards.forEach(r=>{
          const s=r.occupancy_status || r.status;
          if(s==="occupied")summary.occupied++;
          else if(s==="vacant")summary.vacant++;
          else summary.unknown++;
          if(r.occupancy_is_stale)summary.stale++;
        });
        d.room_cards=cards;
        d.occupancy={...d.occupancy,...summary};
        renderOverviewOccupancy(d);
      }

      if(document.querySelector(".nav-item.active")?.dataset.page==="occupancy"){
        renderOccupancySnapshot(occupancySnapshot);
      }
      return changed;
    }

    function renderOverviewOccupancy(d){
      const o=d.occupancy||{occupied:0,vacant:0,unknown:0};
      $("kpiOccupied").textContent=`${num(o.occupied,0)} có người · ${num(o.unknown,0)} chưa rõ`;
      renderOccChart(o);
    }

    function renderOccupancySnapshot(data){
      const d=localizeOccupancyData(data);
      const s=d.summary||d;
      $("occSummary").innerHTML=[
        ["Có người",s.occupied],
        ["Trống",s.vacant],
        ["Chưa rõ",s.unknown]
      ].map(a=>`<div class="stat-chip"><span>${a[0]}</span><b>${num(a[1],0)}</b></div>`).join("");

      $("occupancyList").innerHTML=(d.rooms||[]).map(r=>{
        const status=r.status || "unknown";
        const label=status==="occupied"?"Có người":status==="vacant"?"Trống":"Chưa xác định";
        const badge=status==="occupied"?"badge-active":status==="vacant"?"badge-ended":"badge-off";
        const detail=r.is_stale?" · Mất tín hiệu CV":"";
        return `<div class="history-item flex justify-between items-center gap-3">
          <div><b>${esc(r.room_name||roomName(r.room_id))}</b>
            ${r.heartbeat_at!=null?`<div class="text-xs text-slate-500 mt-1">Heartbeat server: ${time(new Date(normalizeUnixSeconds(r.heartbeat_at)*1000).toISOString())}</div>`:""}
          </div>
          <span class="badge ${badge}">${label}${detail}</span>
        </div>`;
      }).join("")||`<div class="text-slate-500">Chưa có dữ liệu.</div>`;
    }

    // Runs independently of API refreshes. Once the last SERVER heartbeat
    // expires, the UI changes to UNKNOWN even if the backend is unreachable.
    setInterval(()=>{
      if(occupancySnapshot) markLocalOccupancyUnknown();
    },5000);

    function toast(message,type="ok") {
      const el=$("toast"); el.innerHTML=`<div class="toast-inner toast-${type}">${esc(message)}</div>`;
      el.classList.remove("hidden"); clearTimeout(el._t); el._t=setTimeout(()=>el.classList.add("hidden"),3000);
    }
    function modal(title, html) {
      $("modalTitle").textContent=title; $("modalBody").innerHTML=html;
      $("modal").classList.remove("hidden"); $("modal").classList.add("flex");
    }
    function closeModal(){ $("modal").classList.add("hidden"); $("modal").classList.remove("flex"); $("modalBody").innerHTML=""; }
    $("modalClose").onclick=closeModal; $("modal").onclick=e=>{if(e.target===$("modal"))closeModal();};

    function confirmDialog(title,message,ok="Xác nhận",danger=false){
      return new Promise(resolve=>{
        $("confirmTitle").textContent=title; $("confirmMessage").textContent=message;
        $("confirmOk").textContent=ok; $("confirmOk").className=danger?"btn-danger px-4 py-2 text-sm":"btn-primary";
        $("confirmModal").classList.remove("hidden"); $("confirmModal").classList.add("flex");
        const done=v=>{ $("confirmModal").classList.add("hidden"); $("confirmModal").classList.remove("flex"); resolve(v); };
        $("confirmOk").onclick=()=>done(true); $("confirmCancel").onclick=()=>done(false);
      });
    }

    const roomById=id=>rooms.find(r=>r.room_id===id);
    const tenantById=id=>tenants.find(t=>t.id===id);
    const roomName=id=>roomById(id)?.room_name || "Phòng chưa xác định";
    const tenantName=id=>tenantById(id)?.name || "Chưa có khách";
    function linkedRoomText(t){
      const x=t?.linked_rooms||[];
      return x.length ? x.map(r=>r.room_name).join(", ") : "Chưa gắn phòng";
    }

    async function loadCaches(){
      const [r,t,c]=await Promise.all([API.getRooms(),API.getTenants(),API.getContracts()]);
      rooms=r.data?.data||[]; tenants=t.data?.data||[]; contracts=c.data?.data||[];
    }

    function renderPowerChart(cards){
      const el=$("chartPower"); if(!el||typeof Chart==="undefined")return;
      if(powerChart)powerChart.destroy();
      powerChart=new Chart(el,{type:"bar",data:{labels:cards.map(x=>x.room_name),datasets:[{label:"Công suất (W)",data:cards.map(x=>Number(x.power)||0),borderRadius:5}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
    }
    function renderOccChart(o){
      const el=$("chartOccupancy"); if(!el||typeof Chart==="undefined")return;
      if(occChart)occChart.destroy();
      occChart=new Chart(el,{type:"doughnut",data:{labels:["Có người","Trống","Chưa rõ"],datasets:[{data:[o.occupied,o.vacant,o.unknown]}]},options:{responsive:true,maintainAspectRatio:false}});
    }

    async function loadOverview(){
      try{
        const res=await API.dashboardOverview();
        if(res.ok && res.data?.success){
          const d=res.data.data||{}, r=d.rooms||{};
          // Keep a client-side snapshot so the UI can expire CV data even
          // when subsequent API requests fail or never arrive.
          d.room_cards=(d.room_cards||[]).map(localizeOccupancyItem);
          d.occupancy=localizeOccupancyData({...d.occupancy,rooms:d.room_cards}).summary;
          occupancySnapshot={rooms:d.room_cards,summary:d.occupancy,_overviewData:d};
          occupancyLastApiOkAt=Date.now();
          occupancyLastServerDataAt=Math.max(
            ...d.room_cards.map(x=>normalizeUnixSeconds(x.occupancy_heartbeat_at ?? x.heartbeat_at)||0),
            0
          );
          $("kpiTotal").textContent=num(r.total,0);
          $("kpiOnline").textContent=num(r.online,0);
          $("kpiPower").innerHTML=`${num(d.power?.current_power,0)} <small>W</small>`;
          $("kpiToday").innerHTML=`${num(d.energy?.today_consumption,2)} <small>kWh</small>`;
          renderOverviewOccupancy(d);
          $("billUnpaid").textContent=num(d.billing?.unpaid_bills,0);
          $("billPaid").textContent=num(d.billing?.paid_bills,0);
          $("billRevenue").textContent=money(d.billing?.estimated_revenue);
          $("billDebt").textContent=money(d.billing?.unpaid_amount);
          renderPowerChart(d.room_cards||[]);
          $("overviewRooms").innerHTML=(d.room_cards||[]).map(r=>`
            <div class="card p-4">
              <div class="flex justify-between"><b>${esc(r.room_name)}</b><span class="badge ${r.online?"badge-active":"badge-ended"}">${r.online?"Online":"Offline"}</span></div>
              <div class="text-xs text-slate-400 mt-2">Nguồn: ${r.switch===true?"Bật":r.switch===false?"Tắt":"—"} · ${num(r.power,0)} W</div>
              <button class="btn-sm mt-3" data-view-room="${esc(r.room_id)}">Chi tiết</button>
            </div>`).join("")||`<div class="text-slate-500">Chưa có dữ liệu phòng.</div>`;
          $("overviewRooms").querySelectorAll("[data-view-room]").forEach(b=>b.onclick=()=>viewRoom(b.dataset.viewRoom));
        } else toast(res.data?.message||"Không tải được tổng quan","err");
      }catch(e){console.error(e);toast("Không tải được dữ liệu tổng quan","err");}
    }

    async function fetchPower(r){
      try{const x=await API.getRoomEnergy(r.room_id); return x.data?.data||{};}catch{return {};}
    }

    async function loadRooms(){
      await loadCaches();
      const energies=await Promise.all(rooms.map(fetchPower));
      rooms.forEach((r,i)=>r._energy=energies[i]);
      renderRooms();
    }
    function renderRooms(){
      const el=$("roomsTable");
      if(!rooms.length){el.innerHTML=`<div class="p-6 text-center text-slate-500">Chưa có phòng.</div>`;return;}
      el.innerHTML=`<table class="data"><thead><tr><th><input type="checkbox" id="roomsHeadCheck"></th><th>Phòng</th><th>Khách thuê</th><th>Thiết bị</th><th>Công suất</th><th>Trạng thái</th><th></th></tr></thead><tbody>
      ${rooms.map(r=>{const e=r._energy||{};return `<tr>
        <td><input type="checkbox" class="room-check" value="${esc(r.room_id)}"></td>
        <td><b>${esc(r.room_name||r.room_id)}</b></td><td>${esc(tenantName(r.tenant_id))}</td><td class="text-xs">${esc(r.device_id||"—")}</td>
        <td>${num(e.power??e.current_power,0)} W</td><td><span class="badge ${r.status==="occupied"?"badge-active":"badge-ended"}">${r.status==="occupied"?"Đang thuê":"Trống"}</span></td>
        <td class="whitespace-nowrap"><button class="btn-sm" data-room-electric="${esc(r.room_id)}">Thông số điện</button> <button class="btn-sm" data-room-view="${esc(r.room_id)}">Chi tiết</button> <button class="btn-sm" data-room-edit="${esc(r.room_id)}">Sửa</button> <button class="btn-danger" data-room-del="${esc(r.room_id)}">Xóa</button></td>
      </tr>`}).join("")}</tbody></table>`;
      $("roomsHeadCheck").onchange=e=>{$("roomsTable").querySelectorAll(".room-check").forEach(c=>c.checked=e.target.checked);updateSelected();};
      $("roomsTable").querySelectorAll(".room-check").forEach(c=>c.onchange=updateSelected);
      $("roomsTable").querySelectorAll("[data-room-view]").forEach(b=>b.onclick=()=>viewRoom(b.dataset.roomView));
      $("roomsTable").querySelectorAll("[data-room-electric]").forEach(b=>b.onclick=()=>viewRoomElectrical(b.dataset.roomElectric));
      $("roomsTable").querySelectorAll("[data-room-edit]").forEach(b=>b.onclick=()=>roomForm(roomById(b.dataset.roomEdit)));
      $("roomsTable").querySelectorAll("[data-room-del]").forEach(b=>b.onclick=()=>deleteRoom(b.dataset.roomDel));
      updateSelected();
    }
    function selectedRooms(){return [...document.querySelectorAll(".room-check:checked")].map(x=>x.value);}
    function updateSelected(){$("roomsSelectedCount").textContent=`${selectedRooms().length} phòng được chọn`; }
    async function batchPower(on){
      const ids=selectedRooms(); if(!ids.length)return toast("Hãy chọn ít nhất một phòng","err");
      if(!(await confirmDialog(on?"Bật điện hàng loạt":"Ngắt điện hàng loạt",`Thực hiện với ${ids.length} phòng?`,on?"Bật":"Ngắt",!on)))return;
      const r=await API.setBatchPower(ids,on); toast(r.data?.message||"Đã xử lý",r.ok?"ok":"err"); loadRooms();
    }
    async function deleteRoom(id){if(!(await confirmDialog("Xóa phòng","Hành động không thể hoàn tác.","Xóa",true)))return;const r=await API.deleteRoom(id);toast(r.data?.message||"Lỗi",r.ok?"ok":"err");if(r.ok)loadRooms();}
    async function viewRoom(id){
      const rres=await API.getRoom(id); if(!rres.ok)return toast(rres.data?.message||"Không tải được phòng","err");
      const d=rres.data.data||{}, t=d.tenant, c=d.active_contract, e=d.realtime||{};
      modal(`Phòng ${d.room_name||id}`,`<div class="space-y-4 text-sm">
        <div class="grid grid-cols-2 gap-3">
          <div class="card p-3"><span class="text-slate-500">Tên phòng</span><div class="font-semibold mt-1">${esc(d.room_name)}</div></div>
          <div class="card p-3"><span class="text-slate-500">Trạng thái</span><div class="font-semibold mt-1">${esc(d.status==="occupied"?"Đang thuê":"Trống")}</div></div>
          <div class="card p-3"><span class="text-slate-500">Thiết bị</span><div class="font-semibold mt-1">${esc(d.device_id||"Chưa gắn")}</div></div>
          <div class="card p-3"><span class="text-slate-500">Giới hạn công suất</span><div class="font-semibold mt-1">${num(d.power_limit,0)} W</div></div>
        </div>
        <div class="card p-4">
          <div class="flex items-center justify-between gap-2 mb-3"><h4 class="font-semibold">Thông số điện hiện tại</h4><span class="badge ${e.online?"badge-active":"badge-ended"}">${e.online?"Online":"Offline"}</span></div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div><span class="text-slate-500">Điện áp</span><div class="font-semibold text-lg">${e.voltage!=null?num(e.voltage,1):"—"} V</div></div>
            <div><span class="text-slate-500">Dòng điện</span><div class="font-semibold text-lg">${e.current!=null?num(e.current,2):"—"} A</div></div>
            <div><span class="text-slate-500">Công suất</span><div class="font-semibold text-lg">${num(e.power??e.current_power,1)} W</div></div>
            <div><span class="text-slate-500">Điện năng tích lũy</span><div class="font-semibold text-lg">${e.total_energy!=null?num(e.total_energy,3):"—"} kWh</div></div>
          </div>
          <div class="text-xs text-slate-500 mt-3">Nguồn điện: ${e.switch===true?"Bật":e.switch===false?"Tắt":"—"} · Cập nhật: ${time(e.updated_at)}</div>
        </div>
        <div class="pt-1 flex flex-wrap gap-2">
          ${t?`<button class="btn-primary" id="roomToTenant">Xem khách thuê: ${esc(t.name)}</button>`:"<span class='text-slate-500 self-center'>Chưa có khách thuê.</span>"}
          ${c?`<button class="btn-secondary" id="roomToContract">Xem hợp đồng</button>`:""}
        </div></div>`);
      if(t)$("roomToTenant").onclick=()=>viewTenant(t.id);
      if(c)$("roomToContract").onclick=()=>viewContract(c.id);
    }

    async function viewRoomElectrical(id){
      const rres=await API.getRoom(id); if(!rres.ok)return toast(rres.data?.message||"Không tải được thông số điện","err");
      const d=rres.data.data||{}, e=d.realtime||{};
      modal(`Thông số điện · ${d.room_name||id}`,`<div class="space-y-4 text-sm">
        <div class="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <div class="kpi-card"><div class="kpi-label">Điện áp</div><div class="kpi-value">${e.voltage!=null?num(e.voltage,1):"—"} <small>V</small></div></div>
          <div class="kpi-card"><div class="kpi-label">Dòng điện</div><div class="kpi-value">${e.current!=null?num(e.current,2):"—"} <small>A</small></div></div>
          <div class="kpi-card"><div class="kpi-label">Công suất</div><div class="kpi-value">${num(e.power??e.current_power,1)} <small>W</small></div></div>
          <div class="kpi-card"><div class="kpi-label">Điện năng</div><div class="kpi-value">${e.total_energy!=null?num(e.total_energy,3):"—"} <small>kWh</small></div></div>
          <div class="kpi-card"><div class="kpi-label">Trạng thái CB</div><div class="kpi-value">${e.switch===true?"Bật":e.switch===false?"Tắt":"—"}</div></div>
          <div class="kpi-card"><div class="kpi-label">Thiết bị</div><div class="kpi-value text-base">${e.online?"Online":"Offline"}</div></div>
        </div>
        <div class="card p-4 space-y-2">
          <div><span class="text-slate-500">Phòng:</span> <b>${esc(d.room_name||id)}</b></div>
          <div><span class="text-slate-500">Device ID:</span> ${esc(d.device_id||"—")}</div>
          <div><span class="text-slate-500">Giới hạn:</span> ${num(d.power_limit,0)} W</div>
          <div><span class="text-slate-500">Cập nhật:</span> ${time(e.updated_at)}</div>
        </div>
      </div>`);
    }
    function roomForm(r){
      const edit=!!r;
      modal(edit?"Sửa phòng":"Tạo phòng",`<form id="roomForm" class="form-grid">
        <div class="full"><label class="label">Tên phòng *</label><input class="input" name="room_name" required value="${esc(r?.room_name||"")}"></div>
        <div><label class="label">Device ID (Tuya)</label><input class="input" name="device_id" value="${esc(r?.device_id||"")}"></div>
        <div><label class="label">Giới hạn công suất (W)</label><input class="input" type="number" name="power_limit" value="${esc(r?.power_limit??2500)}"></div>
        <div class="full flex justify-end gap-2"><button type="button" class="btn-secondary" id="formCancel">Hủy</button><button class="btn-primary">Lưu</button></div>
      </form>`);
      $("formCancel").onclick=closeModal;$("roomForm").onsubmit=async e=>{e.preventDefault();const b=Object.fromEntries(new FormData(e.target));b.power_limit=Number(b.power_limit)||2500;const x=edit?await API.updateRoom(r.room_id,b):await API.createRoom(b);toast(x.data?.message||"Lỗi",x.ok?"ok":"err");if(x.ok){closeModal();loadRooms();}};
    }

    async function loadTenants(){const x=await API.getTenants();tenants=x.data?.data||[];renderTenants();}
    function renderTenants(){
      $("tenantsTable").innerHTML=tenants.length?`<table class="data"><thead><tr><th>Họ tên</th><th>SĐT</th><th>CCCD</th><th>Email</th><th>Phòng đang thuê</th><th>TT</th><th></th></tr></thead><tbody>
      ${tenants.map(t=>{const locked=(t.active_contracts||[]).length>0;return `<tr><td><b>${esc(t.name)}</b></td><td>${esc(t.phone||"—")}</td><td>${esc(t.identity_number||"—")}</td><td class="text-xs">${esc(t.email||"—")}</td><td>${esc(linkedRoomText(t))}</td><td><span class="badge ${t.status==="active"?"badge-active":"badge-ended"}">${esc(t.status)}</span></td>
      <td class="whitespace-nowrap"><button class="btn-sm" data-tenant-view="${esc(t.id)}">Chi tiết</button> <button class="btn-sm" data-tenant-edit="${esc(t.id)}">Sửa</button> <button class="btn-sm" data-tenant-reset="${esc(t.id)}">Gửi mail reset mật khẩu</button> <button class="btn-danger ${locked?"opacity-50 cursor-not-allowed":""}" data-tenant-del="${esc(t.id)}" ${locked?"disabled":""} title="${locked?"Không thể xóa vì khách đang có hợp đồng còn hiệu lực":"Xóa khách thuê"}">${locked?"Đang có HĐ":"Xóa"}</button></td></tr>`}).join("")}</tbody></table>`:`<div class="p-6 text-center text-slate-500">Chưa có khách thuê.</div>`;
      $("tenantsTable").querySelectorAll("[data-tenant-view]").forEach(b=>b.onclick=()=>viewTenant(b.dataset.tenantView));
      $("tenantsTable").querySelectorAll("[data-tenant-edit]").forEach(b=>b.onclick=()=>tenantForm(tenantById(b.dataset.tenantEdit)));
      $("tenantsTable").querySelectorAll("[data-tenant-reset]").forEach(b=>b.onclick=()=>resetTenant(b.dataset.tenantReset));
      $("tenantsTable").querySelectorAll("[data-tenant-del]").forEach(b=>b.onclick=()=>deleteTenant(b.dataset.tenantDel));
    }
    async function resetTenant(id){
      const t=tenantById(id);if(!t?.email)return toast("Khách chưa có email","err");
      if(!(await confirmDialog("Đặt lại mật khẩu",`Gửi email đặt lại mật khẩu tới ${t.email}?`,"Gửi email")))return;
      try{await firebase.auth().sendPasswordResetEmail(t.email);toast("Đã gửi email đặt lại mật khẩu");}catch(e){toast(e.message||"Không thể gửi email","err");}
    }
    async function deleteTenant(id){
      const t=tenantById(id);
      if((t?.active_contracts||[]).length){
        return toast("Không thể xóa khách thuê đang gắn với hợp đồng còn hiệu lực.","err");
      }
      if(!(await confirmDialog("Xóa khách thuê","Hành động không thể hoàn tác.","Xóa",true)))return;
      const x=await API.deleteTenant(id);
      toast(x.data?.message||"Lỗi",x.ok?"ok":"err");
      if(x.ok){await loadTenants();await loadCaches();}
    }
    async function viewTenant(id){
      const t=tenantById(id)||((await API.getTenant?.(id))?.data?.data);
      if(!t)return;
      modal(`Khách thuê: ${t.name}`,`<div class="space-y-3 text-sm">
        <div><span class="text-slate-500">Họ tên:</span> <b>${esc(t.name)}</b></div><div><span class="text-slate-500">Số điện thoại:</span> ${esc(t.phone||"—")}</div>
        <div><span class="text-slate-500">Email:</span> ${esc(t.email||"—")}</div><div><span class="text-slate-500">CCCD:</span> ${esc(t.identity_number||"—")}</div><div><span class="text-slate-500">Địa chỉ:</span> ${esc(t.address||"—")}</div>
        <div><span class="text-slate-500">Trạng thái:</span> ${esc(t.status||"—")}</div>
        <div class="pt-2"><b>Đối tượng liên kết</b><div class="flex flex-wrap gap-2 mt-2">${(t.active_contracts||[]).map(c=>`<button class="btn-secondary" data-tenant-contract="${esc(c.id)}">Hợp đồng · ${esc(c.room_name)}</button>`).join("")||"<span class='text-slate-500'>Chưa có hợp đồng active.</span>"}</div></div>
        <div class="flex flex-wrap gap-2 pt-2"><button class="btn-primary" id="tenantResetDetail">Gửi mail reset mật khẩu</button></div></div>`);
      $("tenantResetDetail").onclick=()=>resetTenant(id);
      $("modalBody").querySelectorAll("[data-tenant-contract]").forEach(b=>b.onclick=()=>viewContract(b.dataset.tenantContract));
    }
    function tenantForm(t){
      const edit=!!t;
      modal(edit?"Sửa khách thuê":"Đăng ký khách thuê mới",`<form id="tenantForm" class="form-grid">
        <div><label class="label">Họ tên *</label><input class="input" name="name" required value="${esc(t?.name||"")}"></div>
        <div><label class="label">Số điện thoại *</label><input class="input" name="phone" required value="${esc(t?.phone||"")}"></div>
        <div><label class="label">Email *</label><input class="input" type="email" name="email" required value="${esc(t?.email||"")}"></div>
        <div><label class="label">CCCD / CMND</label><input class="input" name="identity_number" value="${esc(t?.identity_number||"")}"></div>
        <div class="full"><label class="label">Địa chỉ thường trú</label><input class="input" name="address" value="${esc(t?.address||"")}"></div>
        ${!edit?`<div class="full rounded-lg border border-sky-500/20 bg-sky-500/5 px-3 py-2 text-xs text-sky-300">Sau khi tạo, hệ thống sẽ tự động gửi email đặt lại mật khẩu tới địa chỉ email này. Không cần nhập mật khẩu ban đầu.</div>`:""}
        <div><label class="label">Trạng thái</label><select class="input" name="status"><option value="active" ${!t||t.status==="active"?"selected":""}>active</option><option value="inactive" ${t?.status==="inactive"?"selected":""}>inactive</option></select></div>
        <div class="full flex justify-end gap-2"><button type="button" class="btn-secondary" id="formCancel">Hủy</button><button class="btn-primary">${edit?"Lưu":"Đăng ký"}</button></div></form>`);
      $("formCancel").onclick=closeModal;$("tenantForm").onsubmit=async e=>{e.preventDefault();const b=Object.fromEntries(new FormData(e.target));const x=edit?await API.updateTenant(t.id,b):await API.createTenant(b);if(x.ok&&x.data?.success){if(!edit){try{await firebase.auth().sendPasswordResetEmail(b.email.trim().toLowerCase());toast("Đã tạo khách thuê và gửi email đặt lại mật khẩu tới "+b.email,"ok");}catch(mailErr){console.error(mailErr);toast("Đã tạo khách thuê nhưng không gửi được email reset: "+(mailErr.message||"lỗi không xác định"),"err");}}else toast("Đã cập nhật");closeModal();loadTenants();}else toast(x.data?.message||"Lỗi","err");};
    }

    async function loadContracts(){await loadCaches();const status=$("contractFilter").value;const x=await API.getContracts(status||undefined);contracts=x.data?.data||[];renderContracts();}
    function renderContracts(){
      $("contractsTable").innerHTML=contracts.length?`<table class="data"><thead><tr><th>Khách thuê</th><th>Phòng</th><th>Tiền thuê</th><th>Bắt đầu</th><th>Kết thúc</th><th>Trạng thái</th><th></th></tr></thead><tbody>
      ${contracts.map(c=>`<tr><td>${esc(c.tenant_name||c.tenant_snapshot?.name||tenantName(c.tenant_id))}</td><td>${esc(roomName(c.room_id))}</td><td>${money(c.monthly_rent)}</td><td>${esc(c.start_date||"—")}</td><td>${esc(c.end_date||"—")}</td><td><span class="badge ${c.status==="active"?"badge-active":"badge-ended"}">${esc(c.status)}</span></td><td><button class="btn-sm" data-contract-view="${esc(c.id)}">Chi tiết</button>${c.status==="active"?` <button class="btn-danger" data-contract-end="${esc(c.id)}">Kết thúc</button>`:""}</td></tr>`).join("")}</tbody></table>`:`<div class="p-6 text-center text-slate-500">Không có hợp đồng phù hợp.</div>`;
      $("contractsTable").querySelectorAll("[data-contract-view]").forEach(b=>b.onclick=()=>viewContract(b.dataset.contractView));
      $("contractsTable").querySelectorAll("[data-contract-end]").forEach(b=>b.onclick=()=>endContract(b.dataset.contractEnd));
    }
    async function endContract(id){if(!(await confirmDialog("Kết thúc hợp đồng","Sau khi kết thúc, phòng sẽ trở lại trạng thái trống.","Kết thúc",true)))return;const x=await API.endContract(id);toast(x.data?.message||"Lỗi",x.ok?"ok":"err");if(x.ok)loadContracts();}
    async function viewContract(id){
      const x=await API.getContract(id);if(!x.ok)return toast(x.data?.message||"Lỗi","err");const c=x.data.data;
      modal("Chi tiết hợp đồng",`<div class="space-y-3 text-sm">
        <div><span class="text-slate-500">Khách thuê:</span> <b>${esc(c.tenant?.name||c.tenant_snapshot?.name||tenantName(c.tenant_id))}</b></div>
        <div><span class="text-slate-500">SĐT:</span> ${esc(c.tenant?.phone||c.tenant_snapshot?.phone||"—")} · <span class="text-slate-500">Email:</span> ${esc(c.tenant?.email||c.tenant_snapshot?.email||"—")}</div>
        <div><span class="text-slate-500">Phòng:</span> <b>${esc(c.room?.room_name||roomName(c.room_id))}</b></div>
        <div><span class="text-slate-500">Tiền thuê:</span> ${money(c.monthly_rent)}</div><div><span class="text-slate-500">Tiền cọc:</span> ${money(c.deposit)}</div>
        <div><span class="text-slate-500">Thời hạn:</span> ${esc(c.start_date||"—")} → ${esc(c.end_date||"Không xác định")}</div><div><span class="text-slate-500">Trạng thái:</span> ${esc(c.status)}</div>
        <div class="flex flex-wrap gap-2 pt-2">${tenantById(c.tenant_id)?`<button class="btn-primary" id="contractTenant">Xem khách thuê</button>`:"<span class='text-xs text-slate-500'>Khách thuê hiện không còn là đối tượng đang lưu, thông tin lịch sử vẫn được giữ trên hợp đồng.</span>"}<button class="btn-secondary" id="contractRoom">Xem phòng</button></div></div>`);
      if($("contractTenant"))$("contractTenant").onclick=()=>viewTenant(c.tenant_id);$("contractRoom").onclick=()=>viewRoom(c.room_id);
    }
    async function createContractForm(){
      await loadCaches();
      const available=rooms.filter(r=>!contracts.some(c=>c.room_id===r.room_id&&c.status==="active"));
      modal("Tạo hợp đồng",`<form id="contractForm" class="form-grid">
        <div><label class="label">Khách thuê *</label><select class="input" name="tenant_id" required><option value="">— Chọn khách —</option>${tenants.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")}</select></div>
        <div><label class="label">Phòng *</label><select class="input" name="room_id" required><option value="">— Chọn phòng còn trống —</option>${available.map(r=>`<option value="${esc(r.room_id)}">${esc(r.room_name)}</option>`).join("")}</select></div>
        <div><label class="label">Tiền thuê *</label><input class="input" type="number" name="monthly_rent" required></div><div><label class="label">Tiền cọc</label><input class="input" type="number" name="deposit" value="0"></div>
        <div><label class="label">Ngày bắt đầu *</label><input class="input" type="date" name="start_date" required></div><div><label class="label">Ngày kết thúc</label><input class="input" type="date" name="end_date"></div>
        <div class="full text-xs text-slate-500">Giá điện được lấy từ Cài đặt hệ thống, không cấu hình riêng trong hợp đồng.</div>
        <div class="full flex justify-end gap-2"><button type="button" class="btn-secondary" id="formCancel">Hủy</button><button class="btn-primary">Tạo hợp đồng</button></div></form>`);
      $("formCancel").onclick=closeModal;$("contractForm").onsubmit=async e=>{e.preventDefault();const b=Object.fromEntries(new FormData(e.target));b.monthly_rent=Number(b.monthly_rent);b.deposit=Number(b.deposit)||0;const x=await API.createContract(b);toast(x.data?.message||"Lỗi",x.ok?"ok":"err");if(x.ok){closeModal();loadContracts();}};
    }

    async function loadBilling(){
      await loadCaches(); populateRoomSelect($("billingRoom"),true);
      if(!$("billingPeriod").value)$("billingPeriod").value=periodNow();
      await loadBills(); await loadPayments();
    }
    function populateRoomSelect(sel,all=false){sel.innerHTML=(all?`<option value="">Tất cả phòng</option>`:"")+rooms.map(r=>`<option value="${esc(r.room_id)}">${esc(r.room_name)}</option>`).join("");}
    async function loadBills(){
      const p={};if($("billingRoom").value)p.room_id=$("billingRoom").value;if($("billingPeriod").value)p.period=$("billingPeriod").value;
      const x=await API.getBills(p);bills=x.data?.data||[];
      $("billsTable").innerHTML=bills.length?`<table class="data"><thead><tr><th>Phòng</th><th>Khách thuê</th><th>Kỳ</th><th>Tiền thuê</th><th>Tiền điện</th><th>Tổng</th><th>TT</th><th></th></tr></thead><tbody>
      ${bills.map(b=>`<tr><td>${esc(b.room_name)}</td><td>${esc(b.tenant_name)}</td><td>${esc(b.period)}</td><td>${money(b.monthly_rent)}</td><td>${money(b.electricity_cost)}</td><td><b>${money(b.total_cost)}</b></td><td><span class="badge ${b.status==="cancelled"?"badge-cancelled":""}">${esc(b.status)}</span></td><td class="flex gap-2"><button class="btn-sm" data-bill-view="${esc(b.room_id)}" data-bill-period="${esc(b.period)}">Xem hóa đơn</button>${b.status==="unpaid"?`<button class="btn-sm" data-bill-cancel="${esc(b.room_id)}" data-bill-period="${esc(b.period)}">Hủy hóa đơn</button>`:""}</td></tr>`).join("")}</tbody></table>`:`<div class="p-6 text-center text-slate-500">Chưa có hóa đơn phù hợp.</div>`;
      $("billsTable").querySelectorAll("[data-bill-view]").forEach(b=>b.onclick=()=>viewBill(b.dataset.billView,b.dataset.billPeriod));
      $("billsTable").querySelectorAll("[data-bill-cancel]").forEach(b=>b.onclick=async()=>{
        const ok=await confirmDialog("Hủy hóa đơn","Hóa đơn sẽ chuyển sang trạng thái cancelled và được lưu vào lịch sử. Bạn có chắc chắn?","Hủy hóa đơn",true);
        if(!ok)return;
        const x=await API.cancelBill(b.dataset.billCancel,b.dataset.billPeriod);
        toast(x.data?.message||"Lỗi",x.ok?"ok":"err");
        if(x.ok){await loadBills();await loadAnalytics();}
      });
    }
    async function viewBill(roomId,period){
      const x=await API.getBill(roomId,period);if(!x.ok)return toast(x.data?.message||"Không tìm thấy hóa đơn","err");const b=x.data.data;
      const displayRoom=b.room_name||roomName(b.room_id);
      const displayTenant=b.tenant_name||b.tenant_snapshot?.name||tenantName(b.tenant_id);
      modal(`Hóa đơn ${period}`,`<div class="space-y-3 text-sm"><div><span class="text-slate-500">Phòng:</span> <b>${esc(displayRoom)}</b></div><div><span class="text-slate-500">Khách thuê:</span> ${esc(displayTenant)}</div><div><span class="text-slate-500">Kỳ:</span> ${esc(b.period)}</div><div><span class="text-slate-500">Tiền thuê:</span> ${money(b.monthly_rent)}</div><div><span class="text-slate-500">Điện năng:</span> ${num(b.consumption,3)} kWh × ${money(b.electricity_price)}/kWh</div><div><span class="text-slate-500">Tiền điện:</span> ${money(b.electricity_cost)}</div><div class="text-lg font-semibold">Tổng: ${money(b.total_cost)}</div><div>Trạng thái: <span class="badge ${b.status==="cancelled"?"badge-cancelled":""}">${esc(b.status)}</span></div><div>${b.archived?`<p class="text-xs text-slate-500">Hóa đơn này đã được lưu trong kho lịch sử độc lập với phòng.</p>`:""}</div><div class="flex flex-wrap gap-2 pt-2">${b.tenant_id?`<button class="btn-primary" id="billTenant">Xem khách thuê</button>`:""}${b.archived?`<span class="text-xs text-slate-500 self-center">Bản ghi lịch sử</span>`:`<button class="btn-secondary" id="billRoom">Xem phòng</button>`}${b.contract_id?`<button class="btn-secondary" id="billContract">Xem hợp đồng</button>`:""}</div></div>`);
      if($("billTenant"))$("billTenant").onclick=()=>viewTenant(b.tenant_id);if($("billRoom"))$("billRoom").onclick=()=>viewRoom(b.room_id);if($("billContract"))$("billContract").onclick=()=>viewContract(b.contract_id);
    }
    async function loadPayments(){
      const p={};if($("billingRoom").value)p.room_id=$("billingRoom").value;const x=await API.getPayments(p);const list=x.data?.data||[];
      $("paymentsTable").innerHTML=list.length?`<table class="data"><thead><tr><th>Phòng</th><th>Kỳ</th><th>Số tiền</th><th>PTTT</th><th>Thời gian</th></tr></thead><tbody>${list.map(p=>`<tr><td>${esc(p.room_name||roomName(p.room_id))}</td><td>${esc(p.period)}</td><td>${money(p.amount)}</td><td>${esc(p.payment_method)}</td><td>${time(p.paid_at||p.created_at)}</td></tr>`).join("")}</tbody></table>`:`<div class="p-4 text-slate-500">Chưa có thanh toán.</div>`;
    }
    async function generateBillForm(){
      await loadCaches();const active=contracts.filter(c=>c.status==="active");
      const selectedPeriod=$("billingPeriod").value||periodNow();
      modal("Tạo hóa đơn từ hợp đồng",`<form id="billForm" class="space-y-4">
        <div><label class="label">Chọn hợp đồng</label><select id="billContractSelect" class="input" required><option value="">— Chọn hợp đồng —</option>${active.map(c=>`<option value="${esc(c.id)}">${esc(c.tenant_name||c.tenant_snapshot?.name||tenantName(c.tenant_id))} · ${esc(roomName(c.room_id))}</option>`).join("")}</select></div>
        <div><label class="label">Tháng hóa đơn *</label><input type="month" id="billPeriodSelect" class="input" value="${esc(selectedPeriod)}" required><p class="text-xs text-slate-500 mt-1">Chọn đúng tháng muốn tạo hóa đơn để phục vụ demo và tra cứu lịch sử.</p></div>
        <div id="billPreview" class="card p-4 text-sm text-slate-400">Chọn hợp đồng và tháng để hệ thống tự lấy tiền thuê và tiền điện.</div>
        <div class="flex justify-end gap-2"><button type="button" class="btn-secondary" id="formCancel">Hủy</button><button class="btn-primary">Tạo hóa đơn</button></div></form>`);
      $("formCancel").onclick=closeModal;
      const refreshBillPreview=async()=>{
        const c=active.find(x=>x.id===$("billContractSelect").value);
        const period=$("billPeriodSelect").value;
        if(!c||!period){$("billPreview").textContent="Chọn hợp đồng và tháng để xem thông tin.";return;}
        const x=await API.getCurrentBill(c.room_id,period);
        if(!x.ok){$("billPreview").innerHTML=`<span class="text-red-400">${esc(x.data?.message||"Không tính được hóa đơn")}</span>`;return;}
        const b=x.data.data;
        $("billPreview").innerHTML=`<div class="space-y-2"><div>Khách thuê: <b>${esc(c.tenant_name||c.tenant_snapshot?.name||tenantName(c.tenant_id))}</b></div><div>Phòng: <b>${esc(roomName(c.room_id))}</b></div><div>Tháng: <b>${esc(b.period)}</b></div><div>Tiền thuê: <b>${money(b.monthly_rent)}</b></div><div>Điện: <b>${num(b.consumption,3)} kWh</b> × ${money(b.electricity_price)} = <b>${money(b.electricity_cost)}</b></div><div class="text-base font-semibold">Tổng: ${money(b.total_cost)}</div></div>`;
      };
      $("billContractSelect").onchange=refreshBillPreview;
      $("billPeriodSelect").onchange=refreshBillPreview;
      refreshBillPreview();
      $("billForm").onsubmit=async e=>{e.preventDefault();const c=active.find(x=>x.id===$("billContractSelect").value),period=$("billPeriodSelect").value;if(!c||!period)return toast("Vui lòng chọn hợp đồng và tháng hóa đơn.","err");const x=await API.generateBill(c.room_id,period);toast(x.data?.message||"Lỗi",x.ok?"ok":"err");if(x.ok){$("billingPeriod").value=period;closeModal();loadBills();}};
    }

    function analyticsDateFor(g){
      const d=new Date();
      const localDate=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
      if(g==="day"||g==="week")return localDate;
      if(g==="year")return String(d.getFullYear());
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    }
    function renderAnalyticsCharts(d){
      const labels=d.labels||[];
      if(energyChart)energyChart.destroy();
      if(typeof Chart!=="undefined"){
        energyChart=new Chart($("chartEnergy"),{type:"bar",data:{labels,datasets:[{label:"Điện tiêu thụ (kWh)",data:d.energy||[],borderRadius:5}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true}}}});
        if(window.analyticsRevenueChart)window.analyticsRevenueChart.destroy();
        window.analyticsRevenueChart=new Chart($("chartRevenue"),{type:"line",data:{labels,datasets:[{label:"Doanh thu (₫)",data:d.revenue||[],tension:.25,fill:true}]},options:{responsive:true,maintainAspectRatio:false}});
        if(window.analyticsBillChart)window.analyticsBillChart.destroy();
        window.analyticsBillChart=new Chart($("chartBills"),{type:"bar",data:{labels,datasets:[{label:"Số hóa đơn",data:d.bill_count_series||[]},{label:"Đã thanh toán",data:d.paid_count_series||[]},{label:"Đã hủy",data:d.cancelled_count_series||[]}]},options:{responsive:true,maintainAspectRatio:false}});
      }
    }
    async function loadAnalytics(){
      const g=$("analyticsGranularity").value||"month";
      const date=analyticsDateFor(g);
      const x=await API.getAnalyticsSummary(g,date);
      if(!x.ok){toast(x.data?.message||"Không tải được thống kê","err");return;}
      const d=x.data?.data||{};
      $("analyticsCards").innerHTML=[["Phòng",d.total_rooms],["Điện năng",num(d.total_energy,3)+" kWh"],["Hóa đơn",d.bill_count],["Đã thanh toán",d.paid_bills],["Hủy",d.cancelled_bills],["Còn nợ",money(d.outstanding_total)],["Doanh thu",money(d.revenue_total)]].map(a=>`<div class="kpi-card"><div class="kpi-label">${a[0]}</div><div class="kpi-value">${a[1]??"—"}</div></div>`).join("");
      $("analyticsRangeLabel").textContent=`${new Date(d.start).toLocaleDateString("vi-VN")} → ${new Date(d.end).toLocaleDateString("vi-VN")}`;
      $("analyticsBillHistory").innerHTML=(d.by_room||[]).length?`<table class="data"><thead><tr><th>Phòng</th><th>Điện tiêu thụ</th></tr></thead><tbody>${(d.by_room||[]).map(r=>`<tr><td>${esc(r.room_name)}</td><td><b>${num(r.consumption,3)} kWh</b></td></tr>`).join("")}</tbody></table>`:`<div class="p-4 text-slate-500">Chưa có dữ liệu điện.</div>`;
      renderAnalyticsCharts(d);
    }

    async function loadOccupancy(){
      try{
        const x=await API.getOccupancy();
        if(!x.ok) throw new Error(x.data?.message||"Occupancy API error");
        const d=x.data?.data||{};
        occupancySnapshot=d;
        occupancyLastApiOkAt=Date.now();
        occupancyLastServerDataAt=Math.max(
          ...((d.rooms||d.data||[]).map(r=>normalizeUnixSeconds(r.heartbeat_at ?? r.occupancy_heartbeat_at)||0)),
          0
        );
        renderOccupancySnapshot(d);
      }catch(e){
        console.error("Occupancy refresh failed:",e);
        // Do not overwrite the last snapshot with a stale value. The 5s
        // client timer will turn it UNKNOWN once the server heartbeat expires.
        if(occupancySnapshot) renderOccupancySnapshot(occupancySnapshot);
        else {
          $("occSummary").innerHTML=[
            ["Có người",0],["Trống",0],["Chưa rõ",0]
          ].map(a=>`<div class="stat-chip"><span>${a[0]}</span><b>${a[1]}</b></div>`).join("");
          $("occupancyList").innerHTML=`<div class="text-slate-500">Chưa xác định · Chưa nhận được heartbeat từ module CV.</div>`;
        }
      }
    }


    async function loadAlerts(){const status=$("alertFilter").value;const x=await API.getAlerts(status?{status}:{}),a=x.data?.data||[];const active=a.filter(x=>x.status==="active").length;$("alertStats").innerHTML=[["Hiển thị",a.length],["Active",active],["Đã xử lý",a.length-active]].map(x=>`<div class="stat-chip"><span>${x[0]}</span><b>${x[1]}</b></div>`).join("");$("alertsList").innerHTML=a.length?a.map(v=>`<div class="alert-card ${v.status==="active"?"is-active":"is-resolved"}"><div class="alert-body"><div class="alert-title"><span>${esc(v.type||"Cảnh báo")}</span><span class="badge">${esc(v.status)}</span></div><div class="alert-msg">${esc(v.message||"")}</div><div class="alert-meta">Phòng: ${esc(roomName(v.room_id))} · ${time(v.created_at)}</div><div class="alert-actions"><button class="btn-sm" data-alert-view="${esc(v.id)}">Chi tiết</button>${v.status==="active"?` <button class="btn-sm ok" data-alert-resolve="${esc(v.id)}">Xử lý</button>`:""}</div></div></div>`).join(""):`<div class="text-slate-500">Không có cảnh báo.</div>`;
      $("alertsList").querySelectorAll("[data-alert-view]").forEach(b=>b.onclick=()=>viewAlert(b.dataset.alertView));$("alertsList").querySelectorAll("[data-alert-resolve]").forEach(b=>b.onclick=async()=>{const r=await API.resolveAlert(b.dataset.alertResolve);toast(r.data?.message||"Lỗi",r.ok?"ok":"err");loadAlerts();});
      const h=await API.getControlHistory({limit:30});const list=h.data?.data||[];$("historyList").innerHTML=list.map(v=>`<div class="history-item"><b>${v.action==="ON"||v.switch===true?"BẬT":"NGẮT"}</b> · ${esc(roomName(v.room_id))} · ${time(v.timestamp)}</div>`).join("")||`<div class="text-slate-500">Chưa có lịch sử.</div>`;
    }
    async function viewAlert(id){const x=await API.getAlert(id);if(!x.ok)return;const a=x.data.data;modal("Chi tiết cảnh báo",`<div class="space-y-3 text-sm"><div><span class="text-slate-500">Loại:</span> ${esc(a.type)}</div><div><span class="text-slate-500">Nội dung:</span> ${esc(a.message||"—")}</div><div><span class="text-slate-500">Giá trị:</span> ${a.value!=null?num(a.value,2):"—"}</div><div><span class="text-slate-500">Ngưỡng:</span> ${a.threshold!=null?num(a.threshold,2):"—"}</div><div><span class="text-slate-500">Trạng thái:</span> ${esc(a.status)}</div><div class="flex gap-2"><button class="btn-primary" id="alertRoom">Xem phòng</button>${a.tenant?`<button class="btn-secondary" id="alertTenant">Xem khách thuê</button>`:""}</div></div>`);$("alertRoom").onclick=()=>viewRoom(a.room_id);if(a.tenant)$("alertTenant").onclick=()=>viewTenant(a.tenant.id);}

    async function loadNotificationLogs(){
      const x=await API.getNotificationLogs(50);
      if(!x.ok){
        $("notifLogs").innerHTML=`<div class="text-slate-500">Không thể tải lịch sử thông báo.</div>`;
        return;
      }
      const logs=x.data?.data||[];
      $("notifLogs").innerHTML=logs.length?logs.map(v=>{
        const target=v.data?.target||"—";
        const scope=v.data?.scope||((target==="all_tenants")?"global":(target==="tenant"||target==="room_tenant")?"private":"system");
        const status=v.status||((Number(v.sent_count||0)>0)?"sent":"no_tokens");
        const statusText={sent:"Đã gửi",failed:"Lỗi gửi",no_tokens:"Chưa có thiết bị nhận"}[status]||status;
        const targetText={all_tenants:"Tất cả khách thuê",tenant:"Một khách thuê",room_tenant:"Khách thuê phòng",landlords:"Chủ trọ"}[target]||target;
        const scopeText={global:"Toàn người dùng",private:"Riêng tư",system:"Hệ thống"}[scope]||scope;
        const roomText=v.data?.room_name ? ` · Phòng: ${esc(v.data.room_name)}` : "";
        const sent=`${Number(v.sent_count||0)}/${Number(v.token_count||0)}`;
        return `<div class="history-item border-b border-slate-800 py-3 last:border-0"><div class="flex justify-between gap-3"><b>${esc(v.title||"Thông báo")}</b><span class="text-xs text-slate-500">${time(v.created_at)}</span></div><div class="text-sm mt-1">${esc(v.body||"")}</div><div class="text-xs text-slate-500 mt-1">Phạm vi: ${esc(scopeText)} · Đối tượng: ${esc(targetText)}${roomText} · ${esc(statusText)} · FCM: ${esc(sent)}</div></div>`;
      }).join(""):`<div class="text-slate-500">Chưa có lịch sử thông báo.</div>`;
    }

    async function loadNotifications(){
      const t=await API.getTenants();
      tenants=t.data?.data||[];
      $("notifTenantId").innerHTML=tenants.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("");
      await loadNotificationLogs();
    }
    $("notifTarget").onchange=()=> $("notifTenantWrap").classList.toggle("hidden",$("notifTarget").value!=="tenant");
    $("btnSendNotif").onclick=async()=>{
      const btn=$("btnSendNotif");
      const title=$("notifTitle").value.trim(),body=$("notifBody").value.trim(),target=$("notifTarget").value;
      if(!title||!body)return toast("Nhập tiêu đề và nội dung","err");
      const p={title,body,target};
      if(target==="tenant")p.tenant_id=$("notifTenantId").value;
      btn.disabled=true;
      try{
        const x=await API.sendNotification(p);
        toast(x.data?.message||x.data?.message||"Lỗi",x.ok?"ok":"err");
        // Reload from Firestore after every send so the history reflects the
        // actual persisted record, including sends made with zero active tokens.
        await loadNotificationLogs();
        if(x.ok){$("notifTitle").value="";$("notifBody").value="";}
      }finally{btn.disabled=false;}
    };

    async function loadSettings(){const x=await API.getSettings();const s=x.data?.data||{};$("settingPrice").value=s.electricity_price??3500;$("settingHighPower").value=s.alert_high_power??3000;$("settingHighCurrent").value=s.alert_high_current??20;$("settingAutoCut").checked=!!s.auto_cut_power;}
    $("btnSaveSettings").onclick=async()=>{const x=await API.updateSettings({electricity_price:Number($("settingPrice").value),alert_high_power:Number($("settingHighPower").value),alert_high_current:Number($("settingHighCurrent").value),auto_cut_power:$("settingAutoCut").checked});toast(x.data?.message||"Lỗi",x.ok?"ok":"err");};

    function showPage(name){
      document.querySelectorAll(".page-section").forEach(s=>s.classList.add("hidden"));$("page-"+name).classList.remove("hidden");
      document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===name));$("pageTitle").textContent={overview:"Tổng quan",rooms:"Phòng trọ",tenants:"Khách thuê",contracts:"Hợp đồng",billing:"Hóa đơn & Thanh toán",analytics:"Thống kê",occupancy:"Occupancy / CV",alerts:"Cảnh báo",notifications:"Thông báo",settings:"Cài đặt"}[name];
      ({overview:loadOverview,rooms:loadRooms,tenants:loadTenants,contracts:loadContracts,billing:loadBilling,analytics:loadAnalytics,occupancy:loadOccupancy,alerts:loadAlerts,notifications:loadNotifications,settings:loadSettings}[name]||(()=>{}))();
    }
    document.querySelectorAll(".nav-item").forEach(b=>b.onclick=()=>showPage(b.dataset.page));
    $("refreshBtn").onclick=()=>showPage(document.querySelector(".nav-item.active")?.dataset.page||"overview");
    $("btnBatchOn").onclick=()=>batchPower(true);$("btnBatchOff").onclick=()=>batchPower(false);$("btnAddRoom").onclick=()=>roomForm(null);$("btnAddTenant").onclick=()=>tenantForm(null);$("btnAddContract").onclick=createContractForm;
    $("contractFilter").onchange=loadContracts;$("btnFilterBills").onclick=()=>{loadBills();loadPayments();};$("btnGenerateBill").onclick=generateBillForm;$("btnLoadAnalytics").onclick=loadAnalytics;$("analyticsGranularity").onchange=loadAnalytics;$("btnReloadAlerts").onclick=loadAlerts;$("alertFilter").onchange=loadAlerts;

    $("userLabel").textContent=user.displayName||user.email||"Admin";$("logoutBtn").onclick=()=>auth.signOut().then(()=>location.href="/login");

    // Poll occupancy independently from the manual refresh button. The local
    // expiry timer above still guarantees UNKNOWN if these requests fail.
    setInterval(()=>{
      const active=document.querySelector(".nav-item.active")?.dataset.page;
      if(active==="occupancy") loadOccupancy();
      else if(active==="overview") loadOverview();
    },30000);

    showPage("overview");
  });
})();
