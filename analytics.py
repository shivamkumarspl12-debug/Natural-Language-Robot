import os
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from customer_orders import ORDER_COLLECTION, normalize_order_status
from firebase_db import get_firestore_client


class AnalyticsConfigurationError(ValueError):
    pass


class AnalyticsDataError(RuntimeError):
    pass


REVENUE_STATUSES = {
    "Order Placed",
    "Accepted",
    "Preparing",
    "Ready",
    "Robot Delivery",
    "Delivered",
    "Completed",
}
TERMINAL_SIMULATION_STATES = {"delivered", "failed"}


def _analytics_timezone(timezone_name):
    try:
        return ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise AnalyticsConfigurationError(
            "RESTAURANT_TIMEZONE must be a valid IANA timezone."
        ) from error


def _money_in_cents(value):
    if isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int(amount * 100)


def _order_timestamp(value):
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _configured_currency(currency):
    if currency in (None, ""):
        return None
    if not isinstance(currency, str) or not re.fullmatch(
        r"[A-Za-z]{3}",
        currency.strip(),
    ):
        raise AnalyticsConfigurationError(
            "RESTAURANT_CURRENCY must be a three-letter ISO currency code."
        )
    return currency.strip().upper()


def _aggregation_count_value(results):
    if not results:
        return 0

    result = results[0]
    if isinstance(result, (list, tuple)):
        if not result:
            raise AnalyticsDataError(
                "Firestore returned an empty analytics count aggregation."
            )
        result = result[0]

    value = getattr(result, "value", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticsDataError(
            "Firestore returned an invalid analytics count aggregation."
        )
    return int(value)


def aggregate_order_analytics(orders, total_orders, now, timezone_name, currency):
    local_timezone = _analytics_timezone(timezone_name)
    currency_code = _configured_currency(currency)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    local_now = current_time.astimezone(local_timezone)
    today = local_now.date()
    week_start = today - timedelta(days=today.weekday())
    daily = {
        week_start + timedelta(days=offset): {
            "orders": 0,
            "order_value_cents": 0,
        }
        for offset in range(7)
    }
    seen_order_ids = set()
    popular_dishes = Counter()
    simulation_tasks = {}
    orders_today = 0
    orders_this_week = 0
    order_value_this_week_cents = 0

    for index, order in enumerate(orders):
        if not isinstance(order, dict):
            continue
        order_id = order.get("id")
        if order_id is None:
            order_id = f"anonymous-{index}"
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)

        created_at = _order_timestamp(order.get("created_at"))
        if created_at is None:
            continue
        local_created_at = created_at.astimezone(local_timezone)
        order_date = local_created_at.date()
        if order_date not in daily:
            continue

        daily[order_date]["orders"] += 1
        if order_date == today:
            orders_today += 1
        if order_date >= week_start and created_at <= current_time:
            orders_this_week += 1

        status = normalize_order_status(order.get("status"))
        order_value_cents = _money_in_cents(order.get("total"))
        revenue_eligible = (
            status in REVENUE_STATUSES and order_value_cents is not None
        )
        if revenue_eligible:
            daily[order_date]["order_value_cents"] += order_value_cents
            if order_date >= week_start and created_at <= current_time:
                order_value_this_week_cents += order_value_cents
                items = order.get("items")
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        name = item.get("name")
                        quantity = item.get("quantity", 1)
                        if (
                            isinstance(name, str)
                            and name.strip()
                            and isinstance(quantity, int)
                            and not isinstance(quantity, bool)
                            and quantity > 0
                        ):
                            popular_dishes[name.strip()] += quantity

        simulation_id = order.get("delivery_simulation_id")
        simulation_state = order.get("delivery_simulation_state")
        if (
            isinstance(simulation_id, str)
            and simulation_id
            and simulation_state in TERMINAL_SIMULATION_STATES
        ):
            simulation_tasks[simulation_id] = simulation_state

    daily_chart = []
    for offset in range(7):
        chart_date = week_start + timedelta(days=offset)
        values = daily[chart_date]
        daily_chart.append({
            "date": chart_date.isoformat(),
            "label": chart_date.strftime("%a"),
            "orders": values["orders"],
            "order_value": values["order_value_cents"] / 100,
        })

    popular = [
        {"name": name, "quantity": quantity}
        for name, quantity in popular_dishes.most_common(5)
    ]
    completed_tasks = sum(
        state == "delivered" for state in simulation_tasks.values()
    )
    failed_tasks = sum(state == "failed" for state in simulation_tasks.values())
    terminal_tasks = completed_tasks + failed_tasks

    return {
        "total_orders": max(0, int(total_orders)),
        "orders_today": orders_today,
        "orders_this_week": orders_this_week,
        "order_value_this_week": order_value_this_week_cents / 100,
        "currency": currency_code,
        "currency_configured": currency_code is not None,
        "timezone": timezone_name,
        "daily": daily_chart,
        "popular_dishes": popular,
        "average_delivery_minutes": None,
        "robot_completion": (
            {
                "completed": completed_tasks,
                "failed": failed_tasks,
                "total": terminal_tasks,
                "percent": round(completed_tasks * 100 / terminal_tasks, 1),
            }
            if terminal_tasks
            else None
        ),
        "delivery_time_unavailable_reason": (
            "Delivery start timestamps are not stored with orders."
        ),
        "updated_at": current_time.isoformat(timespec="seconds"),
        "week_start": week_start.isoformat(),
    }


def load_order_analytics(now=None, timezone_name=None, currency=None):
    timezone_name = timezone_name or os.environ.get(
        "RESTAURANT_TIMEZONE",
        "UTC",
    )
    currency = currency if currency is not None else os.environ.get(
        "RESTAURANT_CURRENCY",
        "",
    )
    local_timezone = _analytics_timezone(timezone_name)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    local_now = current_time.astimezone(local_timezone)
    week_start = local_now.date() - timedelta(days=local_now.weekday())
    week_start_local = datetime.combine(
        week_start,
        time.min,
        tzinfo=local_timezone,
    )
    week_start_utc = week_start_local.astimezone(timezone.utc)

    collection = get_firestore_client().collection(ORDER_COLLECTION)
    total_result = collection.count(alias="total_orders").get()
    total_orders = _aggregation_count_value(total_result)
    snapshots = (
        collection
        .where("created_at", ">=", week_start_utc)
        .where("created_at", "<=", current_time)
        .stream()
    )
    orders = []
    for snapshot in snapshots:
        order = snapshot.to_dict()
        if order is not None:
            order.setdefault("id", snapshot.id)
            orders.append(order)

    return aggregate_order_analytics(
        orders,
        total_orders,
        current_time,
        timezone_name,
        currency,
    )
