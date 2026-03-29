from flask import Flask, request, jsonify
import json, os, time
from datetime import datetime, timedelta

app = Flask(__name__)

RATE_FILE = "rate_limits.json"
if not os.path.exists(RATE_FILE):
    json.dump({}, open(RATE_FILE, "w"))

def load_rates():
    return json.load(open(RATE_FILE))

def save_rates(data):
    json.dump(data, open(RATE_FILE, "w"))

@app.route("/trigger-audit", methods=["POST"])
def trigger():
    ip = request.remote_addr
    email = request.form.get("email", "").lower()
    client_url = request.form.get("client_url", "")
    data = load_rates()

    now = datetime.utcnow()
    key_ip = f"ip:{ip}"
    key_email = f"email:{email}"

    # 2 audits per IP per 24h
    if key_ip in data and datetime.fromisoformat(data[key_ip]) > now - timedelta(hours=24):
        return jsonify({"error": "Rate limit reached (2 audits/IP/day)"}), 429

    # 1 audit per email per 7 days
    if key_email in data and datetime.fromisoformat(data[key_email]) > now - timedelta(days=7):
        return jsonify({"error": "Rate limit reached (1 audit/email/week)"}), 429

    # Record limits
    data[key_ip] = now.isoformat()
    if email:
        data[key_email] = now.isoformat()
    save_rates(data)

    # Forward to n8n (or directly run audit if you prefer)
    # For now we just echo success — we'll hook n8n next
    return jsonify({"status": "success", "message": "Audit queued — report in your inbox in ~15 min"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5679, debug=False)