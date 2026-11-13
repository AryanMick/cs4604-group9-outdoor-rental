"""Customer-facing pages: choose a business, browse equipment, fill a cart, and pay."""
from __future__ import annotations

from functools import wraps
from pathlib import Path
import secrets

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for,
)
import pymysql

import customer_service
from customer_service import BookingError

bp = Blueprint("customer", __name__)


def _csrf_ok() -> bool:
    token = session.get("csrf_token")
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    return bool(token) and secrets.compare_digest(token, sent)


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.path == "/cart/add"


def customer_view(view):
    """Require a customer session and turn database failures into an error page or JSON error."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if (session.get("role") != "customer"
                or not isinstance(session.get("customer_id"), int)
                or not isinstance(session.get("cart_id"), int)):
            if _wants_json():
                return jsonify(ok=False, error="Log in as a customer first."), 401
            return redirect(url_for("login"))
        try:
            return view(*args, **kwargs)
        except (RuntimeError, pymysql.MySQLError) as exc:
            current_app.logger.exception("Customer page database failure")
            if _wants_json():
                return jsonify(ok=False, error=str(exc)), 503
            return render_template("customer/error.html", message=str(exc)), 503
    return wrapper


@bp.app_template_filter("fmt_dt")
def format_datetime(value) -> str:
    return f"{value:%b} {value.day}, {value.year} {value.hour % 12 or 12}:{value:%M} {value:%p}"


@bp.app_template_filter("money")
def format_money(value) -> str:
    return f"${value:,.2f}"


@bp.app_template_filter("rental_image")
def rental_image(value) -> str:
    """Use the configured project placeholder, or the bundled fallback if absent."""
    root = Path(current_app.static_folder).resolve()
    for candidate in (value, "img/placeholder.jpg", "img/placeholder.svg"):
        if candidate:
            path = (root / candidate).resolve()
            if path.is_relative_to(root) and path.is_file():
                return url_for("static", filename=candidate)
    raise RuntimeError("The rental image placeholder is missing.")


@bp.app_context_processor
def inject_cart_count():
    if session.get("role") == "customer" and session.get("cart_id"):
        try:
            return {"cart_count": customer_service.cart_count(session["cart_id"])}
        except (RuntimeError, pymysql.MySQLError):
            pass
    return {"cart_count": 0}


@bp.route("/login/customer")
def login_customer():
    """Keep old customer login links working without starting a demo session."""
    return redirect(url_for("login"))


@bp.route("/rentals")
@customer_view
def rentals():
    return render_template(
        "customer/rentals.html",
        sections=customer_service.get_customer_rentals(session["customer_id"]),
    )


@bp.route("/shop")
@customer_view
def select_business():
    query = request.args.get("q", "").strip()
    return render_template(
        "customer/businesses.html", businesses=customer_service.list_businesses(query), query=query,
    )


@bp.route("/shop/<int:business_id>")
@customer_view
def browse(business_id: int):
    business = customer_service.get_business(business_id)
    if business is None:
        abort(404)
    session["business_id"] = business_id

    filter_from = request.args.get("from", "").strip()
    filter_to = request.args.get("to", "").strip()
    filter_start = filter_end = None
    filter_error = None
    if filter_from or filter_to:
        try:
            if not (filter_from and filter_to):
                raise BookingError("Enter both a start and an end to filter by time.")
            filter_start = customer_service.parse_datetime(filter_from)
            filter_end = customer_service.parse_datetime(filter_to)
            if filter_end <= filter_start:
                raise BookingError("The filter end must be after its start.")
        except BookingError as exc:
            filter_start = filter_end = None
            filter_error = str(exc)

    query = request.args.get("q", "").strip()
    equipment = customer_service.list_equipment(business_id, filter_start, filter_end)
    if query:
        equipment = [item for item in equipment if customer_service.equipment_matches(item, query)]
    return render_template(
        "customer/browse.html",
        business=business,
        equipment=equipment,
        filter_from=filter_from,
        filter_to=filter_to,
        filter_active=filter_start is not None,
        filter_error=filter_error,
        query=query,
    )


@bp.route("/api/equipment/<int:equipment_id>/availability")
@customer_view
def equipment_availability(equipment_id: int):
    data = customer_service.get_equipment_availability(equipment_id, session.get("cart_id"))
    if data is None:
        return jsonify(ok=False, error="That equipment is not available."), 404
    return jsonify(ok=True, **data)


@bp.route("/cart/add", methods=["POST"])
@customer_view
def add_to_cart():
    if not _csrf_ok():
        return jsonify(ok=False, error="Your session expired. Reload the page."), 400
    payload = request.get_json(silent=True) or {}
    try:
        equipment_id = int(payload.get("equipment_id"))
        count = customer_service.add_to_cart(
            session["cart_id"], session["customer_id"], equipment_id,
            str(payload.get("start", "")), str(payload.get("end", "")),
        )
    except (TypeError, ValueError) as exc:
        # BookingError is a ValueError, so customer-fixable messages reach the panel too.
        message = str(exc) if isinstance(exc, BookingError) else "The request was not valid."
        return jsonify(ok=False, error=message), 400
    return jsonify(ok=True, cart_count=count)


@bp.route("/cart")
@customer_view
def cart():
    return render_template(
        "customer/cart.html",
        cart=customer_service.get_cart(session["cart_id"], session["customer_id"]),
    )


@bp.route("/cart/remove/<int:cart_item_id>", methods=["POST"])
@customer_view
def remove_from_cart(cart_item_id: int):
    if not _csrf_ok():
        abort(400)
    customer_service.remove_cart_item(session["cart_id"], cart_item_id)
    return redirect(url_for("customer.cart"))


@bp.route("/checkout", methods=["GET", "POST"])
@customer_view
def checkout():
    cart_data = customer_service.get_cart(session["cart_id"], session["customer_id"])
    if not cart_data["items"] or cart_data["has_problem"]:
        flash("Fix your cart before paying.", "error")
        return redirect(url_for("customer.cart"))
    if request.method == "POST":
        if not _csrf_ok():
            abort(400)
        try:
            order = customer_service.checkout(
                session["customer_id"], session["cart_id"],
                request.form.get("card_number", ""), request.form.get("expiry", ""),
                request.form.get("security_code", ""),
            )
        except BookingError as exc:
            flash(str(exc), "error")
            return render_template("customer/payment.html", cart=cart_data), 400
        session["last_order"] = {
            "payment_id": order["payment_id"],
            "total": str(order["total"]),
            "last4": order["last4"],
            "items": [
                {"name": i["equipment_type"], "start": format_datetime(i["start_at"]), "end": format_datetime(i["end_at"])}
                for i in order["items"]
            ],
        }
        return redirect(url_for("customer.confirmation"))
    return render_template("customer/payment.html", cart=cart_data)


@bp.route("/checkout/complete")
@customer_view
def confirmation():
    order = session.get("last_order")
    if order is None:
        return redirect(url_for("customer.select_business"))
    return render_template("customer/confirmation.html", order=order, business_id=session.get("business_id"))
