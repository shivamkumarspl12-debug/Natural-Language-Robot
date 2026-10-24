(() => {
    "use strict";

    const CART_KEY = "verdantCustomerCartV1";
    const ORDER_KEY = "verdantCustomerDemoOrderV1";
    const ORDERS_KEY = "verdantCustomerOrdersV1";
    const IDEMPOTENCY_KEY = "verdantCustomerPendingOrderKeyV1";
    const ACCESS_TOKEN_KEY = "verdantCustomerPendingAccessTokenV1";
    const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
    const tableFromTemplate = document.body.dataset.tableNumber;
    const tableFromQuery = new URLSearchParams(window.location.search).get("table");
    const tableCandidate = /^([1-6])$/.test(tableFromTemplate || "") ? tableFromTemplate : tableFromQuery;
    const currentTable = /^[1-6]$/.test(tableCandidate || "") ? Number(tableCandidate) : null;
    const customerRoutes = {
        customer_menu: "/customer/menu",
        customer_cart: "/customer/cart",
        customer_checkout: "/customer/checkout",
        customer_my_orders: "/customer/my-orders",
        customer_order_status: "/customer/order-status",
        customer_robot_tracking: "/customer/robot-tracking"
    };
    let pendingAccessToken = null;
    let pendingCheckoutIdempotencyKey = null;

    const getCheckoutIdempotencyKey = () => {
        try {
            let key = sessionStorage.getItem(IDEMPOTENCY_KEY);
            if (!key) {
                if (!window.crypto?.getRandomValues) {
                    throw new Error("Secure random key generation is unavailable.");
                }
                key = Array.from(
                    window.crypto.getRandomValues(new Uint8Array(16)),
                    (value) => value.toString(16).padStart(2, "0")
                ).join("");
                pendingCheckoutIdempotencyKey = key;
                sessionStorage.setItem(IDEMPOTENCY_KEY, key);
            }
            return key;
        } catch {
            if (!pendingCheckoutIdempotencyKey) {
                if (!window.crypto?.getRandomValues) {
                    throw new Error("Secure random key generation is unavailable.");
                }
                pendingCheckoutIdempotencyKey = Array.from(
                    window.crypto.getRandomValues(new Uint8Array(16)),
                    (value) => value.toString(16).padStart(2, "0")
                ).join("");
            }
            return pendingCheckoutIdempotencyKey;
        }
    };

    const clearCheckoutIdempotencyKey = () => {
        pendingCheckoutIdempotencyKey = null;
        try {
            sessionStorage.removeItem(IDEMPOTENCY_KEY);
            sessionStorage.removeItem(ACCESS_TOKEN_KEY);
        } catch {
            return;
        }
    };
    const getCheckoutAccessToken = () => {
        try {
            let token = sessionStorage.getItem(ACCESS_TOKEN_KEY);
            if (!token) {
                if (!window.crypto?.getRandomValues) {
                    throw new Error("Secure random token generation is unavailable.");
                }
                const bytes = window.crypto.getRandomValues(new Uint8Array(32));
                token = btoa(String.fromCharCode(...bytes))
                    .replace(/\+/g, "-")
                    .replace(/\//g, "_")
                    .replace(/=+$/, "");
                sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
            }
            return token;
        } catch (error) {
            if (!pendingAccessToken) {
                if (!window.crypto?.getRandomValues) throw error;
                const bytes = window.crypto.getRandomValues(new Uint8Array(32));
                pendingAccessToken = btoa(String.fromCharCode(...bytes))
                    .replace(/\+/g, "-")
                    .replace(/\//g, "_")
                    .replace(/=+$/, "");
            }
            return pendingAccessToken;
        }
    };
    let products = [
        { id: "garden-margherita", name: "Garden Margherita", category: "Pizza", description: "Slow tomato, basil, fior di latte", price: 18.5, image: "", available: true, tag: "Guest favorite" },
        { id: "woodland-mushroom-pizza", name: "Woodland Mushroom", category: "Pizza", description: "Wild mushrooms, thyme, aged mozzarella", price: 21, image: "", available: true, tag: "Wood-fired" },
        { id: "verdant-smash", name: "Verdant Smash Burger", category: "Burgers", description: "Grass-fed beef, sharp cheddar, garden pickle", price: 17.5, image: "", available: true, tag: "House pick" },
        { id: "crispy-garden-burger", name: "Crispy Garden Burger", category: "Burgers", description: "Crispy chickpea patty, herb yogurt, greens", price: 15, image: "", available: true, tag: "Plant based" },
        { id: "truffle-linguine", name: "Truffle Mushroom Linguine", category: "Pasta", description: "Silky parmesan cream, wild mushroom, herbs", price: 23.5, image: "", available: true, tag: "Kitchen favorite" },
        { id: "lemon-pappardelle", name: "Lemon Garden Pappardelle", category: "Pasta", description: "Fresh lemon, peas, basil, pecorino", price: 19, image: "", available: true, tag: "Seasonal" },
        { id: "whipped-ricotta", name: "Whipped Ricotta Toast", category: "Starters", description: "Grilled sourdough, honey, garden herbs", price: 10, image: "", available: true, tag: "To share" },
        { id: "crispy-polenta", name: "Crispy Polenta Bites", category: "Starters", description: "Golden polenta, tomato relish, parmesan", price: 9.5, image: "", available: true, tag: "Vegetarian" },
        { id: "olive-oil-cake", name: "Lemon Olive Oil Cake", category: "Desserts", description: "Whipped mascarpone, seasonal berries", price: 9, image: "", available: true, tag: "A sweet finish" },
        { id: "dark-chocolate-mousse", name: "Dark Chocolate Mousse", category: "Desserts", description: "70% cacao, sea salt, hazelnut crumble", price: 10.5, image: "", available: false, tag: "Temporarily unavailable" },
        { id: "garden-spritz", name: "Garden Citrus Spritz", category: "Drinks", description: "Blood orange, rosemary, sparkling water", price: 7.5, image: "", available: true, tag: "Zero proof" },
        { id: "iced-matcha", name: "Iced Matcha Cloud", category: "Drinks", description: "Stone-ground matcha, oat milk, soft foam", price: 6.5, image: "", available: true, tag: "Chilled" }
    ];
    const productById = new Map(products.map((product) => [product.id, product]));
    let toastTimer;
    let selectedCategory = "All";
    let searchTerm = "";
    let menuSnapshotKey = "";
    let menuRequestInFlight = false;
    let menuControlsBound = false;
    let checkoutSubmitting = false;

    const customerUrl = (page, orderId = "") => {
        const params = new URLSearchParams();
        if (currentTable) params.set("table", String(currentTable));
        if (orderId) params.set("order_id", orderId);
        const query = params.toString();
        return `${customerRoutes[page]}${query ? `?${query}` : ""}`;
    };

    const applyCustomerNavigation = () => {
        const menuToggle = document.getElementById("customerMenuToggle");
        const customerNav = document.getElementById("customerNav");
        menuToggle?.addEventListener("click", () => {
            const isOpen = customerNav.classList.toggle("is-open");
            menuToggle.setAttribute("aria-expanded", String(isOpen));
            menuToggle.setAttribute("aria-label", isOpen ? "Close navigation menu" : "Open navigation menu");
        });
        customerNav?.addEventListener("click", (event) => {
            if (event.target.closest("a")) {
                customerNav.classList.remove("is-open");
                menuToggle?.setAttribute("aria-expanded", "false");
                menuToggle?.setAttribute("aria-label", "Open navigation menu");
            }
        });
        const context = document.getElementById("customerTableContext");
        if (context && currentTable) {
            context.hidden = false;
            document.getElementById("customerTableLabel").textContent = `Table ${currentTable}`;
        }
        const checkoutTableLabel = document.getElementById("checkoutTableLabel");
        if (checkoutTableLabel && currentTable) checkoutTableLabel.textContent = `Table ${currentTable}`;
    };

    const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);

    const readStorage = (key, fallback) => {
        try {
            const value = localStorage.getItem(key);
            return value ? JSON.parse(value) : fallback;
        } catch {
            return fallback;
        }
    };

    const writeStorage = (key, value) => {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch {
            return false;
        }
    };

    const getCart = () => {
        const saved = readStorage(CART_KEY, {});
        return saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    };

    const cartEntries = () => Object.entries(getCart())
        .map(([id, quantity]) => ({ product: productById.get(id), quantity: Number(quantity) }))
        .filter((entry) => entry.product && Number.isInteger(entry.quantity) && entry.quantity > 0);

    const cartCount = () => cartEntries().reduce((total, entry) => total + entry.quantity, 0);
    const cartTotal = () => Math.round(cartEntries().reduce((total, entry) => total + entry.product.price * entry.quantity, 0) * 100) / 100;

    const updateHeaderCart = () => {
        const count = cartCount();
        document.querySelectorAll("[data-cart-count]").forEach((node) => { node.textContent = String(count); });
        document.querySelectorAll(".header-cart").forEach((link) => {
            link.setAttribute("aria-label", `View cart, ${count} ${count === 1 ? "item" : "items"}`);
        });
    };

    const showToast = (message, isError = false) => {
        const toast = document.getElementById("customerToast");
        if (!toast) return;
        toast.textContent = message;
        toast.classList.toggle("is-error", isError);
        toast.hidden = false;
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => { toast.hidden = true; }, 2800);
    };

    const foodNameSlug = (name) => name.normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "") || "food-item";

    const updateCart = (id, quantity) => {
        const product = productById.get(id);
        if (!product || (quantity > 0 && !product.available)) return false;
        const cart = getCart();
        if (quantity <= 0) delete cart[id];
        else cart[id] = Math.min(99, Math.floor(quantity));
        const saved = writeStorage(CART_KEY, cart);
        updateHeaderCart();
        return saved;
    };

    const renderMenu = () => {
        const grid = document.getElementById("menuGrid");
        if (!grid) return;
        const categoryRow = document.querySelector(".category-row");

        const paint = () => {
            const matches = products.filter((product) => {
                const categoryMatches = selectedCategory === "All" || product.category === selectedCategory;
                const text = `${product.name} ${product.description} ${product.category}`.toLowerCase();
                return categoryMatches && text.includes(searchTerm);
            });
            grid.innerHTML = matches.map((product) => `
                <article class="food-card${product.available ? "" : " is-unavailable"}" data-product-card="${product.id}">
                    <div class="food-image-wrap">
                        ${product.image ? `<img class="food-image" src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}" loading="lazy">` : `<div class="food-image food-image--placeholder" role="img" aria-label="${escapeHtml(product.name)} photo unavailable"><span>Photo unavailable</span></div>`}
                        <span class="food-tag${product.available ? "" : " unavailable-tag"}">${escapeHtml(product.available ? product.tag : "Unavailable")}</span>
                    </div>
                    <div class="food-body">
                        <p class="food-category">${escapeHtml(product.category)}</p>
                        <div class="food-title-row"><h3>${escapeHtml(product.name)}</h3><span class="food-price">${currency.format(product.price)}</span></div>
                        <p class="food-description">${escapeHtml(product.description)}</p>
                        <div class="food-card-footer">
                            ${product.available ? `<div class="quantity-control" aria-label="Quantity for ${escapeHtml(product.name)}"><button type="button" data-menu-quantity="-1" aria-label="Decrease quantity">−</button><output data-menu-quantity-value>1</output><button type="button" data-menu-quantity="1" aria-label="Increase quantity">+</button></div><button class="add-button" type="button" data-add-product="${escapeHtml(product.id)}"><span aria-hidden="true">＋</span> Add</button>` : `<button class="add-button" type="button" disabled aria-disabled="true">Unavailable</button>`}
                        </div>
                    </div>
                </article>`).join("");
            grid.querySelectorAll("img.food-image").forEach((image) => {
                image.addEventListener("error", () => {
                    const placeholder = document.createElement("div");
                    placeholder.className = "food-image food-image--placeholder";
                    placeholder.setAttribute("role", "img");
                    placeholder.setAttribute("aria-label", `${image.alt} photo unavailable`);
                    placeholder.textContent = "Photo unavailable";
                    image.replaceWith(placeholder);
                }, { once: true });
            });
            document.getElementById("menuEmpty").hidden = matches.length > 0;
            const allCount = document.getElementById("menuAllCount");
            if (allCount) allCount.textContent = String(products.length);
        };

        products.forEach((product) => {
            if (categoryRow.querySelector(`[data-category-filter="${CSS.escape(product.category)}"]`)) return;
            const button = document.createElement("button");
            button.className = "category-chip";
            button.type = "button";
            button.dataset.categoryFilter = product.category;
            button.setAttribute("aria-pressed", "false");
            button.textContent = product.category;
            categoryRow.append(button);
        });
        if (!products.some((product) => product.category === selectedCategory)) {
            selectedCategory = "All";
        }
        document.querySelectorAll("[data-category-filter]").forEach((button) => {
            const selected = button.dataset.categoryFilter === selectedCategory;
            button.classList.toggle("is-selected", selected);
            button.setAttribute("aria-pressed", String(selected));
        });

        if (!menuControlsBound) {
            categoryRow.addEventListener("click", (event) => {
                const button = event.target.closest("[data-category-filter]");
                if (!button) return;
                selectedCategory = button.dataset.categoryFilter;
                document.querySelectorAll("[data-category-filter]").forEach((chip) => {
                    const selected = chip === button;
                    chip.classList.toggle("is-selected", selected);
                    chip.setAttribute("aria-pressed", String(selected));
                });
                paint();
            });
            document.getElementById("menuSearch").addEventListener("input", (event) => {
                searchTerm = event.target.value.trim().toLowerCase();
                paint();
            });

            document.getElementById("clearMenuFilters").addEventListener("click", () => {
                selectedCategory = "All";
                searchTerm = "";
                document.getElementById("menuSearch").value = "";
                document.querySelector('[data-category-filter="All"]').click();
            });

            grid.addEventListener("click", (event) => {
                const card = event.target.closest("[data-product-card]");
                if (!card) return;
                const quantityOutput = card.querySelector("[data-menu-quantity-value]");
                const quantityButton = event.target.closest("[data-menu-quantity]");
                if (quantityButton && quantityOutput) {
                    quantityOutput.value = String(Math.max(1, Math.min(99, Number(quantityOutput.value || quantityOutput.textContent) + Number(quantityButton.dataset.menuQuantity))));
                    quantityOutput.textContent = quantityOutput.value;
                    return;
                }
                const addButton = event.target.closest("[data-add-product]");
                if (addButton) {
                    const quantity = Number(quantityOutput.value || quantityOutput.textContent || 1);
                    if (!updateCart(addButton.dataset.addProduct, quantity)) {
                        showToast("Cart storage is unavailable in this browser. Use a local web server for the demo.", true);
                        return;
                    }
                    showToast(`${quantity} × ${productById.get(addButton.dataset.addProduct).name} added to your cart.`);
                }
            });
            menuControlsBound = true;
        }

        paint();
    };

    const applyMenuSnapshot = (items) => {
        const nextSnapshotKey = JSON.stringify(items);
        if (nextSnapshotKey === menuSnapshotKey) return;

        const nextProducts = items.map((item) => {
            const previousProduct = productById.get(item.id);
            const relativeImage = typeof item.image === "string" ? item.image : "";
            const imageFilename = relativeImage.match(/^uploads\/([A-Za-z0-9][A-Za-z0-9_.-]*)\.(?:jpg|jpeg|png|webp)$/i)?.[1] || "";
            const expectedImageSlug = foodNameSlug(item.name);
            const imageMatchesName = imageFilename === expectedImageSlug
                || imageFilename.startsWith(`${expectedImageSlug}-`);
            const image = imageMatchesName
                ? `/static/${relativeImage.split("/").map(encodeURIComponent).join("/")}`
                : "";
            return {
                id: item.id,
                name: item.name,
                category: item.category,
                description: item.description || "",
                price: Number(item.price),
                image,
                available: item.available === true,
                tag: previousProduct?.tag || item.category,
            };
        });
        const nextIds = new Set(nextProducts.map((product) => product.id));
        const cart = getCart();
        const removedIds = Object.keys(cart).filter((id) => !nextIds.has(id));
        if (removedIds.length) {
            removedIds.forEach((id) => delete cart[id]);
            writeStorage(CART_KEY, cart);
        }

        products = nextProducts;
        productById.clear();
        products.forEach((product) => productById.set(product.id, product));
        menuSnapshotKey = nextSnapshotKey;
        renderMenu();
        renderCart();
        renderCheckout();
        updateHeaderCart();
        if (removedIds.length) {
            showToast("Your cart was updated because a menu item was removed.", true);
        }
    };

    const refreshCustomerMenu = async () => {
        if (menuRequestInFlight || document.hidden) return;
        menuRequestInFlight = true;
        try {
            const response = await fetch("/api/customer/menu", {
                headers: { Accept: "application/json" },
                cache: "no-store",
            });
            const result = await response.json();
            if (!response.ok || !result.success || !Array.isArray(result.items)) {
                throw new Error(result.error || "The menu could not be refreshed.");
            }
            applyMenuSnapshot(result.items);
            const feedback = document.getElementById("menuFeedback");
            if (feedback) {
                feedback.textContent = "";
                feedback.hidden = true;
            }
        } catch (error) {
            const feedback = document.getElementById("menuFeedback");
            if (feedback) {
                feedback.textContent = error.message || "The menu could not be refreshed.";
                feedback.hidden = false;
            }
        } finally {
            menuRequestInFlight = false;
        }
    };

    const renderCart = () => {
        const itemsNode = document.getElementById("cartItems");
        if (!itemsNode) return;
        const entries = cartEntries();
        const empty = entries.length === 0;
        document.getElementById("cartContent").hidden = empty;
        document.getElementById("cartEmpty").hidden = !empty;
        if (empty) return;

        itemsNode.innerHTML = entries.map(({ product, quantity }) => `
            <article class="cart-item${product.available ? "" : " is-unavailable"}" data-cart-item="${escapeHtml(product.id)}">
                ${product.image ? `<img class="cart-item-image" src="${escapeHtml(product.image)}" alt="${escapeHtml(product.name)}">` : `<span class="cart-item-image" role="img" aria-label="${escapeHtml(product.name)}"></span>`}
                <div class="cart-item-info"><h3>${escapeHtml(product.name)}</h3><p>${currency.format(product.price)} each</p><div class="cart-item-tools">
                    ${product.available ? `<div class="quantity-control" aria-label="Quantity for ${escapeHtml(product.name)}"><button type="button" data-cart-change="-1" aria-label="Decrease quantity">−</button><output>${quantity}</output><button type="button" data-cart-change="1" aria-label="Increase quantity">+</button></div>` : `<strong class="cart-item-unavailable">Unavailable · remove before ordering</strong>`}
                    <button class="remove-item" type="button" data-remove-item>Remove</button>
                </div></div><strong class="cart-item-price">${currency.format(product.price * quantity)}</strong>
            </article>`).join("");
        const total = cartTotal();
        document.getElementById("cartItemHeading").textContent = `${cartCount()} ${cartCount() === 1 ? "item" : "items"}`;
        document.getElementById("cartSubtotal").textContent = currency.format(total);
        document.getElementById("cartTotal").textContent = currency.format(total);
    };

    const renderCheckout = () => {
        const content = document.getElementById("checkoutContent");
        if (!content) return;
        const entries = cartEntries();
        const empty = entries.length === 0;
        content.hidden = empty;
        document.getElementById("checkoutEmpty").hidden = !empty;
        if (empty) return;
        document.getElementById("checkoutItems").innerHTML = entries.map(({ product, quantity }) => `
            <div class="checkout-item${product.available ? "" : " is-unavailable"}">${product.image ? `<img src="${escapeHtml(product.image)}" alt="">` : `<span class="checkout-item-placeholder" aria-hidden="true"></span>`}<span><strong>${escapeHtml(product.name)}</strong><small>Qty ${quantity} · ${currency.format(product.price)} each${product.available ? "" : " · unavailable"}</small></span><span>${currency.format(product.price * quantity)}</span></div>`).join("");
        const total = currency.format(cartTotal());
        document.getElementById("checkoutSubtotal").textContent = total;
        document.getElementById("checkoutTotal").textContent = total;
        const unavailable = entries.some(({ product }) => !product.available);
        const unavailableMessage = document.getElementById("checkoutAvailabilityError");
        if (unavailableMessage) unavailableMessage.hidden = !unavailable;
        const submitButton = document.querySelector('#checkoutForm button[type="submit"]');
        if (submitButton) submitButton.disabled = unavailable;
    };

    const setFieldError = (input, errorNode, message) => {
        input.setAttribute("aria-invalid", String(Boolean(message)));
        errorNode.textContent = message;
        errorNode.hidden = !message;
    };

    const getOrderReferences = () => {
        const saved = readStorage(ORDERS_KEY, []);
        return Array.isArray(saved)
            ? saved.filter((entry) => entry && typeof entry.id === "string" && typeof entry.accessToken === "string")
            : [];
    };

    const saveOrderReference = (order, accessToken) => {
        const references = getOrderReferences().filter((entry) => entry.id !== order.id);
        references.unshift({ id: order.id, accessToken, order });
        return writeStorage(ORDERS_KEY, references.slice(0, 50)) && writeStorage(ORDER_KEY, order);
    };

    const orderReference = (orderId) => getOrderReferences().find((entry) => entry.id === orderId);

    const fetchAuthorizedOrder = async (reference) => {
        const response = await fetch(
            `/api/customer/orders/${encodeURIComponent(reference.id)}`,
            {
                headers: {
                    Accept: "application/json",
                    "X-Order-Access-Token": reference.accessToken
                }
            }
        );
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Could not refresh this order.");
        }
        const backendOrder = result.order;
        const order = {
            ...backendOrder,
            customerName: backendOrder.customer_name,
            table: `Table ${backendOrder.table_number}`,
            items: backendOrder.items.map((item) => ({
                ...item,
                image: productById.get(item.id)?.image || ""
            }))
        };
        saveOrderReference(order, reference.accessToken);
        return order;
    };

    let currentStatusOrder = null;
    let currentStatusReference = null;
    let robotTrackingRequest = null;

    const renderCustomerRobotTracking = (tracking) => {
        const panel = document.getElementById("customerRobotTracking");
        if (!panel) return;
        panel.hidden = !tracking?.simulated
            || !["Ready", "Robot Delivery", "Delivered"].includes(tracking.status);
        if (panel.hidden) return;

        document.getElementById("customerRobotMessage").textContent =
            tracking.message || "Waiting for delivery updates.";
        const table = document.getElementById("customerRobotTable");
        table.textContent = tracking.destination_table
            ? `TABLE ${tracking.destination_table}`
            : "TABLE";

        const marker = document.getElementById("customerRobotMarker");
        const position = tracking.position;
        marker.hidden = !position
            || !Number.isFinite(position.x)
            || !Number.isFinite(position.z);
        if (!marker.hidden) {
            const left = 12 + ((position.x + 11) / 31) * 76;
            const top = 15 + ((12 - position.z) / 24) * 70;
            marker.style.left = `${Math.max(8, Math.min(92, left))}%`;
            marker.style.top = `${Math.max(12, Math.min(88, top))}%`;
        }
        document.getElementById("customerRobotUpdated").textContent =
            position?.updated_at
                ? `Last simulated position update: ${new Date(position.updated_at).toLocaleTimeString()}`
                : "Waiting for the admin simulation to start this delivery.";
        document.getElementById("customerRobotError").hidden = true;
    };

    const refreshCustomerRobotTracking = async () => {
        if (
            !currentStatusOrder
            || !currentStatusReference
            || document.hidden
            || robotTrackingRequest
        ) return;
        robotTrackingRequest = (async () => {
            try {
                const response = await fetch(
                    `/api/customer/orders/${encodeURIComponent(currentStatusOrder.id)}/tracking`,
                    {
                        headers: {
                            Accept: "application/json",
                            "X-Order-Access-Token": currentStatusReference.accessToken
                        }
                    }
                );
                const contentType = response.headers.get("content-type") || "";
                if (!contentType.includes("application/json")) {
                    throw new Error(`Tracking returned an unexpected response (HTTP ${response.status}).`);
                }
                const result = await response.json();
                if (!response.ok || !result.success) {
                    throw new Error(result.error || "Could not refresh robot tracking.");
                }
                renderCustomerRobotTracking(result.tracking);
            } catch (error) {
                const errorNode = document.getElementById("customerRobotError");
                if (errorNode) {
                    errorNode.textContent = "Live robot tracking is temporarily unavailable.";
                    errorNode.hidden = false;
                }
            } finally {
                robotTrackingRequest = null;
            }
        })();
        await robotTrackingRequest;
    };

    const renderStatusOrder = (order) => {
        document.getElementById("orderConfirmation").hidden = false;
        document.getElementById("orderStatusContent").hidden = false;
        document.getElementById("statusEmpty").hidden = true;
        document.getElementById("confirmationName").textContent = order.customerName;
        document.getElementById("orderId").textContent = order.id;
        document.getElementById("statusCustomer").textContent = order.customerName;
        document.getElementById("statusTable").textContent = order.table || "Not assigned";
        document.getElementById("statusItems").innerHTML = order.items.map((item) => `<div class="status-item"><span>${escapeHtml(item.quantity)} × ${escapeHtml(item.name)}</span><strong>${currency.format(item.price * item.quantity)}</strong></div>`).join("");
        document.getElementById("statusTotal").textContent = currency.format(order.total);
        document.getElementById("statusValue").textContent = order.status;
        document.getElementById("statusCurrent").textContent = `${order.status} · refreshed from Firestore`;
        document.getElementById("statusCreated").textContent = order.created_at
            ? new Date(order.created_at).toLocaleString()
            : "Unavailable";
        const trackingLink = document.getElementById("openRobotTracking");
        if (trackingLink && currentStatusReference) {
            trackingLink.href = customerUrl(
                "customer_robot_tracking",
                order.id
            );
        }

        const stages = ["Order Placed", "Accepted", "Preparing", "Ready", "Robot Delivery", "Delivered"];
        const statusIndex = stages.indexOf(order.status);
        document.getElementById("statusTimeline").innerHTML = stages.map((stage, index) => {
            const complete = statusIndex >= 0 && index < statusIndex;
            const current = index === statusIndex;
            const classes = `timeline-step${complete ? " is-complete" : ""}${current ? " is-current" : ""}`;
            return `<li class="${classes}"${current ? ' aria-current="step"' : ""}><span class="timeline-dot">${complete || current ? "✓" : String(index + 1).padStart(2, "0")}</span><span>${stage}</span></li>`;
        }).join("");
        const terminalStatus = ["Cancelled", "Failed"].includes(order.status);
        const terminalMessage = document.getElementById("statusTerminal");
        terminalMessage.hidden = !terminalStatus;
        terminalMessage.textContent = terminalStatus ? `Order ${order.status.toLowerCase()}.` : "";
        const deliveredMessage = document.getElementById("statusDelivered");
        if (deliveredMessage) {
            deliveredMessage.hidden = order.status !== "Delivered";
        }

        const actions = document.getElementById("orderActions");
        const editable = order.status === "Order Placed";
        const cancellable = ["Order Placed", "Accepted"].includes(order.status);
        actions.hidden = !editable && !cancellable;
        document.getElementById("editOrderButton").hidden = !editable;
        document.getElementById("cancelOrderButton").hidden = !cancellable;
        document.getElementById("orderEditPanel").hidden = true;
        void refreshCustomerRobotTracking();
    };

    const renderOrderStatus = async () => {
        const content = document.getElementById("orderStatusContent");
        if (!content) return;
        const requestedOrderId = new URLSearchParams(window.location.search).get("order_id");
        const reference = requestedOrderId
            ? orderReference(requestedOrderId)
            : orderReference(readStorage(ORDER_KEY, {})?.id);
        if (!reference) {
            currentStatusOrder = null;
            currentStatusReference = null;
            document.getElementById("orderConfirmation").hidden = true;
            content.hidden = true;
            document.getElementById("statusEmpty").hidden = false;
            document.getElementById("customerRobotTracking").hidden = true;
            return;
        }
        currentStatusReference = reference;
        try {
            currentStatusOrder = await fetchAuthorizedOrder(reference);
            renderStatusOrder(currentStatusOrder);
        } catch (error) {
            showToast(error.message);
            if (!currentStatusOrder) {
                document.getElementById("orderConfirmation").hidden = true;
                content.hidden = true;
                document.getElementById("statusEmpty").hidden = false;
            }
        }
    };

    const renderMyOrders = async () => {
        const list = document.getElementById("myOrdersList");
        if (!list) return;
        const references = getOrderReferences();
        if (!references.length) {
            list.replaceChildren();
            document.getElementById("myOrdersEmpty").hidden = false;
            return;
        }
        document.getElementById("myOrdersEmpty").hidden = true;
        const cards = await Promise.all(references.map(async (reference) => {
            try {
                const order = await fetchAuthorizedOrder(reference);
                const card = document.createElement("article");
                card.className = "order-card";
                const itemSummary = order.items
                    .map((item) => `${item.quantity} × ${item.name}`)
                    .join(", ");
                card.innerHTML = `<div class="order-card-top"><div><span class="eyebrow">ORDER</span><h2>${escapeHtml(order.id)}</h2></div><strong class="order-card-status">${escapeHtml(order.status)}</strong></div><p>${escapeHtml(itemSummary)}</p><div class="order-card-meta"><span>Table ${escapeHtml(order.table_number)}</span><strong>${currency.format(order.total)}</strong><time>${order.created_at ? escapeHtml(new Date(order.created_at).toLocaleString()) : "Time unavailable"}</time></div><a class="button button-light" href="${escapeHtml(customerUrl("customer_order_status", order.id))}">View status and manage order <span aria-hidden="true">→</span></a><a class="button button-light" href="${escapeHtml(customerUrl("customer_robot_tracking", order.id))}">View 3D robot tracking <span aria-hidden="true">→</span></a>`;
                if (order.status === "Delivered") {
                    const thankYou = document.createElement("p");
                    thankYou.className = "order-delivered-message";
                    thankYou.textContent = "Thank you for your order!";
                    card.prepend(thankYou);
                }
                return card;
            } catch (error) {
                const card = document.createElement("article");
                card.className = "order-card order-card-error";
                card.textContent = `${reference.id}: ${error.message}`;
                return card;
            }
        }));
        list.replaceChildren(...cards);
    };

    const renderOrderEditForm = () => {
        if (!currentStatusOrder) return;
        const quantities = new Map(currentStatusOrder.items.map((item) => [item.id, item.quantity]));
        const rows = products.filter((product) => product.available).map((product) => `
            <label class="edit-order-item"><span>${escapeHtml(product.name)} <small>${currency.format(product.price)}</small></span><input class="customer-input" type="number" min="0" max="99" step="1" value="${quantities.get(product.id) || 0}" data-product-quantity="${escapeHtml(product.id)}" aria-label="Quantity of ${escapeHtml(product.name)}"></label>
        `).join("");
        document.getElementById("editOrderItems").innerHTML = rows;
        document.getElementById("orderEditPanel").hidden = false;
    };

    const bindOrderActions = () => {
        document.getElementById("editOrderButton")?.addEventListener("click", renderOrderEditForm);
        document.getElementById("saveOrderChanges")?.addEventListener("click", async (event) => {
            if (!currentStatusOrder || !currentStatusReference) return;
            const items = Array.from(document.querySelectorAll("[data-product-quantity]"))
                .map((input) => ({ id: input.dataset.productQuantity, quantity: Number(input.value) }))
                .filter((item) => Number.isInteger(item.quantity) && item.quantity > 0);
            if (!items.length) {
                showToast("Keep at least one item in the order.");
                return;
            }
            const button = event.currentTarget;
            button.disabled = true;
            try {
                const response = await fetch(`/api/customer/orders/${encodeURIComponent(currentStatusOrder.id)}`, {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json",
                        Accept: "application/json",
                        "X-Order-Access-Token": currentStatusReference.accessToken
                    },
                    body: JSON.stringify({ items, revision: currentStatusOrder.revision })
                });
                const result = await response.json();
                if (!response.ok || !result.success) throw new Error(result.error || "Could not update the order.");
                currentStatusOrder = {
                    ...result.order,
                    customerName: result.order.customer_name,
                    table: `Table ${result.order.table_number}`
                };
                saveOrderReference(currentStatusOrder, currentStatusReference.accessToken);
                renderStatusOrder(currentStatusOrder);
                showToast("Order changes saved.");
            } catch (error) {
                showToast(error.message);
            } finally {
                button.disabled = false;
            }
        });
        document.getElementById("cancelOrderButton")?.addEventListener("click", async () => {
            if (!currentStatusOrder || !currentStatusReference || !window.confirm("Cancel this order?")) return;
            try {
                const response = await fetch(`/api/customer/orders/${encodeURIComponent(currentStatusOrder.id)}`, {
                    method: "DELETE",
                    headers: {
                        "Content-Type": "application/json",
                        Accept: "application/json",
                        "X-Order-Access-Token": currentStatusReference.accessToken
                    },
                    body: JSON.stringify({ revision: currentStatusOrder.revision })
                });
                const result = await response.json();
                if (!response.ok || !result.success) throw new Error(result.error || "Could not cancel the order.");
                currentStatusOrder = {
                    ...result.order,
                    customerName: result.order.customer_name,
                    table: `Table ${result.order.table_number}`
                };
                saveOrderReference(currentStatusOrder, currentStatusReference.accessToken);
                renderStatusOrder(currentStatusOrder);
                showToast("Order cancelled.");
            } catch (error) {
                showToast(error.message);
            }
        });
    };

    const bindCartControls = () => {
        const itemsNode = document.getElementById("cartItems");
        if (!itemsNode) return;
        itemsNode.addEventListener("click", (event) => {
            const row = event.target.closest("[data-cart-item]");
            if (!row) return;
            const id = row.dataset.cartItem;
            const current = Number(getCart()[id] || 0);
            const change = event.target.closest("[data-cart-change]");
            if (change) {
                updateCart(id, current + Number(change.dataset.cartChange));
                renderCart();
                return;
            }
            if (event.target.closest("[data-remove-item]")) {
                updateCart(id, 0);
                renderCart();
                showToast("Item removed from your cart.");
            }
        });
        document.getElementById("proceedCheckout").addEventListener("click", () => {
            if (!cartEntries().length) {
                document.getElementById("cartMessage").textContent = "Add an item before continuing to checkout.";
                document.getElementById("cartMessage").hidden = false;
                return;
            }
            window.location.href = customerUrl("customer_checkout");
        });
    };

    const bindCheckout = () => {
        const form = document.getElementById("checkoutForm");
        if (!form) return;
        const nameInput = document.getElementById("customerName");
        const phoneInput = document.getElementById("customerPhone");
        const nameError = document.getElementById("nameError");
        const phoneError = document.getElementById("phoneError");
        const checkoutError = document.getElementById("checkoutError");

        nameInput.addEventListener("input", () => setFieldError(nameInput, nameError, ""));
        phoneInput.addEventListener("input", () => setFieldError(phoneInput, phoneError, ""));

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (checkoutSubmitting) return;
            const customerName = nameInput.value.trim().replace(/\s+/g, " ");
            const customerPhone = phoneInput.value.trim();
            const phoneDigits = customerPhone.replace(/\D/g, "");
            let firstInvalid = null;
            setFieldError(nameInput, nameError, "");
            setFieldError(phoneInput, phoneError, "");
            checkoutError.hidden = true;

            if (customerName.length < 2) {
                setFieldError(nameInput, nameError, "Enter your full name (at least 2 characters).");
                firstInvalid = nameInput;
            }
            if (phoneDigits.length < 10 || phoneDigits.length > 15) {
                setFieldError(phoneInput, phoneError, "Enter a valid mobile number with 10–15 digits.");
                firstInvalid = firstInvalid || phoneInput;
            }
            const entries = cartEntries();
            if (!entries.length) {
                checkoutError.textContent = "Your cart is empty. Return to the menu and add an item first.";
                checkoutError.hidden = false;
                firstInvalid = firstInvalid || nameInput;
            } else if (entries.some(({ product }) => !product.available)) {
                checkoutError.textContent = "Your cart contains an unavailable item. Remove it before placing the order.";
                checkoutError.hidden = false;
                firstInvalid = firstInvalid || nameInput;
            }
            if (!currentTable) {
                checkoutError.textContent = "A valid table QR link is required to place this dine-in demo order.";
                checkoutError.hidden = false;
                firstInvalid = firstInvalid || nameInput;
            }
            if (firstInvalid) {
                firstInvalid.focus();
                return;
            }

            const submitButton = form.querySelector('button[type="submit"]');
            checkoutSubmitting = true;
            submitButton.disabled = true;
            checkoutError.hidden = true;
            let response;
            let result;
            try {
                const accessToken = getCheckoutAccessToken();
                response = await fetch("/api/customer/orders", {
                    method: "POST",
                    mode: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        Accept: "application/json",
                        "Idempotency-Key": getCheckoutIdempotencyKey(),
                        "X-Order-Access-Token": accessToken
                    },
                    body: JSON.stringify({
                        customer_name: customerName,
                        customer_phone: customerPhone,
                        table_number: currentTable,
                        items: entries.map(({ product, quantity }) => ({ id: product.id, quantity }))
                    })
                });
                if (!(response.headers.get("content-type") || "")
                    .includes("application/json")) {
                    throw new Error(
                        `The server returned an unexpected response (HTTP ${response.status}). `
                        + "Use the secure HTTPS customer address and try again."
                    );
                }
                result = await response.json();
            } catch (error) {
                checkoutSubmitting = false;
                submitButton.disabled = false;
                checkoutError.textContent = error.message
                    || "Could not reach the Flask demo server. Check the secure connection and try again.";
                checkoutError.hidden = false;
                return;
            }

            if (!response.ok || !result.success) {
                checkoutSubmitting = false;
                submitButton.disabled = false;
                checkoutError.textContent = result.error || "Flask could not validate this demo order.";
                checkoutError.hidden = false;
                return;
            }

            const backendOrder = result.order;
            const order = {
                ...backendOrder,
                id: backendOrder.id,
                customerName: backendOrder.customer_name,
                table: `Table ${backendOrder.table_number}`,
                tableNumber: backendOrder.table_number,
                items: backendOrder.items.map((item) => ({
                    ...item,
                    image: productById.get(item.id)?.image || ""
                })),
                total: backendOrder.total,
                demoOnly: true
            };

            if (!saveOrderReference(order, result.access_token) || !writeStorage(CART_KEY, {})) {
                checkoutError.textContent =
                    `Order saved successfully. Order ID: ${order.id}. `
                    + "This browser could not save its private tracking link. Copy the order ID and contact the restaurant for help.";
                checkoutError.hidden = false;
                return;
            }
            clearCheckoutIdempotencyKey();
            checkoutError.textContent = `Order saved successfully. Order ID: ${order.id}. Opening your confirmation…`;
            checkoutError.classList.remove("field-error");
            checkoutError.classList.add("checkout-success");
            checkoutError.hidden = false;
            window.location.href = customerUrl("customer_order_status", order.id);
        });
    };

    applyCustomerNavigation();
    updateHeaderCart();
    renderMenu();
    renderCart();
    renderCheckout();
    bindCartControls();
    bindCheckout();
    bindOrderActions();
    renderOrderStatus();
    renderMyOrders();
    if (["menu", "cart", "checkout"].includes(document.body.dataset.customerPage)) {
        void refreshCustomerMenu();
        window.setInterval(refreshCustomerMenu, 15000);
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden) void refreshCustomerMenu();
        });
    }
    if (document.getElementById("orderStatusContent")) {
        window.setInterval(renderOrderStatus, 10000);
        let robotTrackingTimer = null;
        const updateRobotTrackingPolling = () => {
            if (document.hidden) {
                if (robotTrackingTimer !== null) {
                    window.clearInterval(robotTrackingTimer);
                    robotTrackingTimer = null;
                }
                return;
            }
            if (robotTrackingTimer === null) {
                void refreshCustomerRobotTracking();
                robotTrackingTimer = window.setInterval(
                    refreshCustomerRobotTracking,
                    5000
                );
            }
        };
        document.addEventListener("visibilitychange", updateRobotTrackingPolling);
        updateRobotTrackingPolling();
    }
    if (document.getElementById("myOrdersList")) {
        window.setInterval(renderMyOrders, 20000);
    }
})();