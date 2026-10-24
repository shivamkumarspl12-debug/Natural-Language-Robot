(() => {
    "use strict";

    const dashboard = document.getElementById("trackingDashboard");
    if (!dashboard) return;

    const tableLocations = {
        1: { x: 390, y: 125 },
        2: { x: 590, y: 125 },
        3: { x: 790, y: 125 },
        4: { x: 390, y: 420 },
        5: { x: 590, y: 420 },
        6: { x: 790, y: 420 }
    };
    const counterLocation = { x: 238, y: 285 };
    const positionNode = document.getElementById("trackingPosition");
    const destinationNode = document.getElementById("trackingDestination");
    const statusNode = document.getElementById("trackingStatusChip");
    const deliveryNode = document.getElementById("trackingDeliveryStatus");
    const orderNode = document.getElementById("trackingOrderId");
    const customerNode = document.getElementById("trackingCustomer");
    const itemsNode = document.getElementById("trackingItems");
    const totalNode = document.getElementById("trackingTotal");
    const batteryNode = document.getElementById("trackingBattery");
    const batteryFill = document.getElementById("trackingBatteryFill");
    const sourceNode = document.getElementById("trackingSource");
    const updatedNode = document.getElementById("trackingUpdated");
    const marker = document.getElementById("robotMarker");
    const route = document.getElementById("robotRoute");
    const markerLabel = document.getElementById("robotMapLabel");
    const destinationLabel = document.getElementById("destinationMapLabel");
    const errorNode = document.getElementById("trackingError");

    const titleCase = (value) => String(value || "Unknown")
        .toLowerCase()
        .replace(/\b\w/g, (character) => character.toUpperCase());

    const currentMapPosition = (location) => {
        const match = String(location || "").match(/table\s*(\d+)/i);
        return match && tableLocations[Number(match[1])]
            ? tableLocations[Number(match[1])]
            : counterLocation;
    };

    const renderTables = (tables, destinationTable) => {
        const list = document.getElementById("trackingTableList");
        tables.forEach(({ table, status }) => {
            const number = Number(table);
            const mapTable = document.querySelector(`[data-map-table="${number}"]`);
            const row = list.querySelector(`.tracking-table-row:nth-child(${number})`);
            if (!mapTable || !row) return;

            const shownStatus = number === Number(destinationTable) ? "Delivery target" : status;
            const stateClass = shownStatus === "Delivery target"
                ? "target"
                : shownStatus.toLowerCase().replace(/\s+/g, "-");
            mapTable.classList.remove("is-available", "is-occupied", "is-reserved", "is-target");
            mapTable.classList.add(`is-${stateClass}`);
            mapTable.querySelector(".table-status").textContent = shownStatus.toUpperCase();
            row.querySelector(".table-state").textContent = shownStatus;
            row.querySelector(".table-state").className = `table-state is-${stateClass}`;
        });
    };

    const updateTracking = (data) => {
        const currentPosition = currentMapPosition(data.current_position);
        const destinationTable = Number(data.destination_table);
        const destination = tableLocations[destinationTable] || counterLocation;
        const battery = Math.max(0, Math.min(100, Number(data.battery) || 0));
        const positionText = titleCase(data.current_position);

        statusNode.textContent = titleCase(data.status);
        positionNode.textContent = positionText;
        destinationNode.textContent = destinationTable ? `Table ${destinationTable}` : "Not assigned";
        deliveryNode.textContent = titleCase(data.delivery_status);
        orderNode.textContent = data.current_order_id || "No active demo order";
        if (customerNode) customerNode.textContent = data.current_order_customer || "—";
        if (itemsNode) {
            itemsNode.textContent = Array.isArray(data.current_order_items)
                ? data.current_order_items.map(item => `${item.quantity} × ${item.name}`).join(", ") || "—"
                : "—";
        }
        if (totalNode) {
            totalNode.textContent = Number.isFinite(Number(data.current_order_total))
                ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(data.current_order_total)
                : "—";
        }
        batteryNode.textContent = `${battery}%`;
        batteryFill.style.width = `${battery}%`;
        sourceNode.textContent = data.source
            || (data.controller_update_received
                ? "Updated from Python RobotController · Demo only"
                : "Sample preview · waiting for a software-controller update");
        updatedNode.textContent = data.updated_at
            ? `Last update: ${new Date(data.updated_at).toLocaleString()}`
            : "No controller report received in this session.";

        marker.setAttribute("transform", `translate(${currentPosition.x} ${currentPosition.y})`);
        markerLabel.setAttribute("x", currentPosition.x);
        markerLabel.setAttribute("y", currentPosition.y - 30);
        markerLabel.textContent = `ROBOT · ${positionText.toUpperCase()}`;
        destinationLabel.setAttribute("x", destination.x);
        destinationLabel.setAttribute("y", destination.y - 48);
        destinationLabel.textContent = destinationTable ? `TARGET · TABLE ${destinationTable}` : "NO ACTIVE DELIVERY";
        route.setAttribute("d", destinationTable
            ? `M ${currentPosition.x} ${currentPosition.y} L 310 ${currentPosition.y} L 310 285 L ${destination.x} 285 L ${destination.x} ${destination.y}`
            : "");
        renderTables(data.tables || [], destinationTable);
        errorNode.textContent = data.tracking_warning || "";
        errorNode.hidden = !data.tracking_warning;
    };

    const pollTracking = async () => {
        try {
            const response = await fetch(dashboard.dataset.apiUrl, {
                headers: { Accept: "application/json" },
                cache: "no-store"
            });
            if (!response.ok) throw new Error(`Tracking endpoint returned ${response.status}.`);
            const data = await response.json();
            if (!data.demo_mode) throw new Error("Unexpected telemetry source.");
            updateTracking(data);
        } catch (error) {
            errorNode.textContent = `Tracking demo could not refresh: ${error.message}`;
            errorNode.hidden = false;
        }
    };

    pollTracking();
    window.setInterval(pollTracking, 10000);
})();