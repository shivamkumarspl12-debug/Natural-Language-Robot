(() => {
    "use strict";

    const ORDER_REFERENCES_KEY = "verdantCustomerOrdersV1";
    const container = document.getElementById("robotScene");
    const messageNode = document.getElementById("trackingMessage");
    const statusNode = document.getElementById("trackingOrderStatus");
    const errorNode = document.getElementById("trackingError");
    const captionNode = document.getElementById("sceneCaption");

    const showError = (message) => {
        errorNode.textContent = message;
        errorNode.hidden = false;
    };

    const isLocalAddress = (hostname) =>
        hostname === "localhost"
        || hostname === "::1"
        || hostname.startsWith("127.");

    const readOrderReference = () => {
        try {
            const stored = JSON.parse(
                window.localStorage.getItem(ORDER_REFERENCES_KEY) || "[]"
            );
            if (!Array.isArray(stored)) return null;
            const requestedId = new URLSearchParams(window.location.search)
                .get("order_id");
            return stored.find((entry) =>
                entry
                && typeof entry.id === "string"
                && typeof entry.accessToken === "string"
                && (!requestedId || entry.id === requestedId)
            ) || null;
        } catch {
            return null;
        }
    };

    const createScene = () => {
        if (!window.THREE) {
            showError("The 3D view could not load. Check the network connection and reload.");
            return null;
        }

        const THREE = window.THREE;
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0b1b22);
        scene.fog = new THREE.Fog(0x0b1b22, 34, 70);

        const width = Math.max(container.clientWidth, 1);
        const height = Math.max(container.clientHeight, 1);
        const camera = new THREE.PerspectiveCamera(43, width / height, 0.1, 100);
        camera.position.set(22, 24, 27);
        camera.lookAt(2, 0, 0);

        let renderer;
        try {
            renderer = new THREE.WebGLRenderer({
                antialias: true,
                alpha: false,
                powerPreference: "low-power"
            });
        } catch {
            showError("This browser could not start the 3D view. Try an updated browser with WebGL enabled.");
            return null;
        }
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        renderer.setSize(width, height);
        renderer.shadowMap.enabled = false;
        container.appendChild(renderer.domElement);

        scene.add(new THREE.HemisphereLight(0xd9eee1, 0x192a2b, 2.1));
        const keyLight = new THREE.DirectionalLight(0xffe8bd, 2.2);
        keyLight.position.set(-8, 18, 12);
        scene.add(keyLight);

        const floor = new THREE.Mesh(
            new THREE.PlaneGeometry(36, 25),
            new THREE.MeshStandardMaterial({
                color: 0x20362f,
                roughness: 0.9,
                metalness: 0
            })
        );
        floor.rotation.x = -Math.PI / 2;
        floor.position.set(3, -0.08, 0);
        scene.add(floor);

        const grid = new THREE.GridHelper(36, 18, 0x5c806c, 0x344e43);
        grid.position.set(3, 0, 0);
        scene.add(grid);

        const makeBox = (parent, size, color, position) => {
            const geometry = new THREE.BoxGeometry(...size);
            const material = new THREE.MeshStandardMaterial({
                color,
                roughness: 0.68,
                metalness: 0.08
            });
            const mesh = new THREE.Mesh(geometry, material);
            mesh.position.set(...position);
            parent.add(mesh);
            return mesh;
        };

        makeBox(scene, [2.4, 0.7, 1.5], 0x456b59, [-11, 0.35, -7]);
        const counterLabel = makeBox(
            scene,
            [0.8, 0.08, 0.04],
            0xc4df8d,
            [-11, 0.64, -6.22]
        );
        counterLabel.rotation.y = Math.PI;

        const tablePositions = {
            1: [-7, 7],
            2: [0, 7],
            3: [8, 5],
            4: [-1, -1],
            5: [15, 7],
            6: [15, -7]
        };
        const tableMaterials = new Map();
        Object.entries(tablePositions).forEach(([tableNumber, [x, z]]) => {
            const table = makeBox(scene, [2.2, 0.22, 1.8], 0x8c7556, [x, 0.82, z]);
            makeBox(scene, [0.24, 0.8, 0.24], 0x65533f, [x, 0.4, z]);
            tableMaterials.set(Number(tableNumber), table.material);
        });

        const robot = new THREE.Group();
        robot.visible = false;
        const shell = new THREE.MeshStandardMaterial({
            color: 0xe6eee5,
            roughness: 0.4,
            metalness: 0.12
        });
        const trim = new THREE.MeshStandardMaterial({
            color: 0x37745a,
            roughness: 0.38,
            metalness: 0.16
        });
        const dark = new THREE.MeshStandardMaterial({
            color: 0x1d2d32,
            roughness: 0.4
        });
        const addRobotPart = (geometry, material, position) => {
            const part = new THREE.Mesh(geometry, material);
            part.position.set(...position);
            robot.add(part);
            return part;
        };
        addRobotPart(new THREE.CylinderGeometry(0.31, 0.39, 0.66, 12), shell, [0, 1.16, 0]);
        addRobotPart(new THREE.SphereGeometry(0.34, 12, 8), shell, [0, 1.49, 0]);
        addRobotPart(new THREE.SphereGeometry(0.29, 16, 12), shell, [0, 1.9, 0]);
        addRobotPart(new THREE.BoxGeometry(0.38, 0.12, 0.08), trim, [0, 1.93, 0.24]);
        addRobotPart(new THREE.CylinderGeometry(0.13, 0.17, 0.12, 12), trim, [0, 0.72, 0]);

        const leftArm = addRobotPart(
            new THREE.CylinderGeometry(0.09, 0.1, 0.55, 8),
            shell,
            [-0.46, 1.15, 0]
        );
        leftArm.rotation.z = -0.22;
        const rightArm = addRobotPart(
            new THREE.CylinderGeometry(0.09, 0.1, 0.55, 8),
            shell,
            [0.46, 1.15, 0]
        );
        rightArm.rotation.z = 0.22;
        const leftLeg = addRobotPart(
            new THREE.CylinderGeometry(0.11, 0.13, 0.55, 10),
            dark,
            [-0.17, 0.38, 0]
        );
        const rightLeg = addRobotPart(
            new THREE.CylinderGeometry(0.11, 0.13, 0.55, 10),
            dark,
            [0.17, 0.38, 0]
        );
        makeBox(robot, [0.64, 0.04, 0.38], 0xc4df8d, [0, 0.82, -0.34]);
        scene.add(robot);

        const destinationRing = new THREE.Mesh(
            new THREE.RingGeometry(1.15, 1.32, 32),
            new THREE.MeshBasicMaterial({
                color: 0xc4df8d,
                side: THREE.DoubleSide,
                transparent: true,
                opacity: 0.9
            })
        );
        destinationRing.rotation.x = -Math.PI / 2;
        destinationRing.position.y = 0.04;
        destinationRing.visible = false;
        scene.add(destinationRing);

        const resize = () => {
            const nextWidth = Math.max(container.clientWidth, 1);
            const nextHeight = Math.max(container.clientHeight, 1);
            camera.aspect = nextWidth / nextHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(nextWidth, nextHeight);
        };
        window.addEventListener("resize", resize);
        if ("ResizeObserver" in window) {
            new ResizeObserver(resize).observe(container);
        }

        let animationFrame = 0;
        let rendering = false;
        const renderFrame = () => {
            if (!rendering) return;
            animationFrame = window.requestAnimationFrame(renderFrame);
            renderer.render(scene, camera);
        };
        const startRendering = () => {
            if (rendering) return;
            rendering = true;
            renderFrame();
        };
        const stopRendering = () => {
            rendering = false;
            window.cancelAnimationFrame(animationFrame);
        };
        startRendering();

        return {
            robot,
            destinationRing,
            tableMaterials,
            startRendering,
            stopRendering,
            renderer
        };
    };

    const secureForCustomer = () =>
        window.isSecureContext || isLocalAddress(window.location.hostname);

    const reference = readOrderReference();
    const scene = createScene();

    if (!secureForCustomer()) {
        messageNode.textContent = "For your privacy, robot tracking must be opened over HTTPS on your local network.";
        statusNode.textContent = "Secure connection required";
        showError("The order access code was not sent. Connect through the HTTPS address supplied by the restaurant.");
    } else if (!reference) {
        messageNode.textContent = "Your order access is not saved for this secure site address.";
        statusNode.textContent = "No authorized order on this device";
        showError("Open the restaurant's HTTPS menu on this phone and place the order there. Order access is kept in that browser and is never added to the tracking URL.");
    } else {
        let requestPending = false;
        let pollingTimer = null;

        const refresh = async () => {
            if (requestPending || document.hidden) return;
            requestPending = true;
            try {
                const response = await fetch(
                    `/api/customer/orders/${encodeURIComponent(reference.id)}/tracking`,
                    {
                        headers: {
                            Accept: "application/json",
                            "X-Order-Access-Token": reference.accessToken
                        }
                    }
                );
                if (!(response.headers.get("content-type") || "")
                    .includes("application/json")) {
                    throw new Error("The tracking service returned an unexpected response.");
                }
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.error || "Could not load this order's tracking.");
                }

                const tracking = result.tracking;
                messageNode.textContent = tracking.message;
                statusNode.textContent = `Order status: ${tracking.status}`;
                errorNode.hidden = true;
                if (tracking.destination_table) {
                    captionNode.textContent =
                        `Destination: table ${tracking.destination_table}. Position comes from the admin simulation.`;
                } else {
                    captionNode.textContent = "Waiting for a delivery mission.";
                }

                if (scene && tracking.position
                    && Number.isFinite(tracking.position.x)
                    && Number.isFinite(tracking.position.z)) {
                    scene.robot.position.set(
                        tracking.position.x,
                        0,
                        tracking.position.z
                    );
                    scene.robot.visible = true;
                }

                if (scene) {
                    scene.destinationRing.visible =
                        Number.isInteger(tracking.destination_table);
                    const destination = scene.destinationRing.visible
                        ? {
                            1: [-7, 7],
                            2: [0, 7],
                            3: [8, 5],
                            4: [-1, -1],
                            5: [15, 7],
                            6: [15, -7]
                        }[tracking.destination_table]
                        : null;
                    if (destination) {
                        scene.destinationRing.position.set(
                            destination[0],
                            0.04,
                            destination[1]
                        );
                    }
                    scene.tableMaterials.forEach((material, tableNumber) => {
                        material.color.set(
                            tableNumber === tracking.destination_table
                                ? 0xc4df8d
                                : 0x8c7556
                        );
                    });
                }
            } catch (error) {
                messageNode.textContent = "Robot tracking is temporarily unavailable.";
                showError(error.message);
            } finally {
                requestPending = false;
            }
        };

        const updatePolling = () => {
            if (document.hidden) {
                scene?.stopRendering();
                if (pollingTimer !== null) {
                    window.clearInterval(pollingTimer);
                    pollingTimer = null;
                }
                return;
            }
            scene?.startRendering();
            if (pollingTimer === null) {
                void refresh();
                pollingTimer = window.setInterval(refresh, 5000);
            }
        };

        document.addEventListener("visibilitychange", updatePolling);
        updatePolling();
        window.addEventListener("pagehide", () => {
            if (pollingTimer !== null) window.clearInterval(pollingTimer);
            if (scene) {
                scene.stopRendering();
                scene.renderer.dispose();
            }
        }, { once: true });
    }
})();
