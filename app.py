import uuid

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import (
    add_log_entry,
    create_timestamp,
    find_entry,
    get_log,
    update_status,
)
from detector import analyze_text


app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "Provenance Guard",
        "status": "running",
        "endpoints": [
            "POST /submit",
            "POST /appeal",
            "GET /log",
        ],
    })


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request body must be JSON."
        }), 400

    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not isinstance(text, str):
        return jsonify({
            "error": "The 'text' field is required."
        }), 400

    if not creator_id:
        return jsonify({
            "error": "The 'creator_id' field is required."
        }), 400

    text = text.strip()

    if len(text) < 10:
        return jsonify({
            "error": "Text must contain at least 10 characters."
        }), 400

    content_id = str(uuid.uuid4())

    try:
        result = analyze_text(text)
    except Exception as e:
        return jsonify({
            "error": f"Detection failed: {str(e)}"
        }), 500

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": create_timestamp(),
        "attribution": result["attribution"],
        "confidence": result["confidence"],
        "llm_score": result["llm_score"],
        "stylometric_score": result["stylometric_score"],
        "status": "classified",
    }

    add_log_entry(entry)

    return jsonify({
        "content_id": content_id,
        "attribution": result["attribution"],
        "confidence": result["confidence"],
        "label": result["label"],
    })


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request body must be JSON."
        }), 400

    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id:
        return jsonify({
            "error": "The 'content_id' field is required."
        }), 400

    if not creator_reasoning or not isinstance(creator_reasoning, str):
        return jsonify({
            "error": "The 'creator_reasoning' field is required."
        }), 400

    original = find_entry(content_id)

    if original is None:
        return jsonify({
            "error": "No classification found for that content_id."
        }), 404

    update_status(
        content_id,
        "under_review",
        creator_reasoning,
    )

    appeal_entry = {
        "content_id": content_id,
        "creator_id": original.get("creator_id"),
        "timestamp": create_timestamp(),
        "event": "appeal",
        "status": "under_review",
        "appeal_reasoning": creator_reasoning,
        "original_attribution": original.get("attribution"),
        "original_confidence": original.get("confidence"),
        "llm_score": original.get("llm_score"),
        "stylometric_score": original.get("stylometric_score"),
    }

    add_log_entry(appeal_entry)

    return jsonify({
        "message": "Appeal received.",
        "content_id": content_id,
        "status": "under_review",
    })


@app.route("/log", methods=["GET"])
def log():
    return jsonify({
        "entries": get_log()
    })


@app.errorhandler(429)
def rate_limit_error(error):
    return jsonify({
        "error": "Rate limit exceeded. Please try again later."
    }), 429


if __name__ == "__main__":
    app.run(debug=True, port=5000)