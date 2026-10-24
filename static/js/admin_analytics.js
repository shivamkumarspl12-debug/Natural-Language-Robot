(() => {
    "use strict";

    const endpoint = "/api/admin/analytics";
    const refreshInterval = 7000;
    const status = document.getElementById("analyticsStatus");
    const updatedAt = document.getElementById("analyticsUpdatedAt");
    const errorMessage = document.getElementById("analyticsError");
    const metricElements = new Map(
        [...document.querySelectorAll("[data-analytics-metric]")].map((element) => [
            element.dataset.analyticsMetric,
            element,
        ]),
    );
    let timer = 0;
    let refreshing = false;
    let requestController = null;
    let lastPayload = null;

    const formatCount = (value) => new Intl.NumberFormat().format(value);
    const formatAmount = (value, currency) => {
        if (currency) {
            return new Intl.NumberFormat(undefined, {
                style: "currency",
                currency,
                maximumFractionDigits: 2,
            }).format(value);
        }
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(value);
    };

    const setMetric = (name, value) => {
        const element = metricElements.get(name);
        if (element) {
            element.textContent = value;
        }
    };

    const setEmpty = (container, text) => {
        const message = document.createElement("p");
        message.className = "analytics-empty";
        message.textContent = text;
        container.replaceChildren(message);
    };

    const renderOrdersChart = (days) => {
        const chart = document.getElementById("ordersChart");
        if (!chart) {
            return;
        }
        if (!days.length) {
            setEmpty(chart, "No data yet");
            return;
        }

        const columns = document.createElement("div");
        columns.className = "bar-columns analytics-columns";
        const maximum = Math.max(1, ...days.map((day) => day.orders));
        days.forEach((day) => {
            const column = document.createElement("div");
            const bar = document.createElement("i");
            const label = document.createElement("span");
            const count = document.createElement("small");
            bar.className = "analytics-bar";
            bar.style.height = `${day.orders ? Math.max(4, day.orders / maximum * 100) : 0}%`;
            label.textContent = day.label;
            count.textContent = formatCount(day.orders);
            column.append(bar, label, count);
            columns.append(column);
        });
        chart.replaceChildren(columns);
    };

    const renderValueChart = (days, currency) => {
        const chart = document.getElementById("revenueChart");
        if (!chart) {
            return;
        }
        if (!days.length) {
            setEmpty(chart, "No data yet");
            return;
        }

        const width = 600;
        const height = 170;
        const values = days.map((day) => day.order_value);
        const maximum = Math.max(1, ...values);
        const points = values.map((value, index) => {
            const x = values.length > 1
                ? index * width / (values.length - 1)
                : width / 2;
            const y = height - value / maximum * (height - 12) - 6;
            return `${x},${y}`;
        });
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("role", "presentation");
        const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
        polyline.setAttribute("points", points.join(" "));
        polyline.setAttribute("fill", "none");
        polyline.setAttribute("stroke", "#769947");
        polyline.setAttribute("stroke-width", "3");
        svg.append(polyline);

        const labels = document.createElement("div");
        labels.className = "chart-x-labels";
        days.forEach((day) => {
            const label = document.createElement("span");
            label.textContent = day.label;
            labels.append(label);
        });
        const plot = document.createElement("div");
        plot.className = "line-plot analytics-line-plot";
        plot.append(svg, labels);
        chart.replaceChildren(plot);
        chart.setAttribute(
            "aria-label",
            `Daily order value: ${days.map((day) => `${day.label} ${formatAmount(day.order_value, currency)}`).join(", ")}`,
        );
    };

    const renderPopularDishes = (dishes) => {
        const list = document.getElementById("popularDishes");
        if (!list) {
            return;
        }
        if (!dishes.length) {
            const item = document.createElement("li");
            item.className = "analytics-empty";
            item.textContent = "No data yet";
            list.replaceChildren(item);
            return;
        }

        const maximum = Math.max(...dishes.map((dish) => dish.quantity));
        const items = dishes.map((dish, index) => {
            const item = document.createElement("li");
            const rank = document.createElement("span");
            rank.className = "popular-rank";
            rank.textContent = String(index + 1).padStart(2, "0");

            const food = document.createElement("span");
            food.className = "popular-food";
            const name = document.createElement("strong");
            name.textContent = dish.name;
            const quantity = document.createElement("small");
            quantity.textContent = `${formatCount(dish.quantity)} ordered`;
            food.append(name, quantity);

            const bar = document.createElement("span");
            bar.className = "popular-bar";
            const fill = document.createElement("i");
            fill.style.width = `${dish.quantity / maximum * 100}%`;
            bar.append(fill);

            const count = document.createElement("strong");
            count.textContent = formatCount(dish.quantity);
            item.append(rank, food, bar, count);
            return item;
        });
        list.replaceChildren(...items);
    };

    const renderRobotCompletion = (completion) => {
        const ring = document.getElementById("completionRing");
        const percent = document.querySelector("[data-completion-percent]");
        const delivered = document.querySelector("[data-completion-delivered]");
        const failed = document.querySelector("[data-completion-failed]");
        const total = document.querySelector("[data-completion-total]");
        const deliveryTime = document.getElementById("deliveryTime");

        if (completion) {
            percent.textContent = `${completion.percent}%`;
            delivered.textContent = formatCount(completion.completed);
            failed.textContent = formatCount(completion.failed);
            total.textContent = `${formatCount(completion.total)} completed simulation tasks`;
            ring.style.background = `conic-gradient(#78994d 0 ${completion.percent}%,#e9eee5 ${completion.percent}% 100%)`;
        } else {
            percent.textContent = "No data yet";
            delivered.textContent = "—";
            failed.textContent = "—";
            total.textContent = "No completed simulation records";
            ring.style.background = "#e9eee5";
        }
        deliveryTime.textContent = "Average delivery time: No data yet";
        deliveryTime.title = "Delivery start timestamps are not stored with orders.";
    };

    const render = (data) => {
        setMetric("total_orders", formatCount(data.total_orders));
        setMetric("orders_today", formatCount(data.orders_today));
        setMetric("orders_this_week", formatCount(data.orders_this_week));
        setMetric(
            "order_value_this_week",
            formatAmount(data.order_value_this_week, data.currency),
        );

        document.querySelectorAll("[data-analytics-timezone]").forEach((element) => {
            element.textContent = data.timezone;
        });
        document.querySelectorAll("[data-currency-note]").forEach((element) => {
            element.textContent = data.currency
                ? `Currency: ${data.currency}. Payment status is not recorded.`
                : "Currency not configured. Payment status is not recorded.";
        });
        document.querySelectorAll("[data-currency-badge]").forEach((element) => {
            element.textContent = data.currency || "Currency not configured";
        });

        renderOrdersChart(data.daily);
        renderValueChart(data.daily, data.currency);
        renderPopularDishes(data.popular_dishes);
        renderRobotCompletion(data.robot_completion);

        updatedAt.dateTime = data.updated_at;
        updatedAt.textContent = new Intl.DateTimeFormat(undefined, {
            dateStyle: "medium",
            timeStyle: "medium",
        }).format(new Date(data.updated_at));
        status.textContent = "Live Firestore data";
        errorMessage.hidden = true;
        lastPayload = data;
    };

    const showError = (message) => {
        status.textContent = lastPayload
            ? "Unable to refresh analytics"
            : "Unable to load analytics";
        errorMessage.textContent = message;
        errorMessage.hidden = false;
        if (!lastPayload) {
            metricElements.forEach((element) => {
                element.textContent = "Unable to load analytics";
            });
            renderOrdersChart([]);
            renderValueChart([], null);
            renderPopularDishes([]);
            renderRobotCompletion(null);
        }
    };

    const scheduleRefresh = (delay) => {
        window.clearTimeout(timer);
        if (!document.hidden) {
            timer = window.setTimeout(refresh, delay);
        }
    };

    const refresh = async () => {
        if (document.hidden || refreshing) {
            return;
        }
        refreshing = true;
        requestController = new AbortController();
        try {
            const response = await fetch(endpoint, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
                signal: requestController.signal,
            });
            const finalUrl = new URL(response.url, window.location.href);
            if (
                response.redirected &&
                finalUrl.pathname === "/admin-login"
            ) {
                window.location.assign(
                    "/admin-login?next=%2Fadmin%2Fanalytics",
                );
                return;
            }
            if (response.status === 401) {
                window.location.assign("/admin-login?next=%2Fadmin%2Fanalytics");
                return;
            }
            const contentType = response.headers.get("content-type") || "";
            if (!/(?:application\/json|application\/[a-z0-9.+-]+\+json)(?:\s*;|$)/i.test(contentType)) {
                throw new Error(
                    `Analytics API returned a non-JSON response (HTTP ${response.status}). Check the Flask server and API route.`,
                );
            }
            let result;
            try {
                result = await response.json();
            } catch (error) {
                throw new Error(
                    `Analytics API returned invalid JSON (HTTP ${response.status}). Check the Flask server logs.`,
                    { cause: error },
                );
            }
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Unable to load analytics.");
            }
            render(result);
        } catch (error) {
            if (error.name !== "AbortError") {
                showError(error instanceof Error
                    ? error.message
                    : "Unable to load analytics.");
            }
        } finally {
            refreshing = false;
            requestController = null;
            scheduleRefresh(refreshInterval);
        }
    };

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            window.clearTimeout(timer);
            requestController?.abort();
        } else {
            refresh();
        }
    });

    refresh();
})();
