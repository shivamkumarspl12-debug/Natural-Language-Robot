const assert = require("node:assert/strict");
const test = require("node:test");
const { createNavigator } = require("../static/js/restaurant_navigation.js");

const tables = {
    1: { x: -7, z: 7 },
    2: { x: 0, z: 7 },
    3: { x: 8, z: 5 },
    4: { x: -1, z: -1 },
    5: { x: 15, z: 7 },
    6: { x: 15, z: -7 },
};
const navigator = createNavigator(tables, {
    rectangles: [
        { minX: -19.5, maxX: -12.5, minZ: -4.35, maxZ: -2.85 },
    ],
});

function pathLength(points) {
    return points.slice(1).reduce((sum, point, index) =>
        sum + Math.hypot(
            point.x - points[index].x,
            point.z - points[index].z,
        ), 0);
}

test("plans safe reachable approaches for every restaurant table", () => {
    const start = { x: -11, z: -7 };
    for (const [tableNumber, table] of Object.entries(tables)) {
        const plan = navigator.planToTable(start, Number(tableNumber));
        assert.ok(plan, `Table ${tableNumber} should be reachable`);
        assert.ok(
            Math.hypot(plan.goal.x - table.x, plan.goal.z - table.z) > 3.7,
            `Table ${tableNumber} approach must remain outside its safety boundary`,
        );
        for (let index = 1; index < plan.points.length; index++) {
            assert.ok(
                navigator.segmentIsClear(plan.points[index - 1], plan.points[index]),
                `Table ${tableNumber} route segment ${index} crosses an obstacle`,
            );
        }
    }
});

test("detours around blocking tables instead of crossing their clearance", () => {
    const start = { x: -11, z: -7 };
    const goal = { x: 12, z: 0 };
    const plan = navigator.planToPoint(start, goal);
    assert.ok(plan, "Target should be reachable around the tables");
    assert.ok(plan.points.length > 2, "Blocked direct route should be detoured");
    assert.ok(
        pathLength(plan.points) > Math.hypot(goal.x - start.x, goal.z - start.z),
        "Detour should be longer than the blocked direct line",
    );
    for (let index = 1; index < plan.points.length; index++) {
        assert.ok(navigator.segmentIsClear(plan.points[index - 1], plan.points[index]));
    }
});

test("delivery to Table 5 detours around intervening tables", () => {
    const start = { x: -11, z: -7 };
    const plan = navigator.planToTable(start, 5);
    assert.ok(plan, "Table 5 should be reachable");
    assert.ok(plan.points.length > 2, "The blocked route should use intermediate waypoints");
    assert.equal(
        navigator.segmentIsClear(start, plan.goal),
        false,
        "The direct route to Table 5's approach must be blocked by a table",
    );
    for (let index = 1; index < plan.points.length; index++) {
        assert.ok(navigator.segmentIsClear(plan.points[index - 1], plan.points[index]));
    }
});

test("returns no path when a wall completely separates valid start and goal", () => {
    const enclosedNavigator = createNavigator({}, {
        bounds: { minX: 0, maxX: 4, minZ: 0, maxZ: 4 },
        cellSize: 0.25,
        robotRadius: 0,
        safetyMargin: 0,
        circles: [],
        rectangles: [{ minX: 1.9, maxX: 2.1, minZ: 0, maxZ: 4 }],
    });
    const plan = enclosedNavigator.planToPoint(
        { x: 0.5, z: 2 },
        { x: 3.5, z: 2 },
    );
    assert.equal(plan, null);
});

test("rejects a target inside a table collision boundary", () => {
    assert.equal(
        navigator.planToPoint({ x: -11, z: -7 }, tables[3]),
        null,
    );
});
