(() => {
    "use strict";

    const toast = document.getElementById("toastMessage");
    const dialog = document.getElementById("detailDialog");
    const dialogTitle = document.getElementById("dialogTitle");
    const dialogBody = document.getElementById("dialogBody");
    let toastTimer = 0;
    let editingMenuItem = null;
    const menuItemsById = new Map();
    const customerHistoryById = new Map();

    const showToast = (message) => {
        if (!toast) {
            return;
        }
        toast.textContent = message;
        toast.classList.add("show");
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3000);
    };

    const openDialog = (title, content) => {
        if (!dialog || !dialogTitle || !dialogBody) {
            throw new Error("The shared dashboard dialog is unavailable.");
        }
        dialogTitle.textContent = title;
        dialogBody.replaceChildren();
        if (typeof content === "string") {
            dialogBody.innerHTML = content;
        } else {
            dialogBody.append(content);
        }
        dialog.showModal();
    };

    document.querySelectorAll(".dialog-close").forEach((button) => {
        button.addEventListener("click", () => dialog?.close());
    });
    dialog?.addEventListener("click", (event) => {
        if (event.target === dialog) {
            dialog.close();
        }
    });

    document.querySelectorAll("[data-toast]").forEach((button) => {
        button.addEventListener("click", () => showToast(button.dataset.toast));
    });

    document.querySelector(".notification-button")?.addEventListener("click", () => {
        showToast("You're all caught up in this demo workspace.");
    });

    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    sidebarToggle?.addEventListener("click", () => {
        const isOpen = sidebar.classList.toggle("is-open");
        sidebarToggle.setAttribute("aria-expanded", String(isOpen));
    });
    document.addEventListener("click", (event) => {
        if (
            sidebar?.classList.contains("is-open") &&
            !sidebar.contains(event.target) &&
            !sidebarToggle?.contains(event.target)
        ) {
            sidebar.classList.remove("is-open");
            sidebarToggle?.setAttribute("aria-expanded", "false");
        }
    });

    document.querySelector("[data-restaurant-toggle]")?.addEventListener("change", (event) => {
        const label = event.currentTarget.checked ? "Open" : "Closed";
        const statusChip = document.querySelector(".restaurant-panel .status-chip");
        const featureTitle = document.querySelector(".status-feature strong");
        const featureDescription = document.querySelector(".status-feature small");
        if (statusChip && featureTitle && featureDescription) {
            statusChip.className = `status-chip ${event.currentTarget.checked ? "status-open" : "status-offline"}`;
            statusChip.innerHTML = `<i></i> ${label}`;
            featureTitle.textContent = event.currentTarget.checked ? "Open for service" : "Temporarily closed";
            featureDescription.textContent = event.currentTarget.checked ? "Status is active in this demo view" : "Reopen any time in this demo";
        }
        showToast(`Restaurant marked ${label.toLowerCase()} in this preview.`);
    });

    const orderRows = Array.from(document.querySelectorAll("[data-order-row]"));
    const orderSearch = document.getElementById("orderSearch");
    const orderStatusFilter = document.getElementById("orderStatusFilter");
    const ordersEmpty = document.getElementById("ordersEmpty");
    const ordersShown = document.getElementById("ordersShown");

    const filterOrders = () => {
        if (!orderSearch || !orderStatusFilter) {
            return;
        }
        const query = orderSearch.value.trim().toLowerCase();
        const status = orderStatusFilter.value.toLowerCase();
        let visible = 0;
        orderRows.forEach((row) => {
            const matchesQuery = row.dataset.search.toLowerCase().includes(query);
            const matchesStatus = status === "all" || row.dataset.status.toLowerCase() === status;
            row.hidden = !matchesQuery || !matchesStatus;
            if (!row.hidden) {
                visible += 1;
            }
        });
        if (ordersEmpty) {
            ordersEmpty.hidden = visible !== 0;
        }
        if (ordersShown) {
            ordersShown.textContent = String(visible);
        }
    };
    orderSearch?.addEventListener("input", filterOrders);
    orderStatusFilter?.addEventListener("change", filterOrders);

    const statusClass = (status) => ({
        "Order Placed": "status-order-placed",
        Accepted: "status-accepted",
        Pending: "status-pending",
        Preparing: "status-preparing",
        Ready: "status-ready",
        "Robot Delivery": "status-robot-delivery",
        Delivered: "status-delivered",
        Completed: "status-completed",
        Cancelled: "status-cancelled",
        Failed: "status-failed",
    }[status] || "status-offline");

    const statusOptions = [
        "Order Placed",
        "Accepted",
        "Preparing",
        "Ready",
        "Robot Delivery",
        "Delivered",
        "Completed",
        "Cancelled",
        "Failed",
    ];
    const nextOrderStatuses = {
        "Order Placed": ["Accepted", "Cancelled", "Failed"],
        Accepted: ["Preparing", "Cancelled", "Failed"],
        Preparing: ["Ready", "Cancelled", "Failed"],
        Ready: ["Cancelled", "Failed"],
        "Robot Delivery": ["Failed"],
        "Received by Flask demo": ["Order Placed", "Accepted", "Cancelled", "Failed"],
    };

    const updateOrderStatus = async (row, status) => {
        if (row.dataset.orderSource === "firestore") {
            try {
                const response = await fetch(`/api/admin/orders/${encodeURIComponent(row.dataset.orderId)}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json", Accept: "application/json" },
                    body: JSON.stringify({
                        status,
                        revision: Number(row.dataset.revision)
                    })
                });
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.error || "Could not update the Firestore order.");
                }
                row.dataset.revision = String(result.order.revision);
            } catch (error) {
                showToast(error.message);
                return false;
            }
        }
        row.dataset.status = status;
        const cell = row.querySelector(".status-chip");
        if (cell) {
            cell.className = `status-chip ${statusClass(status)}`;
            cell.textContent = status;
        }
        filterOrders();
        showToast(row.dataset.orderSource === "firestore"
            ? `${row.dataset.orderId} status saved to Firestore.`
            : `${row.dataset.orderId} updated in the sample view.`);
        return true;
    };

    document.addEventListener("click", (event) => {
        const detailButton = event.target.closest("[data-order-details]");
        if (detailButton) {
            const row = orderRows.find((candidate) => candidate.dataset.orderId === detailButton.dataset.orderDetails);
            if (row) {
                const cells = row.cells;
                const items = Array.from(cells[2].querySelectorAll("small"))
                    .map((item) => item.textContent.trim());
                const itemDescription = items.length ? items.join(", ") : cells[2].firstChild.textContent.trim();
                const detail = document.createElement("div");
                detail.className = "detail-list";
                [
                    ["Order", `#${row.dataset.orderId}`],
                    ["Customer", cells[1].childNodes[0].textContent.trim()],
                    ["Phone", cells[1].querySelector("small")?.textContent || "Masked sample number"],
                    ["Table", cells[3].textContent.trim()],
                    ["Items", itemDescription],
                    ["Total", cells[4].textContent.trim()],
                    ["Order time", cells[5].textContent.trim()],
                    ["Status", row.dataset.status],
                    ["Assigned robot", cells[7].querySelector("select")?.value || cells[7].textContent.trim()],
                ].forEach(([label, value]) => {
                    const block = document.createElement("div");
                    const title = document.createElement("span");
                    const text = document.createElement("strong");
                    title.textContent = label;
                    text.textContent = value;
                    block.append(title, text);
                    detail.append(block);
                });
                openDialog("Order details", detail);
            }
            return;
        }

        const updateButton = event.target.closest("[data-order-edit]");
        if (updateButton) {
            const row = orderRows.find((candidate) => candidate.dataset.orderId === updateButton.dataset.orderEdit);
            if (row) {
                const form = document.createElement("div");
                form.className = "status-edit";
                const label = document.createElement("label");
                label.textContent = `Choose a new status for #${row.dataset.orderId}`;
                const select = document.createElement("select");
                select.setAttribute("aria-label", "New order status");
                const availableStatuses = row.dataset.orderSource === "firestore"
                    ? nextOrderStatuses[row.dataset.status] || [row.dataset.status]
                    : statusOptions;
                availableStatuses.forEach((status) => {
                    const option = document.createElement("option");
                    option.value = status;
                    option.textContent = status;
                    option.selected = row.dataset.status === status;
                    select.append(option);
                });
                const save = document.createElement("button");
                save.className = "button-primary";
                save.type = "button";
                save.textContent = "Save status";
                save.addEventListener("click", async () => {
                    save.disabled = true;
                    if (await updateOrderStatus(row, select.value)) dialog.close();
                    save.disabled = false;
                });
                form.append(label, select, save);
                openDialog("Update order status", form);
            }
            return;
        }

        const cancelButton = event.target.closest("[data-order-cancel]");
        if (cancelButton) {
            const row = orderRows.find((candidate) => candidate.dataset.orderId === cancelButton.dataset.orderCancel);
            const confirmation = row?.dataset.orderSource === "firestore"
                ? `Cancel Firestore order #${row.dataset.orderId}?`
                : `Cancel sample order #${row?.dataset.orderId}? This changes only the sample view.`;
            if (row && window.confirm(confirmation)) {
                void updateOrderStatus(row, "Cancelled");
            }
            return;
        }

        const menuEditButton = event.target.closest(".menu-edit");
        if (menuEditButton) {
            openMenuEditor(menuEditButton.closest("[data-menu-item]"));
            return;
        }

        const menuToggleButton = event.target.closest(".menu-toggle");
        if (menuToggleButton) {
            const card = menuToggleButton.closest("[data-menu-item]");
            void setMenuAvailability(card, card.dataset.available !== "true");
            return;
        }

        const menuDeleteButton = event.target.closest(".menu-delete");
        if (menuDeleteButton) {
            const card = menuDeleteButton.closest("[data-menu-item]");
            if (card) void deleteMenuItem(card);
            return;
        }

        const robotAction = event.target.closest("[data-robot-action]");
        if (robotAction) {
            handleRobotAction(robotAction);
            return;
        }

        const customerHistoryButton = event.target.closest("[data-customer-id]");
        if (customerHistoryButton) {
            const customer = customerHistoryById.get(customerHistoryButton.dataset.customerId);
            if (!customer) {
                showToast("Customer history is not available. Refresh the page and try again.");
                return;
            }
            const details = document.createElement("div");
            const heading = document.createElement("p");
            heading.textContent = `Order history for ${customer.name}`;
            const info = document.createElement("div");
            info.className = "detail-list";
            [
                ["Masked phone", customer.phone],
                ["Total orders", String(customer.order_count)],
                ["Total spending", formatCurrency(customer.total_spending)],
            ].forEach(([title, value]) => {
                const block = document.createElement("div");
                const label = document.createElement("span");
                const text = document.createElement("strong");
                label.textContent = title;
                text.textContent = value;
                block.append(label, text);
                info.append(block);
            });
            details.append(heading, info);
            const historyHeading = document.createElement("h3");
            historyHeading.textContent = "Orders";
            details.append(historyHeading);
            const orderList = document.createElement("ul");
            customer.orders_history.forEach((order) => {
                const item = document.createElement("li");
                const time = order.created_at
                    ? formatDate(order.created_at)
                    : "Time unavailable";
                const table = order.table_number
                    ? ` · Table ${order.table_number}`
                    : "";
                const itemNames = order.items
                    .map((orderedItem) => `${orderedItem.quantity} × ${orderedItem.name}`)
                    .join(", ");
                item.textContent = `#${order.id} · ${time}${table} · ${formatCurrency(order.total)}${itemNames ? ` · ${itemNames}` : ""}`;
                orderList.append(item);
            });
            details.append(orderList);
            openDialog("Customer order history", details);
        }

        const qrButton = event.target.closest("[data-view-qr]");
        if (qrButton) {
            const tableCard = qrButton.closest("[data-table-card]");
            const number = qrButton.dataset.viewQr;
            const imageUrl = tableCard?.dataset.qrImage;
            const menuUrl = tableCard?.dataset.qrUrl;
            if (!imageUrl || !menuUrl) {
                showToast("Configure a phone-reachable CUSTOMER_QR_BASE_URL to generate this QR code.");
                return;
            }
            const preview = document.createElement("div");
            preview.className = "qr-dialog-preview";
            const qr = document.createElement("img");
            qr.className = "table-qr-image";
            qr.src = imageUrl;
            qr.alt = `Real customer menu QR code for Table ${number}`;
            const note = document.createElement("p");
            note.textContent = `Table ${number} customer menu`;
            const link = document.createElement("a");
            link.href = menuUrl;
            link.target = "_blank";
            link.rel = "noopener";
            link.textContent = menuUrl;
            preview.append(qr, note, link);
            openDialog(`Table ${number} QR preview`, preview);
            return;
        }

        const printButton = event.target.closest("[data-print-qr]");
        if (printButton) {
            const tableCard = printButton.closest("[data-table-card]");
            const number = printButton.dataset.printQr;
            const imageUrl = tableCard?.dataset.qrImage;
            const menuUrl = tableCard?.dataset.qrUrl;
            if (!imageUrl || !menuUrl) {
                showToast("Configure a phone-reachable CUSTOMER_QR_BASE_URL to generate this QR code.");
                return;
            }
            const printWindow = window.open("", "_blank", "width=420,height=520");
            if (!printWindow) {
                showToast("Allow pop-ups to open the table QR print preview.");
                return;
            }
            const document = printWindow.document;
            document.title = `Table ${number} customer menu QR`;
            const style = document.createElement("style");
            style.textContent = "body{font:16px Arial,sans-serif;text-align:center;padding:32px;color:#173d32}img{display:block;width:240px;height:240px;margin:24px auto}a{overflow-wrap:anywhere;color:#315e49}";
            const heading = document.createElement("h1");
            heading.textContent = `Table ${number}`;
            const image = document.createElement("img");
            image.alt = `Customer menu QR code for Table ${number}`;
            const link = document.createElement("a");
            link.href = menuUrl;
            link.textContent = menuUrl;
            document.head.append(style);
            document.body.replaceChildren(heading, image, link);
            image.addEventListener("load", () => {
                printWindow.focus();
                printWindow.print();
            }, { once: true });
            image.addEventListener("error", () => {
                printWindow.close();
                showToast("Could not load the table QR image for printing.");
            }, { once: true });
            image.src = imageUrl;
        }
    });

    const customerSearch = document.getElementById("customerSearch");
    const customersEmpty = document.getElementById("customersEmpty");
    const customerRowsBody = document.getElementById("customerRows");
    const customersLoading = document.getElementById("customersLoading");
    const customerDataStatus = document.getElementById("customerDataStatus");
    const customerCurrency = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
    });
    const formatCurrency = (amount) => customerCurrency.format(Number(amount) || 0);
    const formatDate = (value) => {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
    };

    const filterCustomerRows = () => {
        if (!customerRowsBody || !customerSearch) {
            return;
        }
        const query = customerSearch.value.trim().toLowerCase();
        let visible = 0;
        customerRowsBody.querySelectorAll("[data-customer-row]").forEach((row) => {
            row.hidden = !row.dataset.customerSearch.includes(query);
            if (!row.hidden) {
                visible += 1;
            }
        });
        if (customersEmpty) {
            customersEmpty.hidden = visible !== 0;
            const message = customersEmpty.querySelector(".empty-state span");
            if (message) {
                message.textContent = query
                    ? "Try searching for another name or phone number."
                    : "New customer orders will appear here.";
            }
        }
    };
    customerSearch?.addEventListener("input", filterCustomerRows);

    const renderCustomers = (customers) => {
        if (!customerRowsBody || !customersEmpty || !customersLoading) {
            throw new Error("The customer dashboard table is unavailable.");
        }
        customerRowsBody.querySelectorAll("[data-customer-row]").forEach((row) => row.remove());
        customerHistoryById.clear();
        customersLoading.hidden = true;

        customers.forEach((customer, index) => {
            customerHistoryById.set(customer.id, customer);
            const row = document.createElement("tr");
            row.dataset.customerRow = "";
            row.dataset.customerSearch = `${customer.name} ${customer.phone}`.toLowerCase();

            const identityCell = document.createElement("td");
            const identity = document.createElement("span");
            identity.className = "customer-identity";
            const avatar = document.createElement("span");
            avatar.className = `customer-avatar ${["avatar-peach", "avatar-blue", "avatar-lilac", "avatar-mint"][index % 4]}`;
            avatar.textContent = customer.name
                .split(/\s+/)
                .filter(Boolean)
                .slice(0, 2)
                .map((part) => part[0])
                .join("")
                .toUpperCase();
            const name = document.createElement("strong");
            name.textContent = customer.name;
            identity.append(avatar, name);
            identityCell.append(identity);

            const phoneCell = document.createElement("td");
            phoneCell.textContent = customer.phone;
            const ordersCell = document.createElement("td");
            const orderCount = document.createElement("strong");
            orderCount.textContent = String(customer.order_count);
            ordersCell.append(orderCount);
            const spendingCell = document.createElement("td");
            const spending = document.createElement("strong");
            spending.textContent = formatCurrency(customer.total_spending);
            spendingCell.append(spending);
            const lastOrderCell = document.createElement("td");
            lastOrderCell.textContent = customer.last_order_at
                ? formatDate(customer.last_order_at)
                : "Time unavailable";
            const historyCell = document.createElement("td");
            const historyButton = document.createElement("button");
            historyButton.className = "action-button";
            historyButton.type = "button";
            historyButton.dataset.customerId = customer.id;
            historyButton.textContent = "View history";
            historyCell.append(historyButton);

            row.append(
                identityCell,
                phoneCell,
                ordersCell,
                spendingCell,
                lastOrderCell,
                historyCell,
            );
            customerRowsBody.insertBefore(row, customersEmpty);
        });
        filterCustomerRows();
    };

    const updateCustomerSummary = (summary) => {
        document.getElementById("customerTotal").textContent = String(summary.total_customers);
        document.getElementById("customerReturning").textContent = `${summary.returning_rate_percent}%`;
        document.getElementById("customerAverageSpend").textContent = formatCurrency(summary.average_order_spend);
        document.getElementById("customerNewThisWeek").textContent = String(summary.new_customers_this_week);
    };

    let customerRefreshPending = false;
    let hasCustomerData = false;
    const refreshCustomers = async () => {
        if (customerRefreshPending || document.hidden) {
            return;
        }
        customerRefreshPending = true;
        try {
            const response = await fetch("/api/admin/customers", {
                cache: "no-store",
                credentials: "same-origin",
            });
            if (response.status === 401 || response.status === 403) {
                window.location.assign("/admin-login?next=%2Fadmin%2Fcustomers");
                return;
            }
            if (!response.ok) {
                throw new Error("Customer data request failed.");
            }
            const result = await response.json();
            if (!result.success || !Array.isArray(result.customers) || !result.summary) {
                throw new Error("Customer data response was invalid.");
            }
            updateCustomerSummary(result.summary);
            renderCustomers(result.customers);
            hasCustomerData = true;
            if (customerDataStatus) {
                customerDataStatus.textContent = `Updated ${formatDate(result.updated_at)}`;
            }
        } catch {
            if (customerDataStatus) {
                customerDataStatus.textContent = hasCustomerData
                    ? "Refresh failed · showing the last successful data"
                    : "Customer data is temporarily unavailable";
            }
            if (customersLoading && !hasCustomerData) {
                customersLoading.hidden = true;
                customersEmpty.hidden = false;
                const message = customersEmpty.querySelector(".empty-state span");
                if (message) {
                    message.textContent = "Check the server connection, then wait for the next update.";
                }
            }
        } finally {
            customerRefreshPending = false;
        }
    };
    if (customerRowsBody) {
        refreshCustomers();
        const customerRefreshTimer = window.setInterval(refreshCustomers, 15_000);
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) {
                refreshCustomers();
            }
        });
        window.addEventListener("pagehide", () => window.clearInterval(customerRefreshTimer), { once: true });
    }

    document.querySelector("[data-admin-logout]")?.addEventListener("click", async (event) => {
        event.preventDefault();
        try {
            const response = await fetch("/api/admin/session", {
                method: "DELETE",
                credentials: "same-origin",
            });
            if (!response.ok) {
                throw new Error("Sign-out request failed.");
            }
            window.location.assign("/admin-login");
        } catch {
            showToast("Could not sign out. Check the connection and try again.");
        }
    });

    const menuGrid = document.getElementById("menuGrid");
    const menuDialog = document.getElementById("menuDialog");
    const menuForm = document.getElementById("menuForm");
    const menuSearch = document.getElementById("menuSearch");
    const menuCategoryFilter = document.getElementById("menuCategoryFilter");
    const menuEmpty = document.getElementById("menuEmpty");
    const menuCount = document.getElementById("menuCount");
    const menuLoadMessage = document.getElementById("menuLoadMessage");
    let menuItems = [];
    const menuInputs = {
        name: document.getElementById("menuItemName"),
        description: document.getElementById("menuItemDescription"),
        category: document.getElementById("menuItemCategory"),
        price: document.getElementById("menuItemPrice"),
        image: document.getElementById("menuItemImage"),
        available: document.getElementById("menuItemAvailable"),
    };

    const setMenuAvailability = async (card, available) => {
        const item = menuItemsById.get(card?.dataset.menuItemId);
        if (!item) return;
        try {
            const response = await fetch(`/api/admin/menu/${encodeURIComponent(item.id)}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({ ...item, available }),
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Could not update menu availability.");
            }
            await loadMenuItems();
            showToast(`${item.name} marked ${available ? "available" : "unavailable"}.`);
        } catch (error) {
            showToast(error.message || "Could not update menu availability.");
        }
    };

    const menuCardElements = () => Array.from(document.querySelectorAll("[data-menu-item]"));

    const filterMenu = () => {
        if (!menuSearch || !menuCategoryFilter) {
            return;
        }
        const query = menuSearch.value.trim().toLowerCase();
        const category = menuCategoryFilter.value;
        let visible = 0;
        menuCardElements().forEach((card) => {
            const text = `${card.dataset.name} ${card.dataset.description} ${card.dataset.category}`.toLowerCase();
            const matches = text.includes(query) && (category === "all" || card.dataset.category === category);
            card.hidden = !matches;
            if (matches) {
                visible += 1;
            }
        });
        if (menuEmpty) {
            menuEmpty.hidden = visible !== 0;
        }
    };
    menuSearch?.addEventListener("input", filterMenu);
    menuCategoryFilter?.addEventListener("change", filterMenu);

    const safeImageUrl = (value) => {
        if (!value) {
            return "";
        }
        try {
            const source = value.startsWith("uploads/")
                ? `/static/${value.split("/").map(encodeURIComponent).join("/")}`
                : value;
            const url = new URL(source, window.location.href);
            return ["http:", "https:"].includes(url.protocol) ? url.href : "";
        } catch {
            return "";
        }
    };

    const foodNameSlug = (name) => name.normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "") || "food-item";
    const imageMatchesMenuName = (image, name) => {
        const filename = image.split("/").pop()?.replace(/\.(?:jpg|jpeg|png|webp)$/i, "") || "";
        const slug = foodNameSlug(name);
        return filename === slug || filename.startsWith(`${slug}-`);
    };
    const updateMenuImageRequirement = () => {
        menuInputs.image.required = menuInputs.available.checked
            && !imageMatchesMenuName(editingMenuItem?.image || "", menuInputs.name.value.trim());
    };

    const openMenuEditor = (card = null) => {
        if (!menuDialog || !menuForm) {
            showToast("Menu editor is not available on this page.");
            return;
        }
        editingMenuItem = card ? menuItemsById.get(card.dataset.menuItemId) || null : null;
        document.getElementById("menuDialogTitle").textContent = editingMenuItem ? "Edit menu item" : "Add menu item";
        menuInputs.name.value = editingMenuItem?.name || "";
        menuInputs.description.value = editingMenuItem?.description || "";
        menuInputs.category.value = editingMenuItem?.category || "";
        menuInputs.price.value = editingMenuItem?.price ?? "";
        menuInputs.image.value = "";
        menuInputs.available.checked = editingMenuItem ? editingMenuItem.available : true;
        updateMenuImageRequirement();
        const preview = document.getElementById("menuItemImagePreview");
        const previewUrl = safeImageUrl(editingMenuItem?.image || "");
        preview.src = previewUrl;
        preview.hidden = !previewUrl;
        document.getElementById("menuImageHelp").textContent = previewUrl
            ? `Current image: ${editingMenuItem.image}. Choose a photo with a filename matching the food name.`
            : "Choose an item-specific photo. It is saved with a filename based on the food name.";
        menuDialog.showModal();
        menuInputs.name.focus();
    };

    document.getElementById("addMenuItem")?.addEventListener("click", () => openMenuEditor());
    menuInputs.name?.addEventListener("input", updateMenuImageRequirement);
    menuInputs.available?.addEventListener("change", updateMenuImageRequirement);
    document.querySelectorAll("[data-menu-close]").forEach((button) => {
        button.addEventListener("click", () => menuDialog?.close());
    });
    menuDialog?.addEventListener("click", (event) => {
        if (event.target === menuDialog) {
            menuDialog.close();
        }
    });

    const createMenuCard = ({ id, name, description, category, price, image, available }) => {
        const card = document.createElement("article");
        card.className = "menu-card";
        card.dataset.menuItem = "";
        card.dataset.menuItemId = id;
        card.dataset.name = name;
        card.dataset.category = category;
        card.dataset.description = description;
        card.dataset.price = String(price);
        card.dataset.available = String(available);

        const photo = document.createElement("div");
        photo.className = "food-image";
        const url = safeImageUrl(image);
        if (url) {
            photo.style.setProperty("--food-image", `url("${url.replaceAll('"', "%22")}")`);
        } else {
            photo.classList.add("food-image--placeholder");
        }
        const categoryLabel = document.createElement("span");
        categoryLabel.className = "category-label";
        categoryLabel.textContent = category;
        photo.append(categoryLabel);

        const body = document.createElement("div");
        body.className = "menu-card__body";
        const descriptionWrap = document.createElement("div");
        const title = document.createElement("h2");
        title.textContent = name;
        const detail = document.createElement("p");
        detail.textContent = description || "Freshly prepared for your guests";
        descriptionWrap.append(title, detail);
        const meta = document.createElement("div");
        meta.className = "menu-card__meta";
        const amount = document.createElement("strong");
        amount.textContent = `$${Number(price).toFixed(2)}`;
        const availability = document.createElement("span");
        availability.className = `availability ${available ? "available" : "unavailable"}`;
        availability.innerHTML = `<i></i> ${available ? "Available" : "Unavailable"}`;
        meta.append(amount, availability);
        const actions = document.createElement("div");
        actions.className = "menu-card__actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "button-secondary menu-edit";
        edit.textContent = "Edit";
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "button-tertiary menu-toggle";
        toggle.textContent = `Mark ${available ? "unavailable" : "available"}`;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button menu-delete";
        remove.setAttribute("aria-label", `Delete ${name}`);
        remove.textContent = "×";
        actions.append(edit, toggle, remove);
        body.append(descriptionWrap, meta, actions);
        card.append(photo, body);
        return card;
    };

    const loadMenuItems = async () => {
        if (!menuGrid) return;
        const response = await fetch("/api/admin/menu", {
            headers: { Accept: "application/json" },
            cache: "no-store",
        });
        const result = await response.json();
        if (!response.ok || !result.success || !Array.isArray(result.items)) {
            throw new Error(result.error || "Could not load the Firestore menu.");
        }
        menuItems = result.items;
        menuItemsById.clear();
        menuItems.forEach((item) => menuItemsById.set(item.id, item));
        menuGrid.replaceChildren(...menuItems.map(createMenuCard));
        const selectedCategory = menuCategoryFilter.value;
        menuCategoryFilter.replaceChildren(new Option("All categories", "all"));
        [...new Set(menuItems.map((item) => item.category))]
            .sort((left, right) => left.localeCompare(right))
            .forEach((category) => menuCategoryFilter.add(new Option(category, category)));
        if ([...menuCategoryFilter.options].some((option) => option.value === selectedCategory)) {
            menuCategoryFilter.value = selectedCategory;
        }
        if (menuCount) menuCount.textContent = `${menuItems.length} menu items`;
        if (menuLoadMessage) {
            menuLoadMessage.textContent = "";
            menuLoadMessage.hidden = true;
        }
        filterMenu();
    };

    const deleteMenuItem = async (card) => {
        const item = menuItemsById.get(card.dataset.menuItemId);
        if (!item || !window.confirm(`Delete "${item.name}" from the Firestore menu?`)) return;
        try {
            const response = await fetch(`/api/admin/menu/${encodeURIComponent(item.id)}`, {
                method: "DELETE",
                headers: { Accept: "application/json" },
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Could not delete this menu item.");
            }
            await loadMenuItems();
            showToast(`${item.name} deleted from the menu.`);
        } catch (error) {
            showToast(error.message || "Could not delete this menu item.");
        }
    };

    const uploadMenuImage = async (file, name) => {
        const formData = new FormData();
        formData.append("image", file);
        formData.append("name", name);
        const response = await fetch("/api/admin/menu-images", {
            method: "POST",
            body: formData,
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Could not upload the food image.");
        }
        return result.image;
    };

    menuInputs.image?.addEventListener("change", () => {
        const file = menuInputs.image.files[0];
        const preview = document.getElementById("menuItemImagePreview");
        if (!file) {
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            menuInputs.image.value = "";
            showToast("Images must be 5 MB or smaller.");
            return;
        }
        preview.src = URL.createObjectURL(file);
        preview.hidden = false;
        document.getElementById("menuImageHelp").textContent = file.name;
    });

    menuForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!menuForm.reportValidity()) {
            return;
        }
        const item = {
            name: menuInputs.name.value.trim(),
            description: menuInputs.description.value.trim(),
            category: menuInputs.category.value.trim(),
            price: Number(menuInputs.price.value),
            image: editingMenuItem?.image || "",
            available: menuInputs.available.checked,
        };
        if (!item.name || !Number.isFinite(item.price) || item.price <= 0) {
            showToast("Enter an item name and a valid price.");
            return;
        }
        const saveButton = menuForm.querySelector('button[type="submit"]');
        saveButton.disabled = true;
        try {
            const file = menuInputs.image.files[0];
            if (file) item.image = await uploadMenuImage(file, item.name);
            const endpoint = editingMenuItem
                ? `/api/admin/menu/${encodeURIComponent(editingMenuItem.id)}`
                : "/api/admin/menu";
            const response = await fetch(endpoint, {
                method: editingMenuItem ? "PUT" : "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify(item),
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Could not save this menu item.");
            }
            await loadMenuItems();
            menuDialog.close();
            showToast(`${item.name} saved to the Firestore menu.`);
        } catch (error) {
            showToast(error.message || "Could not save this menu item.");
        } finally {
            saveButton.disabled = false;
        }
    });

    loadMenuItems().catch((error) => {
        if (menuLoadMessage) {
            menuLoadMessage.textContent = error.message || "Could not load the Firestore menu.";
            menuLoadMessage.hidden = false;
        }
        if (menuCount) menuCount.textContent = "Menu unavailable";
    });

    const robotCards = Array.from(document.querySelectorAll("[data-robot-card]"));
    const handleRobotAction = (button) => {
        const card = button.closest("[data-robot-card]");
        const name = card?.dataset.robotName;
        const action = button.dataset.robotAction;
        if (!card || card.dataset.robotStatus === "Offline") {
            showToast("This demo robot is offline and unavailable.");
            return;
        }

        if (action === "pause") {
            const task = card.querySelector("[data-current-task]");
            const state = card.querySelector(".robot-state");
            const isPaused = card.dataset.robotStatus === "Paused";
            card.dataset.robotStatus = isPaused ? "Idle" : "Paused";
            if (task) {
                task.textContent = isPaused ? "Waiting for assignment" : "Paused by admin";
            }
            if (state) {
                state.textContent = isPaused ? "Idle & available" : "Paused";
                state.className = `robot-state ${isPaused ? "state-idle" : "state-offline"}`;
            }
            button.textContent = isPaused ? "Pause" : "Resume";
            showToast(`${name} ${isPaused ? "resumed" : "paused"} in the demo.`);
            return;
        }

        if (action === "charge") {
            card.dataset.robotStatus = "Charging";
            const task = card.querySelector("[data-current-task]");
            const assigned = card.querySelector("[data-assigned-order]");
            const state = card.querySelector(".robot-state");
            if (task) task.textContent = "Returning to charging station";
            if (assigned) assigned.textContent = "None";
            if (state) {
                state.textContent = "Charging";
                state.className = "robot-state state-charging";
            }
            showToast(`${name} is returning to the demo charging station.`);
            return;
        }

        if (action === "assign") {
            const assignable = ["VD-2046", "VD-2042"];
            const form = document.createElement("div");
            form.className = "status-edit";
            const label = document.createElement("label");
            label.textContent = "Select an unassigned sample order";
            const select = document.createElement("select");
            select.setAttribute("aria-label", "Select sample order");
            assignable.forEach((orderId) => {
                const option = document.createElement("option");
                option.value = orderId;
                option.textContent = `#${orderId}`;
                select.append(option);
            });
            const confirm = document.createElement("button");
            confirm.className = "button-primary";
            confirm.type = "button";
            confirm.textContent = "Assign to robot";
            confirm.addEventListener("click", () => {
                const assigned = card.querySelector("[data-assigned-order]");
                const task = card.querySelector("[data-current-task]");
                const state = card.querySelector(".robot-state");
                if (assigned) assigned.textContent = `#${select.value}`;
                if (task) task.textContent = "Delivering sample order";
                if (state) {
                    state.textContent = "Delivering";
                    state.className = "robot-state state-delivering";
                }
                card.dataset.robotStatus = "Delivering";
                showToast(`#${select.value} assigned to ${name} in the demo.`);
                dialog.close();
            });
            form.append(label, select, confirm);
            openDialog("Assign a sample order", form);
            return;
        }

        if (action === "history" || button.hasAttribute("data-history-all")) {
            const history = document.createElement("div");
            history.innerHTML = "<p><strong>Today · Sample task history</strong></p><ul><li>Order delivery to Table 05 · Completed at 12:29 PM</li><li>Order delivery to Table 02 · Completed at 12:20 PM</li><li>Returned to service area · Completed at 11:54 AM</li></ul><small>History is illustrative and not connected to robot telemetry.</small>";
            openDialog(`${name || "Fleet"} task history`, history);
        }
    };
    document.querySelector("[data-history-all]")?.addEventListener("click", (event) => {
        event.preventDefault();
        const historyButton = document.createElement("button");
        historyButton.dataset.robotAction = "history";
        handleRobotAction(historyButton);
    });

    const settingsForm = document.getElementById("settingsForm");
    let settingsSnapshot = "";
    if (settingsForm) {
        settingsSnapshot = new URLSearchParams(new FormData(settingsForm)).toString();
        settingsForm.addEventListener("change", (event) => {
            if (event.target.name === "restaurantOpen") {
                const label = document.querySelector("[data-status-label]");
                if (label) {
                    label.textContent = event.target.checked ? "Open for service" : "Temporarily closed";
                }
            }
        });
        settingsForm.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!settingsForm.reportValidity()) {
                return;
            }
            showToast("Settings updated in this preview only; nothing was saved to a server.");
        });
        document.getElementById("cancelSettings")?.addEventListener("click", () => {
            const values = new URLSearchParams(settingsSnapshot);
            Array.from(settingsForm.elements).forEach((field) => {
                if (!field.name) {
                    return;
                }
                if (field.type === "checkbox") {
                    field.checked = values.getAll(field.name).includes("on");
                } else {
                    field.value = values.get(field.name) || "";
                }
            });
            const statusLabel = document.querySelector("[data-status-label]");
            if (statusLabel) {
                statusLabel.textContent = settingsForm.elements.restaurantOpen.checked
                    ? "Open for service"
                    : "Temporarily closed";
            }
            showToast("Unsaved form changes were cancelled.");
        });
        document.querySelectorAll(".settings-nav a").forEach((link) => {
            link.addEventListener("click", () => {
                document.querySelectorAll(".settings-nav a").forEach((item) => item.classList.remove("active"));
                link.classList.add("active");
            });
        });
    }

    document.querySelectorAll('a[href="#"]').forEach((link) => {
        link.addEventListener("click", (event) => event.preventDefault());
    });
})();
