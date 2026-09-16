(() => {
  const $ = (id) => document.getElementById(id);
  let currentUser = null;

  const money = (v) => `${Number(v || 0).toLocaleString("vi-VN")} ₫`;
  const date = (v) => v ? new Date(v).toLocaleString("vi-VN") : "—";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[c]));

  function showMessage(text, error = false) {
    const el = $("message");
    el.textContent = text;
    el.className = `rounded-xl px-4 py-3 text-sm ${error ? "bg-red-500/10 border border-red-500/30 text-red-300" : "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"}`;
    el.classList.remove("hidden");
    setTimeout(() => el.classList.add("hidden"), 4000);
  }

  async function api(path, options = {}) {
    if (!currentUser) throw new Error("Chưa đăng nhập");
    const token = await currentUser.getIdToken();
    const res = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}`, ...(options.headers || {}) }
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || payload.success === false) throw new Error(payload.message || `HTTP ${res.status}`);
    return payload;
  }

  async function loadProfile() {
    const r = await api("/api/tenant/me");
    const t = r.data;
    $("userEmail").textContent = t.email || currentUser.email || "";
    $("profileName").value = t.name || "";
    $("profileEmail").value = t.email || "";
    $("profilePhone").value = t.phone || "";
    $("profileAddress").value = t.address || "";
    $("profileIdentity").value = t.identity_number || "";
    if (t.must_change_password) $("passwordSetup").classList.remove("hidden");
  }

  async function loadRoom() {
    try {
      const r = await api("/api/tenant/room");
      const d = r.data, room = d.room, rt = d.realtime;
      $("roomName").textContent = room.room_name || room.id;
      $("switchState").textContent = rt.switch ? "Đang bật" : "Đang tắt";
      $("powerState").textContent = `${Number(rt.power || 0).toFixed(1)} W`;
      $("roomMeta").textContent = `${room.status || "—"} · ${rt.online ? "Thiết bị online" : "Thiết bị offline"}`;
      $("roomDetails").innerHTML = [
        ["Phòng", room.room_name || room.id],
        ["Trạng thái", room.status || "—"],
        ["Công suất hiện tại", `${Number(rt.power || 0).toFixed(1)} W`],
        ["Điện áp", rt.voltage != null ? `${Number(rt.voltage).toFixed(1)} V` : "—"],
        ["Dòng điện", rt.current != null ? `${Number(rt.current).toFixed(2)} A` : "—"],
        ["Cập nhật", date(rt.updated_at)]
      ].map(x => `<div class="bg-slate-800/60 rounded-xl p-4"><span class="text-slate-400">${esc(x[0])}</span><div class="font-medium mt-1">${esc(x[1])}</div></div>`).join("");
    } catch (e) {
      $("roomMeta").textContent = e.message;
      showMessage(e.message, true);
    }
  }

  async function setPower(value) {
    if (!confirm(value ? "Bạn muốn bật điện phòng của mình?" : "Bạn muốn tắt điện phòng của mình?")) return;
    try {
      await api("/api/tenant/room/power", { method: "POST", body: JSON.stringify({ switch: value, reason: value ? "Tenant bật điện" : "Tenant tắt điện" }) });
      showMessage(value ? "Đã bật điện." : "Đã tắt điện.");
      await loadRoom();
      await loadHistory();
    } catch (e) { showMessage(e.message, true); }
  }

  async function loadBills() {
    try {
      const r = await api("/api/tenant/bills");
      const rows = r.data || [];
      $("billState").textContent = rows.length ? `${money(rows[0].total_cost)} · ${rows[0].status}` : "Chưa có";
      $("billsTable").innerHTML = rows.length ? rows.map(b => `<tr><td>${esc(b.period)}</td><td>${money(b.monthly_rent)}</td><td>${money(b.electricity_cost)}</td><td>${money(b.total_cost)}</td><td>${esc(b.status)}</td></tr>`).join("") : `<tr><td colspan="5">Chưa có hóa đơn.</td></tr>`;
    } catch (e) { showMessage(e.message, true); }
  }

  async function loadContracts() {
    try {
      const r = await api("/api/tenant/contracts");
      $("contractsTable").innerHTML = (r.data || []).map(c => `<tr><td>${esc(c.room?.room_name || c.room_id)}</td><td>${esc(c.start_date)}</td><td>${esc(c.end_date || "Không xác định")}</td><td>${money(c.monthly_rent)}</td><td>${esc(c.status)}</td></tr>`).join("") || `<tr><td colspan="5">Chưa có hợp đồng.</td></tr>`;
    } catch (e) { showMessage(e.message, true); }
  }

  async function loadHistory() {
    try {
      const [p, pay, e] = await Promise.all([
        api("/api/tenant/power-history?limit=100"),
        api("/api/tenant/payments"),
        api("/api/tenant/energy-history?limit=100")
      ]);
      $("powerHistoryTable").innerHTML = (p.data || []).map(x => `<tr><td>${date(x.timestamp)}</td><td>${x.switch ? "BẬT" : "TẮT"}</td><td>${esc(x.triggered_by || "—")}</td><td>${esc(x.reason || "—")}</td></tr>`).join("") || `<tr><td colspan="4">Chưa có dữ liệu.</td></tr>`;
      $("paymentsTable").innerHTML = (pay.data || []).map(x => `<tr><td>${date(x.paid_at || x.created_at)}</td><td>${esc(x.period)}</td><td>${money(x.amount)}</td><td>${esc(x.payment_method)}</td><td>${esc(x.status)}</td></tr>`).join("") || `<tr><td colspan="5">Chưa có dữ liệu.</td></tr>`;
      $("energyHistoryTable").innerHTML = (e.data || []).map(x => `<tr><td>${date(x.timestamp)}</td><td>${x.voltage ?? "—"} V</td><td>${x.current ?? "—"} A</td><td>${x.power ?? "—"} W</td><td>${x.switch ? "ON" : "OFF"}</td></tr>`).join("") || `<tr><td colspan="5">Chưa có dữ liệu.</td></tr>`;
    } catch (e) { showMessage(e.message, true); }
  }

  async function loadNotifications() {
    try {
      const r = await api("/api/tenant/notifications?limit=50");
      $("notificationsList").innerHTML = (r.data || []).map(n => `<article class="rounded-xl border border-slate-800 bg-slate-800/50 p-4"><div class="flex justify-between gap-3"><h3 class="font-semibold">${esc(n.title)}</h3><time class="text-xs text-slate-500">${date(n.created_at)}</time></div><p class="text-sm text-slate-300 mt-2">${esc(n.body)}</p></article>`).join("") || `<p class="text-sm text-slate-400">Chưa có thông báo.</p>`;
    } catch (e) { showMessage(e.message, true); }
  }

  async function bootstrap(user) {
    currentUser = user;
    try {
      const token = await user.getIdTokenResult(true);
      if (token.claims.role !== "tenant") {
        window.location.href = token.claims.role === "landlord" ? "/dashboard" : "/login";
        return;
      }
      await Promise.all([loadProfile(), loadRoom(), loadBills(), loadContracts(), loadHistory(), loadNotifications()]);
    } catch (e) { showMessage(e.message, true); }
  }

  $("logoutBtn").onclick = () => firebaseAuth.signOut().then(() => location.href = "/login");
  $("turnOnBtn").onclick = () => setPower(true);
  $("turnOffBtn").onclick = () => setPower(false);
  $("refreshRoomBtn").onclick = loadRoom;
  $("refreshNotificationsBtn").onclick = loadNotifications;

  document.querySelectorAll(".tab").forEach(btn => btn.onclick = () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(x => x.classList.add("hidden"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });

  $("profileForm").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const r = await api("/api/tenant/me", { method: "PUT", body: JSON.stringify({
        name: $("profileName").value.trim(),
        phone: $("profilePhone").value.trim(),
        address: $("profileAddress").value.trim()
      })});
      $("profileName").value = r.data.name || "";
      showMessage("Đã cập nhật thông tin.");
    } catch (e) { showMessage(e.message, true); }
  };

  $("passwordForm").onsubmit = async (e) => {
    e.preventDefault();
    const p = $("newPassword").value, c = $("confirmPassword").value;
    if (p.length < 6 || p !== c) return showMessage("Mật khẩu phải từ 6 ký tự và hai ô phải giống nhau.", true);
    try {
      await currentUser.updatePassword(p);
      await api("/api/tenant/me/password-setup-complete", { method: "POST", body: "{}" });
      $("passwordSetup").classList.add("hidden");
      $("newPassword").value = $("confirmPassword").value = "";
      showMessage("Đổi mật khẩu thành công.");
    } catch (e) { showMessage(e.message || "Không thể đổi mật khẩu.", true); }
  };

  firebaseAuth.onAuthStateChanged(user => {
    if (!user) { location.href = "/login"; return; }
    bootstrap(user);
  });
})();
