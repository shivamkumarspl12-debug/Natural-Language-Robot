// ============================================================
// AI RESTAURANT SERVICE ROBOT - FRONTEND
// Clean working version
// ============================================================

"use strict";

document.addEventListener("DOMContentLoaded", function () {

    const executeBtn = document.getElementById("executeBtn");
    const instructionInput = document.getElementById("instruction");
    const resultDiv = document.getElementById("result");
    const loadingDiv = document.getElementById("loading");

    console.log("AI Restaurant Robot frontend loaded.");

    if (!executeBtn) {
        console.error("executeBtn not found in index.html");
        return;
    }

    if (!instructionInput) {
        console.error("instruction input not found in index.html");
        return;
    }

    executeBtn.addEventListener("click", executeInstruction);

    async function executeInstruction() {

        const instruction = instructionInput.value.trim();

        if (!instruction) {
            alert("Please enter an instruction.");
            return;
        }

        if (loadingDiv) {
            loadingDiv.style.display = "block";
        }

        resultDiv.innerHTML = `
            <div class="result-card">
                <h2>🤖 Processing...</h2>
                <p>AI Restaurant Robot is processing:</p>
                <strong>${escapeHTML(instruction)}</strong>
            </div>
        `;

        try {

            console.log("Sending instruction:", instruction);

            const response = await fetch("/process", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    instruction: instruction
                })
            });

            if (response.status === 401) {
                window.location.assign("/admin-login?next=%2F");
                return;
            }

            const data = await response.json();

            console.log("Backend response:", data);

            if (!response.ok) {
                throw new Error(
                    data.error || "Backend returned an error."
                );
            }

            sessionStorage.setItem(
                "pipelineResult",
                JSON.stringify(data)
            );

            displayResult(data);

        } catch (error) {

            console.error("Robot error:", error);

            resultDiv.innerHTML = `
                <div class="result-card">
                    <h2>❌ Error</h2>
                    <p>${escapeHTML(error.message)}</p>
                    <p>
                        Check that Flask is running at
                        <strong>http://127.0.0.1:5000</strong>
                    </p>
                </div>
            `;

        } finally {

            if (loadingDiv) {
                loadingDiv.style.display = "none";
            }
        }
    }

    function displayResult(data) {

        const parser = data.parser || {};
        const decomposition = data.task_decomposition || [];
        const actions = data.action_sequence || [];
        const commands = data.robot_commands || [];
        const execution = data.checked_execution || [];
        const failure = data.failure_analysis || {};

        const intent =
            data.intent ||
            parser.intent ||
            "UNKNOWN";

        const item =
            data.item ||
            parser.item ||
            parser.object ||
            "N/A";

        const target =
            data.target ||
            parser.target ||
            "N/A";

        const quantity =
            data.quantity ||
            parser.quantity ||
            1;

        const status =
            data.overall_status ||
            "UNKNOWN";

        const success =
            status === "SUCCESS";

        // ----------------------------------------------------
        // TASK DECOMPOSITION
        // ----------------------------------------------------

        let decompositionHTML = "";

        if (decomposition.length === 0) {

            decompositionHTML =
                "<p>No task decomposition available.</p>";

        } else {

            decompositionHTML = "<ol>";

            decomposition.forEach(function (step) {

                decompositionHTML += `
                    <li>
                        <strong>
                            ${escapeHTML(step.task || "TASK")}
                        </strong>
                        -
                        ${escapeHTML(step.description || "")}
                    </li>
                `;

            });

            decompositionHTML += "</ol>";
        }

        // ----------------------------------------------------
        // ACTION SEQUENCE
        // ----------------------------------------------------

        let actionsHTML = "";

        if (actions.length === 0) {

            actionsHTML =
                "<p>No actions generated.</p>";

        } else {

            actionsHTML = "<ol>";

            actions.forEach(function (action) {

                actionsHTML += `
                    <li>
                        <strong>
                            ${escapeHTML(action.action || "UNKNOWN")}
                        </strong>

                        <small>
                            (${escapeHTML(
                                action.source_task || ""
                            )})
                        </small>
                    </li>
                `;

            });

            actionsHTML += "</ol>";
        }

        // ----------------------------------------------------
        // EXECUTION
        // ----------------------------------------------------

        let executionHTML = "";

        if (execution.length === 0) {

            executionHTML =
                "<p>No execution data available.</p>";

        } else {

            executionHTML = `
                <div class="table-container">

                    <table>

                        <thead>

                            <tr>
                                <th>Step</th>
                                <th>Command</th>
                                <th>Status</th>
                                <th>Attempts</th>
                                <th>Message</th>
                            </tr>

                        </thead>

                        <tbody>
            `;

            execution.forEach(function (row) {

                const ok =
                    row.success === true ||
                    row.status === "SUCCESS";

                executionHTML += `
                    <tr>

                        <td>
                            ${escapeHTML(row.step)}
                        </td>

                        <td>
                            <strong>
                                ${escapeHTML(row.command)}
                            </strong>
                        </td>

                        <td>
                            ${ok
                                ? "✅ SUCCESS"
                                : "❌ FAILED"}
                        </td>

                        <td>
                            ${escapeHTML(row.attempts || 1)}
                        </td>

                        <td>
                            ${escapeHTML(row.message || "")}
                        </td>

                    </tr>
                `;

            });

            executionHTML += `
                        </tbody>

                    </table>

                </div>
            `;
        }

        // ----------------------------------------------------
        // FAILURE STATUS
        // ----------------------------------------------------

        const failureStatus =
            failure.status ||
            (
                failure.success === true
                    ? "SUCCESS"
                    : "CHECKED"
            );

        // ----------------------------------------------------
        // COMPLETE RESULT
        // ----------------------------------------------------

        resultDiv.innerHTML = `

            <div class="result-card">

                <h2>
                    ${
                        success
                            ? "✅ Robot Task Completed"
                            : "❌ Robot Task Failed"
                    }
                </h2>

                <p>
                    <strong>Instruction:</strong>
                    ${escapeHTML(data.instruction)}
                </p>

                <p>
                    <strong>Intent:</strong>
                    ${escapeHTML(intent)}
                </p>

                <p>
                    <strong>Item:</strong>
                    ${escapeHTML(item)}
                </p>

                <p>
                    <strong>Quantity:</strong>
                    ${escapeHTML(quantity)}
                </p>

                <p>
                    <strong>Target:</strong>
                    ${escapeHTML(target)}
                </p>

                <h3>🧠 AI Parser</h3>

                <pre>${escapeHTML(
                    JSON.stringify(parser, null, 2)
                )}</pre>

            </div>


            <div class="result-card">

                <h2>🔹 Task Decomposition</h2>

                ${decompositionHTML}

            </div>


            <div class="result-card">

                <h2>⚙️ Robot Action Sequence</h2>

                ${actionsHTML}

                <p>
                    <strong>Commands:</strong>
                    ${escapeHTML(
                        commands.join(" → ")
                    )}
                </p>

            </div>


            <div class="result-card">

                <h2>🤖 Robot Execution</h2>

                ${executionHTML}

            </div>


            <div class="result-card">

                <h2>🛡️ Failure Detection & Recovery</h2>

                <p>
                    <strong>Status:</strong>
                    ${escapeHTML(failureStatus)}
                </p>

                <pre>${escapeHTML(
                    JSON.stringify(
                        failure,
                        null,
                        2
                    )
                )}</pre>

            </div>


            <div class="result-card final-status">

                <h2>
                    Overall Status:
                    ${
                        success
                            ? "✅ SUCCESS"
                            : "❌ FAILED"
                    }
                </h2>

                ${
                    success
                    ? `
                        <button
                            type="button"
                            class="simulation-button"
                            onclick="openSimulation()">

                            🤖 Start 3D Restaurant Robot Simulation

                        </button>
                    `
                    : ""
                }

            </div>
        `;

        resultDiv.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });
    }


    // ========================================================
    // ESCAPE HTML
    // ========================================================

    function escapeHTML(value) {

        if (
            value === null ||
            value === undefined
        ) {
            return "";
        }

        return String(value)
            .replace(
                /&/g,
                "&amp;"
            )
            .replace(
                /</g,
                "&lt;"
            )
            .replace(
                />/g,
                "&gt;"
            )
            .replace(
                /"/g,
                "&quot;"
            )
            .replace(
                /'/g,
                "&#039;"
            );
    }

});


// ============================================================
// OPEN 3D SIMULATION
// ============================================================

function openSimulation() {

    const saved =
        sessionStorage.getItem(
            "pipelineResult"
        );

    if (!saved) {

        alert(
            "Please execute an instruction first."
        );

        return;
    }

    window.open(
        "/simulation",
        "_blank"
    );
}


// ============================================================
// GLOBAL FUNCTION
// ============================================================

window.openSimulation =
    openSimulation;

console.log(
    "✅ Restaurant Robot JavaScript initialized successfully."
);