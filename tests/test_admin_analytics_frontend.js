const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
    path.join(__dirname, "..", "static", "js", "admin_analytics.js"),
    "utf8",
);

const runAnalyticsScript = async (response) => {
    const elements = new Map();
    const element = (id) => {
        if (!elements.has(id)) {
            elements.set(id, {
                id,
                textContent: "",
                hidden: false,
                style: {},
                dataset: {},
                children: [],
                replaceChildren(...children) {
                    this.children = children;
                },
                append(...children) {
                    this.children.push(...children);
                },
                setAttribute() {},
            });
        }
        return elements.get(id);
    };

    const metrics = [
        "total_orders",
        "orders_today",
        "orders_this_week",
        "order_value_this_week",
    ].map((name) => ({
        ...element(`metric-${name}`),
        dataset: { analyticsMetric: name },
    }));
    const completionElements = {
        "[data-completion-percent]": element("completion-percent"),
        "[data-completion-delivered]": element("completion-delivered"),
        "[data-completion-failed]": element("completion-failed"),
        "[data-completion-total]": element("completion-total"),
    };
    const document = {
        hidden: false,
        getElementById: element,
        querySelectorAll(selector) {
            if (selector === "[data-analytics-metric]") {
                return metrics;
            }
            return [];
        },
        querySelector(selector) {
            return completionElements[selector] || null;
        },
        createElement(tagName) {
            return { tagName, style: {}, append() {}, textContent: "" };
        },
        createElementNS(namespace, tagName) {
            return {
                namespace,
                tagName,
                setAttribute() {},
            };
        },
        addEventListener() {},
    };
    const assignedLocations = [];
    const window = {
        location: {
            href: "http://127.0.0.1/admin/analytics",
            assign(location) {
                assignedLocations.push(location);
            },
        },
        clearTimeout() {},
        setTimeout() {
            return 1;
        },
    };
    const context = {
        AbortController,
        URL,
        Intl,
        document,
        window,
        fetch: async () => response,
    };
    vm.runInNewContext(script, context);
    await new Promise((resolve) => setImmediate(resolve));
    return { elements, metrics, assignedLocations };
};

test("HTML server errors are reported without attempting JSON parsing", async () => {
    let jsonCalls = 0;
    const response = {
        status: 500,
        ok: false,
        redirected: false,
        url: "http://127.0.0.1/api/admin/analytics",
        headers: { get: () => "text/html; charset=utf-8" },
        async json() {
            jsonCalls += 1;
            throw new SyntaxError("Unexpected token '<'");
        },
    };

    const { elements, metrics } = await runAnalyticsScript(response);

    assert.equal(jsonCalls, 0);
    assert.equal(
        elements.get("analyticsStatus").textContent,
        "Unable to load analytics",
    );
    assert.match(
        elements.get("analyticsError").textContent,
        /non-JSON response \(HTTP 500\)/,
    );
    assert.equal(
        metrics[0].textContent,
        "Unable to load analytics",
    );
});

test("unauthorized HTML responses send the browser to admin login", async () => {
    let jsonCalls = 0;
    const response = {
        status: 401,
        ok: false,
        redirected: false,
        url: "http://127.0.0.1/api/admin/analytics",
        headers: { get: () => "text/html" },
        async json() {
            jsonCalls += 1;
            throw new SyntaxError("Unexpected token '<'");
        },
    };

    const { assignedLocations } = await runAnalyticsScript(response);

    assert.equal(jsonCalls, 0);
    assert.deepEqual(
        assignedLocations,
        ["/admin-login?next=%2Fadmin%2Fanalytics"],
    );
});

test("redirected login HTML responses do not become JSON parse errors", async () => {
    let jsonCalls = 0;
    const response = {
        status: 200,
        ok: true,
        redirected: true,
        url: "http://127.0.0.1/admin-login?next=%2Fadmin%2Fanalytics",
        headers: { get: () => "text/html; charset=utf-8" },
        async json() {
            jsonCalls += 1;
            throw new SyntaxError("Unexpected token '<'");
        },
    };

    const { assignedLocations } = await runAnalyticsScript(response);

    assert.equal(jsonCalls, 0);
    assert.deepEqual(
        assignedLocations,
        ["/admin-login?next=%2Fadmin%2Fanalytics"],
    );
});
