# ============================================================
# ACTION GENERATOR
# Natural Language Restaurant Service Robot
# ============================================================


def generate_action_sequence(decomposed_steps):
    """
    Convert high-level decomposed robot tasks into
    executable robot actions.

    Supports:
    - Traditional pick and place
    - Customer greeting
    - Menu service
    - Table guidance
    - Navigation
    - Order taking
    - Food delivery
    - Return to counter
    """

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    if not isinstance(decomposed_steps, list):
        return []

    # --------------------------------------------------------
    # Mapping:
    # High-level task -> Low-level robot command
    # --------------------------------------------------------

    action_mapping = {

        # ====================================================
        # OBJECT PICK & PLACE
        # ====================================================

        "DETECT_OBJECT": "DETECT",

        "MOVE_TO_OBJECT": "MOVE",

        "PICK": "GRAB",

        "MOVE_TO_TARGET": "MOVE",

        "PLACE": "RELEASE",


        # ====================================================
        # CUSTOMER SERVICE
        # ====================================================

        "DETECT_CUSTOMER": "DETECT_CUSTOMER",

        "GREET_CUSTOMER": "GREET",

        "SHOW_MENU": "SHOW_MENU",


        # ====================================================
        # TABLE SERVICE
        # ====================================================

        "ASSIGN_TABLE": "ASSIGN_TABLE",

        "MOVE_TO_CUSTOMER": "MOVE_TO_CUSTOMER",

        "GUIDE_TO_TABLE": "GUIDE",


        # ====================================================
        # NAVIGATION
        # ====================================================

        "GET_CURRENT_LOCATION": "GET_LOCATION",

        "PLAN_ROUTE": "PLAN_ROUTE",

        "NAVIGATE_TO_TABLE": "NAVIGATE",

        "CONFIRM_ARRIVAL": "CONFIRM_ARRIVAL",


        # ====================================================
        # ORDER SERVICE
        # ====================================================

        "TAKE_ORDER": "TAKE_ORDER",

        "CONFIRM_ORDER": "CONFIRM_ORDER",


        # ====================================================
        # FOOD / ORDER DELIVERY
        # ====================================================

        "CONFIRM_DELIVERY": "CONFIRM_DELIVERY",

        "RETURN_TO_COUNTER": "RETURN"

    }


    # --------------------------------------------------------
    # Generate action sequence
    # --------------------------------------------------------

    action_sequence = []

    for step in decomposed_steps:

        # ----------------------------------------------------
        # Validate individual step
        # ----------------------------------------------------

        if not isinstance(step, dict):
            continue

        task = step.get("task")

        if not task:
            continue

        # ----------------------------------------------------
        # Convert task to robot action
        # ----------------------------------------------------

        if task in action_mapping:

            action_sequence.append({

                "step": len(action_sequence) + 1,

                "action": action_mapping[task],

                "source_task": task

            })

    return action_sequence


# ============================================================
# TESTING
# ============================================================

if __name__ == "__main__":

    from instruction_parser import parse_instruction
    from task_decomposer import decompose_task


    # ========================================================
    # TEST INSTRUCTIONS
    # ========================================================

    test_instructions = [

        # Traditional robot tasks
        "Pick up the red block and put it in the box.",

        "Grab the green cube and place it in the container.",

        "Take the blue ball to the basket.",

        "Move the yellow bottle into the bin.",


        # Customer service
        "Greet the customer.",

        "Show the customer the menu.",


        # Table service
        "Guide the customer to table 3.",

        "Go to table 4.",


        # Order service
        "I want a pizza.",

        "Order a burger.",


        # Food delivery
        "Deliver the water bottle to table 2.",


        # Return
        "Return to the counter."

    ]


    print("=" * 70)

    print("🤖 ACTION GENERATOR TEST")

    print("NATURAL LANGUAGE RESTAURANT SERVICE ROBOT")

    print("=" * 70)


    # ========================================================
    # PROCESS EACH TEST
    # ========================================================

    for i, instruction in enumerate(
        test_instructions,
        1
    ):

        print("\n")

        print("-" * 70)

        print(f"TEST {i}")

        print("-" * 70)


        print("\n🗣️ Instruction:")

        print(instruction)


        # ====================================================
        # STEP 1: PARSER
        # ====================================================

        try:

            parsed = parse_instruction(
                instruction
            )

        except Exception as e:

            print("\n❌ Parser Error:")

            print(e)

            continue


        print("\n🧠 Parsed Goal:")

        print(parsed)


        # ====================================================
        # STEP 2: TASK DECOMPOSITION
        # ====================================================

        try:

            decomposed_steps = decompose_task(
                parsed
            )

        except Exception as e:

            print("\n❌ Task Decomposition Error:")

            print(e)

            continue


        print("\n🔹 Task Decomposition:")


        if not decomposed_steps:

            print("No decomposition generated.")

        else:

            for step in decomposed_steps:

                print(

                    f"{step.get('step', '?')}. "

                    f"{step.get('task', 'UNKNOWN')} "

                    f"- "

                    f"{step.get('description', '')}"

                )


        # ====================================================
        # STEP 3: ACTION GENERATION
        # ====================================================

        actions = generate_action_sequence(
            decomposed_steps
        )


        print("\n⚙️ Robot Action Sequence:")


        if not actions:

            print("❌ No executable actions generated.")

        else:

            for action in actions:

                print(

                    f"{action['step']}. "

                    f"{action['action']} "

                    f"(from "

                    f"{action['source_task']}"

                    f")"

                )


        # ====================================================
        # STEP 4: SUMMARY
        # ====================================================

        print("\n📊 Summary:")

        print(
            "Decomposition Steps:",
            len(decomposed_steps)
        )

        print(
            "Generated Actions:",
            len(actions)
        )


        if actions:

            print(
                "Status: ✅ ACTION GENERATION SUCCESS"
            )

        else:

            print(
                "Status: ❌ ACTION GENERATION FAILED"
            )


    # ========================================================
    # COMPLETION
    # ========================================================

    print("\n")

    print("=" * 70)

    print("✅ ACTION GENERATOR TEST COMPLETED")

    print("=" * 70)