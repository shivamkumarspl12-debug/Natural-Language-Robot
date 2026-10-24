(() => {
    "use strict";

    const loginForm = document.getElementById("loginForm");
    const loginButton = document.getElementById("loginButton");
    const loginNotice = document.getElementById("loginNotice");
    const emailInput = document.getElementById("adminIdentity");
    const passwordInput = document.getElementById("adminPassword");
    const passwordToggle = document.getElementById("passwordToggle");
    const firebaseConfig = window.firebaseAuthConfig;
    const localAdminLoginEnabled = window.localAdminLoginEnabled === true;
    const adminNextPath = window.adminNextPath || "/admin";

    if (
        !loginForm || !loginButton || !loginNotice ||
        (!localAdminLoginEnabled && !emailInput) ||
        !passwordInput || !passwordToggle || !firebaseConfig
    ) {
        throw new Error("Admin login page is missing required authentication elements.");
    }

    const setLoading = (loading) => {
        loginButton.classList.toggle("is-loading", loading);
        loginButton.disabled = loading;
        loginButton.setAttribute("aria-busy", String(loading));
    };

    const showError = (message) => {
        loginNotice.textContent = message;
        loginNotice.hidden = false;
    };

    passwordToggle.addEventListener("click", () => {
        const showPassword = passwordInput.type === "password";
        passwordInput.type = showPassword ? "text" : "password";
        passwordToggle.setAttribute("aria-pressed", String(showPassword));
        passwordToggle.setAttribute("aria-label", showPassword ? "Hide password" : "Show password");
        passwordInput.focus();
    });

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        loginNotice.textContent = "";
        loginNotice.hidden = true;

        if (!localAdminLoginEnabled && !loginForm.reportValidity()) {
            return;
        }

        if (!localAdminLoginEnabled && !firebaseConfig.apiKey) {
            showError("Firebase web sign-in is not configured. Set FIREBASE_API_KEY and restart Flask.");
            return;
        }

        setLoading(true);
        try {
            if (localAdminLoginEnabled) {
                const localSessionResponse = await fetch("/api/admin/local-session", {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ password: passwordInput.value }),
                });
                const localSessionResult = await localSessionResponse.json();
                if (!localSessionResponse.ok || !localSessionResult.success) {
                    throw new Error(localSessionResult.error || "Local sign-in failed.");
                }
                window.location.assign(adminNextPath);
                return;
            }

            const signInResponse = await fetch(
                `${firebaseConfig.signInUrl}?key=${encodeURIComponent(firebaseConfig.apiKey)}`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        email: emailInput.value.trim(),
                        password: passwordInput.value,
                        returnSecureToken: true,
                    }),
                },
            );
            const signInResult = await signInResponse.json();
            if (!signInResponse.ok || !signInResult.idToken) {
                const errorCode = signInResult.error?.message || "";
                if (errorCode === "TOO_MANY_ATTEMPTS_TRY_LATER") {
                    throw new Error("Too many sign-in attempts. Wait a little and try again.");
                }
                if (errorCode === "OPERATION_NOT_ALLOWED") {
                    throw new Error("Enable Email/Password sign-in in Firebase Authentication.");
                }
                if (errorCode === "API_KEY_INVALID") {
                    throw new Error("Firebase sign-in configuration is invalid. Check FIREBASE_API_KEY.");
                }
                throw new Error("Email or password is incorrect, or this Firebase account is unavailable.");
            }

            const sessionResponse = await fetch("/api/admin/session", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ idToken: signInResult.idToken }),
            });
            const sessionResult = await sessionResponse.json();
            if (!sessionResponse.ok || !sessionResult.success) {
                throw new Error(sessionResult.error || "This account is not authorized for the admin portal.");
            }
            window.location.assign(adminNextPath);
        } catch (error) {
            showError(error instanceof Error
                ? error.message
                : "Sign-in failed. Check your connection and try again.");
        } finally {
            setLoading(false);
            passwordInput.value = "";
        }
    });
})();
