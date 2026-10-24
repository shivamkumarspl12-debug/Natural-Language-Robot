"use strict";

(function (root, factory) {
    const navigation = factory();
    if (typeof module !== "undefined" && module.exports) {
        module.exports = navigation;
    }
    root.RestaurantNavigation = navigation;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    const DEFAULTS = {
        bounds: { minX: -21.9, maxX: 21.9, minZ: -16.9, maxZ: 16.9 },
        cellSize: 0.25,
        robotRadius: 0.75,
        safetyMargin: 0.2,
        tableRadius: 2.75,
        rectangles: [
            { minX: -19.6, maxX: -12.4, minZ: -4.9, maxZ: -2.8 },
        ],
    };

    const DIRECTIONS = [
        [1, 0], [0, 1], [-1, 0], [0, -1],
        [1, 1], [1, -1], [-1, 1], [-1, -1],
    ];

    function distance(a, b) {
        return Math.hypot(a.x - b.x, a.z - b.z);
    }

    function segmentIntersectsRectangle(start, end, rectangle) {
        let low = 0;
        let high = 1;
        const dx = end.x - start.x;
        const dz = end.z - start.z;
        const edges = [
            [-dx, start.x - rectangle.minX],
            [dx, rectangle.maxX - start.x],
            [-dz, start.z - rectangle.minZ],
            [dz, rectangle.maxZ - start.z],
        ];

        for (const [direction, offset] of edges) {
            if (direction === 0) {
                if (offset < 0) return false;
                continue;
            }
            const ratio = offset / direction;
            if (direction < 0) {
                if (ratio > high) return false;
                low = Math.max(low, ratio);
            } else {
                if (ratio < low) return false;
                high = Math.min(high, ratio);
            }
        }
        return low <= high;
    }

    function distanceToSegment(point, start, end) {
        const dx = end.x - start.x;
        const dz = end.z - start.z;
        const lengthSquared = dx * dx + dz * dz;
        if (lengthSquared === 0) return distance(point, start);
        const projection = Math.max(0, Math.min(1,
            ((point.x - start.x) * dx + (point.z - start.z) * dz) /
                lengthSquared,
        ));
        return Math.hypot(
            point.x - (start.x + projection * dx),
            point.z - (start.z + projection * dz),
        );
    }

    function createMinHeap() {
        const values = [];
        return {
            get size() {
                return values.length;
            },
            push(value) {
                values.push(value);
                let index = values.length - 1;
                while (index > 0) {
                    const parent = Math.floor((index - 1) / 2);
                    if (values[parent].score <= value.score) break;
                    values[index] = values[parent];
                    index = parent;
                }
                values[index] = value;
            },
            pop() {
                const first = values[0];
                const last = values.pop();
                if (values.length && last) {
                    let index = 0;
                    while (true) {
                        const left = index * 2 + 1;
                        const right = left + 1;
                        if (left >= values.length) break;
                        const child = right < values.length &&
                            values[right].score < values[left].score ? right : left;
                        if (values[child].score >= last.score) break;
                        values[index] = values[child];
                        index = child;
                    }
                    values[index] = last;
                }
                return first;
            },
        };
    }

    function createNavigator(tablePositions = {}, options = {}) {
        const config = {
            ...DEFAULTS,
            ...options,
            bounds: { ...DEFAULTS.bounds, ...(options.bounds || {}) },
            rectangles: options.rectangles || DEFAULTS.rectangles,
            circles: options.circles || Object.values(tablePositions).map(position => ({
                x: position.x,
                z: position.z,
                radius: DEFAULTS.tableRadius,
            })),
        };
        const clearance = config.robotRadius + config.safetyMargin;
        const gridWidth = Math.floor(
            (config.bounds.maxX - config.bounds.minX) / config.cellSize,
        ) + 1;
        const gridDepth = Math.floor(
            (config.bounds.maxZ - config.bounds.minZ) / config.cellSize,
        ) + 1;
        const maxGridX = gridWidth - 1;
        const maxGridZ = gridDepth - 1;

        function pointIsClear(point) {
            const { minX, maxX, minZ, maxZ } = config.bounds;
            if (
                point.x < minX || point.x > maxX ||
                point.z < minZ || point.z > maxZ
            ) return false;

            for (const rectangle of config.rectangles) {
                if (
                    point.x >= rectangle.minX - clearance &&
                    point.x <= rectangle.maxX + clearance &&
                    point.z >= rectangle.minZ - clearance &&
                    point.z <= rectangle.maxZ + clearance
                ) return false;
            }
            for (const circle of config.circles) {
                if (distance(point, circle) <= circle.radius + clearance) {
                    return false;
                }
            }
            return true;
        }

        function segmentIsClear(start, end) {
            if (!pointIsClear(start) || !pointIsClear(end)) return false;
            for (const rectangle of config.rectangles) {
                const expanded = {
                    minX: rectangle.minX - clearance,
                    maxX: rectangle.maxX + clearance,
                    minZ: rectangle.minZ - clearance,
                    maxZ: rectangle.maxZ + clearance,
                };
                if (segmentIntersectsRectangle(start, end, expanded)) return false;
            }
            for (const circle of config.circles) {
                if (distanceToSegment(circle, start, end) <= circle.radius + clearance) {
                    return false;
                }
            }
            return true;
        }

        function smoothPath(points) {
            if (points.length < 3) return points;
            const smoothed = [points[0]];
            let anchor = 0;
            while (anchor < points.length - 1) {
                let next = points.length - 1;
                while (
                    next > anchor + 1 &&
                    !segmentIsClear(points[anchor], points[next])
                ) next--;
                smoothed.push(points[next]);
                anchor = next;
            }
            return smoothed;
        }

        function planToGoals(start, goals) {
            if (!pointIsClear(start) || goals.some(goal => !pointIsClear(goal))) {
                return null;
            }
            let directGoal = null;
            let directDistance = Infinity;
            for (const goal of goals) {
                const cost = distance(start, goal);
                if (cost < directDistance && segmentIsClear(start, goal)) {
                    directGoal = goal;
                    directDistance = cost;
                }
            }
            if (directGoal) {
                return {
                    points: [start, directGoal],
                    goal: directGoal,
                    distance: directDistance,
                };
            }

            const nearestGridX = Math.round(
                (start.x - config.bounds.minX) / config.cellSize,
            );
            const nearestGridZ = Math.round(
                (start.z - config.bounds.minZ) / config.cellSize,
            );
            const key = (x, z) => z * gridWidth + x;
            const gridPoint = (x, z) => ({
                x: config.bounds.minX + x * config.cellSize,
                z: config.bounds.minZ + z * config.cellSize,
            });
            const open = createMinHeap();
            const scores = new Map();
            const parents = new Map();

            function heuristic(point) {
                let minimum = Infinity;
                for (const goal of goals) {
                    minimum = Math.min(minimum, distance(point, goal));
                }
                return minimum;
            }

            for (let x = nearestGridX - 2; x <= nearestGridX + 2; x++) {
                for (let z = nearestGridZ - 2; z <= nearestGridZ + 2; z++) {
                    if (x < 0 || z < 0 || x > maxGridX || z > maxGridZ) continue;
                    const point = gridPoint(x, z);
                    const initialCost = distance(start, point);
                    if (
                        initialCost > config.cellSize * 1.5 ||
                        !segmentIsClear(start, point)
                    ) continue;
                    const nodeKey = key(x, z);
                    if (initialCost >= (scores.get(nodeKey) ?? Infinity)) continue;
                    scores.set(nodeKey, initialCost);
                    parents.set(nodeKey, -1);
                    open.push({
                        x,
                        z,
                        key: nodeKey,
                        score: initialCost + heuristic(point),
                    });
                }
            }

            let best = null;
            let bestCost = Infinity;
            while (open.size) {
                const current = open.pop();
                const currentScore = scores.get(current.key);
                if (currentScore === undefined) continue;
                const currentPoint = gridPoint(current.x, current.z);
                if (current.score > currentScore + heuristic(currentPoint) + 1e-8) {
                    continue;
                }
                if (current.score >= bestCost) break;

                for (const goal of goals) {
                    const finalLeg = distance(currentPoint, goal);
                    const totalCost = currentScore + finalLeg;
                    if (
                        totalCost < bestCost &&
                        segmentIsClear(currentPoint, goal)
                    ) {
                        best = { current, goal };
                        bestCost = totalCost;
                    }
                }

                for (const [dx, dz] of DIRECTIONS) {
                    const x = current.x + dx;
                    const z = current.z + dz;
                    if (x < 0 || z < 0 || x > maxGridX || z > maxGridZ) continue;
                    const nextPoint = gridPoint(x, z);
                    if (!segmentIsClear(currentPoint, nextPoint)) continue;
                    const nextKey = key(x, z);
                    const stepCost = distance(currentPoint, nextPoint);
                    const tentative = currentScore + stepCost;
                    if (tentative >= (scores.get(nextKey) ?? Infinity)) continue;
                    scores.set(nextKey, tentative);
                    parents.set(nextKey, current.key);
                    open.push({
                        x,
                        z,
                        key: nextKey,
                        score: tentative + heuristic(nextPoint),
                    });
                }
            }

            if (!best) return null;
            const reversed = [];
            let nodeKey = best.current.key;
            while (nodeKey !== -1) {
                const x = nodeKey % gridWidth;
                const z = Math.floor(nodeKey / gridWidth);
                reversed.push(gridPoint(x, z));
                nodeKey = parents.get(nodeKey);
            }
            reversed.reverse();
            const points = smoothPath([start, ...reversed, best.goal]);
            let pathDistance = 0;
            for (let index = 1; index < points.length; index++) {
                pathDistance += distance(points[index - 1], points[index]);
            }
            return { points, goal: best.goal, distance: pathDistance };
        }

        function planToPoint(start, goal) {
            return planToGoals(start, [goal]);
        }

        function planToTable(start, tableNumber) {
            const table = tablePositions[tableNumber];
            if (!table) return null;
            const approachRadius = config.tableRadius + clearance + 0.35;
            const approaches = [];
            for (let index = 0; index < 16; index++) {
                const angle = index * Math.PI / 8;
                approaches.push({
                    x: table.x + Math.cos(angle) * approachRadius,
                    z: table.z + Math.sin(angle) * approachRadius,
                });
            }
            let best = null;
            for (const approach of approaches) {
                const candidate = planToPoint(start, approach);
                if (candidate && (!best || candidate.distance < best.distance)) {
                    best = candidate;
                }
            }
            return best;
        }

        return { planToPoint, planToTable, pointIsClear, segmentIsClear };
    }

    return { createNavigator, defaults: DEFAULTS };
});
