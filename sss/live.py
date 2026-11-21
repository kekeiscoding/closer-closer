import json
from urllib.parse import urlsplit

from flask import abort, g, request, session
from flask_sock import Sock
from simple_websocket import ConnectionClosed

from .db import guest_payment_status, paid_order_ids
from .students import student


def stream_status(socket, snapshot, *, complete=lambda _status: False):
    origin = urlsplit(request.headers.get("Origin", ""))
    if origin.netloc != request.host or origin.scheme not in {"http", "https"}:
        socket.close(reason=1008)
        return
    previous = None
    try:
        while socket.connected:
            status = snapshot()
            if status is None:
                socket.close(reason=1008)
                return
            if status != previous:
                socket.send(json.dumps(status))
                if complete(status):
                    return
                previous = status
            socket.receive(timeout=1)
    except ConnectionClosed:
        return


def register_payment_updates(app):
    sock = Sock(app)

    def account_status():
        if g.user is None:
            return None
        student_id = g.user["id"] if g.user["role"] == "student" else None
        if student_id:
            account = student(student_id)
            if not account or not account["active"] or account["revision"] != session.get("revision"):
                return None
        return {"paid_orders": paid_order_ids(student_id)}

    @app.get("/payments/status")
    def payments_status():
        status = account_status()
        if status is None:
            abort(401)
        return status

    @sock.route("/payments/status/live")
    def payments_live(socket):
        stream_status(socket, account_status)

    @app.get("/checkout/<token>/status")
    def checkout_status(token):
        status = guest_payment_status(token)
        if status is None:
            abort(404)
        return status

    @sock.route("/checkout/<token>/status/live")
    def checkout_live(socket, token):
        stream_status(socket, lambda: guest_payment_status(token), complete=lambda status: status["paid"])
