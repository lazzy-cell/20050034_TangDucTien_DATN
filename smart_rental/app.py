from flask import Flask, render_template, redirect, url_for
from flask_cors import CORS

from firebase_config import initialize_firebase
from services.scheduler_service import start_scheduler

from routes.rooms import rooms_bp
from routes.energy import energy_bp
from routes.analytics import analytics_bp
from routes.billing import billing_bp
from routes.daily_energy import daily_energy_bp
from routes.dashboard import dashboard_bp
from routes.alerts import alerts_bp
from routes.tenants import tenants_bp
from routes.contracts import contracts_bp
from routes.payments import payments_bp
from routes.auth import auth_bp
from routes.power import power_bp
from routes.occupancy import occupancy_bp
from routes.settings import settings_bp
from routes.notifications import notifications_bp
from routes.tenant import tenant_bp

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Firebase
initialize_firebase()

# Blueprints (API)
app.register_blueprint(auth_bp)
app.register_blueprint(rooms_bp)
app.register_blueprint(energy_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(daily_energy_bp)
app.register_blueprint(billing_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(tenants_bp)
app.register_blueprint(contracts_bp)
app.register_blueprint(payments_bp)
app.register_blueprint(power_bp)
app.register_blueprint(occupancy_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(tenant_bp)


# ---------- Web pages ----------

@app.route("/")
def home():
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard_page():
    return render_template("index.html")


@app.route("/tenant")
def tenant_page():
    return render_template("tenant.html")


@app.route("/api")
def api_info():
    return {
        "success": True,
        "message": "Smart Rental API",
        "version": "1.9.1",
        "web": {
            "login": "/login",
            "dashboard": "/dashboard",
            "tenant": "/tenant",
        },
        "endpoints": {
            "auth": "/api/auth/login",
            "rooms": "/api/rooms",
            "power": "/api/rooms/<room_id>/power",
            "energy": "/api/energy/<room_id>/realtime",
            "dashboard": "/api/dashboard/overview",
            "alerts": "/api/alerts",
            "control_history": "/api/control-history",
            "occupancy": "/api/occupancy",
            "occupancy_room": "/api/occupancy/<room_id>",
            "monitoring_occupancy": "/api/monitoring/occupancy",
            "monitoring_occupancy_room": "/api/monitoring/occupancy/<room_id>",
            "analytics_today": "/api/analytics/room/<room_id>/today",
            "analytics_month": "/api/analytics/room/<room_id>/month",
            "analytics_summary": "/api/analytics/summary?granularity=day|week|month|year&date=...",
            "settings": "/api/settings",
            "tenant_login": "/api/auth/tenant/login",
            "tenant_profile": "/api/tenant/me",
            "tenant_room": "/api/tenant/room",
            "tenant_power": "/api/tenant/room/power",
            "tenant_bills": "/api/tenant/bills",
            "tenant_contracts": "/api/tenant/contracts",
            "tenant_payments": "/api/tenant/payments",
            "tenant_power_history": "/api/tenant/power-history",
            "tenant_energy_history": "/api/tenant/energy-history",
            "tenant_notifications": "/api/tenant/notifications",
            "notifications_register": "/api/notifications/register",
            "notifications_test": "/api/notifications/test",
            "notifications_send": "/api/notifications/send",
            "notifications_logs": "/api/notifications/logs",
            "billing": "/api/billing",
            "billing_cancel": "/api/billing/room/<room_id>/<period>/cancel",
            "power_batch": "/api/rooms/power/batch",
            "assign_tenant": "/api/rooms/<room_id>/assign-tenant",
        },
    }


if __name__ == "__main__":
    start_scheduler()
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,
    )
