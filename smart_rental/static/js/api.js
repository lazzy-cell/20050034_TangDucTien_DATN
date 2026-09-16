const API = {
  base: "",

  // =========================================================
  // FIREBASE AUTH TOKEN
  // =========================================================

  async getToken(forceRefresh = false) {
    const user = firebaseAuth.currentUser;

    if (!user) {
      return "";
    }

    try {
      return await user.getIdToken(forceRefresh);
    } catch (error) {
      console.error("Failed to get Firebase ID token:", error);
      return "";
    }
  },


  // =========================================================
  // COMMON REQUEST
  // =========================================================

  async request(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };

    const user = firebaseAuth.currentUser;

    // Nếu đã đăng nhập Firebase thì lấy Firebase ID Token
    // và gửi lên Flask backend.
    if (user) {
      try {
        const token = await user.getIdToken();

        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }
      } catch (error) {
        console.error("Failed to get Firebase ID token:", error);
      }
    }

    let res;

    try {
      res = await fetch(this.base + path, {
        ...options,
        headers,
        cache: "no-store"
      });
    } catch (error) {
      console.error("API request failed:", error);

      return {
        ok: false,
        status: 0,
        data: {
          success: false,
          message: "Không thể kết nối tới server."
        }
      };
    }

    let data = null;

    try {
      data = await res.json();
    } catch {
      data = {
        success: false,
        message: "Invalid JSON response from server."
      };
    }

    // =======================================================
    // FIREBASE TOKEN EXPIRED / INVALID
    // =======================================================

    if (res.status === 401) {
      try {
        await firebaseAuth.signOut();
      } catch (error) {
        console.error("Firebase signOut failed:", error);
      }

      if (!window.location.pathname.includes("/login")) {
        window.location.href = "/login";
      }
    }

    return {
      ok: res.ok,
      status: res.status,
      data
    };
  },


  // =========================================================
  // AUTH
  // =========================================================

  async me() {
    return this.request("/api/auth/me");
  },


  async logout() {
    try {
      await firebaseAuth.signOut();
    } catch (error) {
      console.error("Logout failed:", error);
    }

    window.location.href = "/login";
  },


  // =========================================================
  // DASHBOARD
  // =========================================================

  dashboardOverview() {
    return this.request("/api/dashboard/overview");
  },


  // =========================================================
  // ROOMS
  // =========================================================

  getRooms() {
    return this.request("/api/rooms");
  },

  getRoom(id) {
    return this.request(
      `/api/rooms/${encodeURIComponent(id)}`
    );
  },


  createRoom(body) {
    return this.request("/api/rooms", {
      method: "POST",
      body: JSON.stringify(body)
    });
  },


  updateRoom(id, body) {
    return this.request(
      `/api/rooms/${encodeURIComponent(id)}`,
      {
        method: "PUT",
        body: JSON.stringify(body)
      }
    );
  },


  deleteRoom(id) {
    return this.request(
      `/api/rooms/${encodeURIComponent(id)}`,
      {
        method: "DELETE"
      }
    );
  },


  getRoomEnergy(id) {
    return this.request(
      `/api/energy/${encodeURIComponent(id)}/realtime`
    );
  },


  setPower(id, switchOn, reason) {
    return this.request(
      `/api/rooms/${encodeURIComponent(id)}/power`,
      {
        method: "POST",

        body: JSON.stringify({
          switch: !!switchOn,

          reason:
            reason ||
            (
              switchOn
                ? "Bật điện từ Dashboard"
                : "Ngắt điện từ Dashboard"
            )
        })
      }
    );
  },


  setBatchPower(roomIds, switchOn, reason) {
    return this.request(
      "/api/rooms/power/batch",
      {
        method: "POST",

        body: JSON.stringify({
          room_ids: roomIds,

          switch: !!switchOn,

          reason:
            reason ||
            (
              switchOn
                ? "Bật điện hàng loạt từ Dashboard"
                : "Ngắt điện hàng loạt từ Dashboard"
            )
        })
      }
    );
  },


  assignTenantToRoom(roomId, tenantId) {
    return this.request(
      `/api/rooms/${encodeURIComponent(roomId)}/assign-tenant`,
      {
        method: "POST",

        body: JSON.stringify({
          tenant_id: tenantId || null
        })
      }
    );
  },


  // =========================================================
  // TENANTS
  // =========================================================

  getTenants() {
    return this.request("/api/tenants");
  },

  getTenant(id) {
    return this.request(`/api/tenants/${encodeURIComponent(id)}`);
  },


  createTenant(body) {
    return this.request(
      "/api/tenants",
      {
        method: "POST",
        body: JSON.stringify(body)
      }
    );
  },


  updateTenant(id, body) {
    return this.request(
      `/api/tenants/${encodeURIComponent(id)}`,
      {
        method: "PUT",
        body: JSON.stringify(body)
      }
    );
  },


  resetTenantPassword(id) {
    return this.request(`/api/tenants/${encodeURIComponent(id)}/reset-password`, { method: "POST" });
  },

  deleteTenant(id) {
    return this.request(
      `/api/tenants/${encodeURIComponent(id)}`,
      {
        method: "DELETE"
      }
    );
  },


  // =========================================================
  // TENANT CURRENT USER
  // =========================================================

  getTenantMe() {
    return this.request("/api/tenant/me");
  },


  // =========================================================
  // CONTRACTS
  // =========================================================

  getContracts(status) {
    const q = status
      ? `?status=${encodeURIComponent(status)}`
      : "";

    return this.request(
      "/api/contracts" + q
    );
  },


  createContract(body) {
    return this.request(
      "/api/contracts",
      {
        method: "POST",
        body: JSON.stringify(body)
      }
    );
  },

  getContract(id) {
    return this.request(
      `/api/contracts/${encodeURIComponent(id)}`
    );
  },


  endContract(id) {
    return this.request(
      `/api/contracts/${encodeURIComponent(id)}/end`,
      {
        method: "POST"
      }
    );
  },


  cancelContract(id) {
    return this.request(
      `/api/contracts/${encodeURIComponent(id)}/cancel`,
      {
        method: "POST"
      }
    );
  },


  // =========================================================
  // BILLING
  // =========================================================

  getCurrentBill(roomId, period) {
    const q = period
      ? `?period=${encodeURIComponent(period)}`
      : "";

    return this.request(
      `/api/billing/room/${encodeURIComponent(roomId)}/current` + q
    );
  },


  generateBill(roomId, period) {
    return this.request(
      `/api/billing/room/${encodeURIComponent(roomId)}/generate`,
      {
        method: "POST",

        body: JSON.stringify({
          period
        })
      }
    );
  },


  // =========================================================
  // PAYMENTS
  // =========================================================

  getPayments(params = {}) {
    const q = new URLSearchParams(params).toString();

    return this.request(
      "/api/payments" +
      (q ? `?${q}` : "")
    );
  },


  createPayment(body) {
    return this.request(
      "/api/payments",
      {
        method: "POST",
        body: JSON.stringify(body)
      }
    );
  },


  getBills(params = {}) {
    const q = new URLSearchParams(params).toString();
    return this.request("/api/billing" + (q ? `?${q}` : ""));
  },

  getBill(roomId, period) {
    return this.request(`/api/billing/room/${encodeURIComponent(roomId)}/${encodeURIComponent(period)}`);
  },

  cancelBill(roomId, period) {
    return this.request(
      `/api/billing/room/${encodeURIComponent(roomId)}/${encodeURIComponent(period)}/cancel`,
      { method: "POST" }
    );
  },

  // =========================================================
  // ALERTS
  // =========================================================

  getAlerts(params = {}) {
    const q = new URLSearchParams(params).toString();

    return this.request(
      "/api/alerts" +
      (q ? `?${q}` : "")
    );
  },


  getAlert(id) {
    return this.request(`/api/alerts/${encodeURIComponent(id)}`);
  },

  resolveAlert(id) {
    return this.request(
      `/api/alerts/${encodeURIComponent(id)}/resolve`,
      {
        method: "PATCH"
      }
    );
  },


  // =========================================================
  // CONTROL HISTORY
  // =========================================================

  getControlHistory(params = {}) {
    const q = new URLSearchParams(params).toString();

    return this.request(
      "/api/control-history" +
      (q ? `?${q}` : "")
    );
  },


  // =========================================================
  // OCCUPANCY
  // =========================================================

  getOccupancy() {
    return this.request("/api/occupancy");
  },


  getRoomOccupancy(id) {
    return this.request(
      `/api/occupancy/${encodeURIComponent(id)}`
    );
  },


  getOccupancyHistory(id, limit = 50) {
    return this.request(
      `/api/occupancy/${encodeURIComponent(id)}/history?limit=${encodeURIComponent(limit)}`
    );
  },


  // =========================================================
  // ANALYTICS
  // =========================================================

  getAnalyticsToday(id) {
    return this.request(
      `/api/analytics/room/${encodeURIComponent(id)}/today`
    );
  },


  getAnalyticsOverview(period) {
    return this.request(`/api/analytics/overview?period=${encodeURIComponent(period)}`);
  },

  getAnalyticsSummary(granularity, date) {
    return this.request(`/api/analytics/summary?granularity=${encodeURIComponent(granularity)}&date=${encodeURIComponent(date)}`);
  },

  getAnalyticsMonth(id) {
    return this.request(
      `/api/analytics/room/${encodeURIComponent(id)}/month`
    );
  },


  // =========================================================
  // SETTINGS
  // =========================================================

  getSettings() {
    return this.request("/api/settings");
  },


  updateSettings(body) {
    return this.request(
      "/api/settings",
      {
        method: "PUT",
        body: JSON.stringify(body)
      }
    );
  },


  // =========================================================
  // PASSWORD
  // =========================================================
  //
  // Firebase Auth quản lý password.
  //
  // Không dùng API cũ:
  // POST /api/auth/change-password
  //
  // Nếu sau này cần đổi password, dùng:
  // firebaseAuth.currentUser.updatePassword(...)
  //
  // =========================================================


  // =========================================================
  // NOTIFICATIONS
  // =========================================================

  testPush(body = {}) {
    return this.request(
      "/api/notifications/test",
      {
        method: "POST",
        body: JSON.stringify(body)
      }
    );
  },


  getNotificationTokens() {
    return this.request(
      "/api/notifications/tokens"
    );
  },


  sendNotification(body) {
    return this.request(
      "/api/notifications/send",
      {
        method: "POST",
        body: JSON.stringify(body)
      }
    );
  },


  getNotificationLogs(limit = 30) {
    return this.request(
      `/api/notifications/logs?limit=${encodeURIComponent(limit)}`
    );
  }
};