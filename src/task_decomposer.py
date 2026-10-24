# ============================================================
# TASK DECOMPOSER
# Natural Language Restaurant Service Robot
# ============================================================


def decompose_task(parsed_instruction):

    # --------------------------------------------------------
    # Basic validation
    # --------------------------------------------------------

    if not isinstance(parsed_instruction, dict):
        return []

    intent = parsed_instruction.get("intent", "")
    actions = parsed_instruction.get("actions", [])

    obj = parsed_instruction.get("object", "")
    item = parsed_instruction.get("item", "")
    target = parsed_instruction.get("target", "")
    color = parsed_instruction.get("color", "")

    # Use item if object is empty
    if not obj and item:
        obj = item

    steps = []

    # ========================================================
    # 1. CUSTOMER GREETING
    # ========================================================

    if intent in [
        "GREETING",
        "GREET",
        "WELCOME",
        "CUSTOMER_GREETING"
    ]:

        steps = [
            {
                "step": 1,
                "task": "DETECT_CUSTOMER",
                "description": "Detect the customer entering the restaurant"
            },
            {
                "step": 2,
                "task": "GREET_CUSTOMER",
                "description": "Greet the customer and ask how to help"
            }
        ]

        return steps

    # ========================================================
    # 2. SHOW MENU
    # ========================================================

    if intent in [
        "MENU",
        "SHOW_MENU",
        "VIEW_MENU"
    ]:

        steps = [
            {
                "step": 1,
                "task": "DETECT_CUSTOMER",
                "description": "Detect the customer"
            },
            {
                "step": 2,
                "task": "GREET_CUSTOMER",
                "description": "Greet the customer"
            },
            {
                "step": 3,
                "task": "SHOW_MENU",
                "description": "Show the restaurant menu to the customer"
            }
        ]

        return steps

    # ========================================================
    # 3. GUIDE CUSTOMER TO TABLE
    # ========================================================

    if intent in [
        "GUIDE",
        "GUIDE_CUSTOMER",
        "TABLE_GUIDANCE"
    ]:

        steps = [
            {
                "step": 1,
                "task": "DETECT_CUSTOMER",
                "description": "Detect the customer"
            },
            {
                "step": 2,
                "task": "GREET_CUSTOMER",
                "description": "Greet the customer"
            },
            {
                "step": 3,
                "task": "ASSIGN_TABLE",
                "description": f"Assign {target or 'an available table'} to the customer"
            },
            {
                "step": 4,
                "task": "MOVE_TO_CUSTOMER",
                "description": "Move the robot toward the customer"
            },
            {
                "step": 5,
                "task": "GUIDE_TO_TABLE",
                "description": f"Guide the customer to {target or 'the assigned table'}"
            }
        ]

        return steps

    # ========================================================
    # 4. NAVIGATION
    # ========================================================

    if intent in [
        "NAVIGATE",
        "NAVIGATION",
        "GO_TO_TABLE",
        "TABLE_NAVIGATION"
    ]:

        steps = [
            {
                "step": 1,
                "task": "GET_CURRENT_LOCATION",
                "description": "Get the robot's current location"
            },
            {
                "step": 2,
                "task": "PLAN_ROUTE",
                "description": f"Plan a safe route to {target or 'the destination'}"
            },
            {
                "step": 3,
                "task": "NAVIGATE_TO_TABLE",
                "description": f"Navigate to {target or 'the target table'}"
            },
            {
                "step": 4,
                "task": "CONFIRM_ARRIVAL",
                "description": f"Confirm arrival at {target or 'the destination'}"
            }
        ]

        return steps

    # ========================================================
    # 5. CUSTOMER ORDER
    # ========================================================

    if intent in [
        "ORDER",
        "TAKE_ORDER"
    ]:

        steps = [
            {
                "step": 1,
                "task": "DETECT_CUSTOMER",
                "description": "Detect the customer"
            },
            {
                "step": 2,
                "task": "GREET_CUSTOMER",
                "description": "Greet the customer"
            },
            {
                "step": 3,
                "task": "TAKE_ORDER",
                "description": f"Take the order for {obj or 'the requested item'}"
            },
            {
                "step": 4,
                "task": "CONFIRM_ORDER",
                "description": f"Confirm the order for {obj or 'the requested item'}"
            }
        ]

        return steps

    # ========================================================
    # 6. FOOD / DRINK DELIVERY
    # ========================================================

    if intent in [
        "DELIVERY",
        "DELIVER",
        "FOOD_DELIVERY",
        "ORDER_DELIVERY",
        "DELIVER_FOOD"
    ]:

        object_name = obj or "the ordered item"
        target_name = target or "the customer table"

        steps = [
            {
                "step": 1,
                "task": "DETECT_OBJECT",
                "description": f"Detect {object_name}"
            },
            {
                "step": 2,
                "task": "MOVE_TO_OBJECT",
                "description": f"Move robot to {object_name}"
            },
            {
                "step": 3,
                "task": "PICK",
                "description": f"Pick up {object_name}"
            },
            {
                "step": 4,
                "task": "PLAN_ROUTE",
                "description": f"Plan a safe route to {target_name}"
            },
            {
                "step": 5,
                "task": "NAVIGATE_TO_TABLE",
                "description": f"Navigate to {target_name}"
            },
            {
                "step": 6,
                "task": "PLACE",
                "description": f"Place {object_name} at {target_name}"
            },
            {
                "step": 7,
                "task": "CONFIRM_DELIVERY",
                "description": "Confirm successful delivery to the customer"
            },
            {
                "step": 8,
                "task": "RETURN_TO_COUNTER",
                "description": "Return the robot to the restaurant counter"
            }
        ]

        return steps

    # ========================================================
    # 7. RETURN TO COUNTER
    # ========================================================

    if intent in [
        "RETURN",
        "RETURN_TO_COUNTER"
    ]:

        steps = [
            {
                "step": 1,
                "task": "GET_CURRENT_LOCATION",
                "description": "Get the robot's current location"
            },
            {
                "step": 2,
                "task": "PLAN_ROUTE",
                "description": "Plan a route back to the counter"
            },
            {
                "step": 3,
                "task": "RETURN_TO_COUNTER",
                "description": "Return the robot to the counter"
            }
        ]

        return steps

    # ========================================================
    # 8. LEGACY PICK AND PLACE
    # ========================================================

    if intent == "PICK_AND_PLACE":

        if not obj or not target:
            return []

        steps = [
            {
                "step": 1,
                "task": "DETECT_OBJECT",
                "description": f"Detect the {color + ' ' if color else ''}{obj}"
            },
            {
                "step": 2,
                "task": "MOVE_TO_OBJECT",
                "description": f"Move robot to the {color + ' ' if color else ''}{obj}"
            },
            {
                "step": 3,
                "task": "PICK",
                "description": f"Pick the {color + ' ' if color else ''}{obj}"
            },
            {
                "step": 4,
                "task": "MOVE_TO_TARGET",
                "description": f"Move robot to the {target}"
            },
            {
                "step": 5,
                "task": "PLACE",
                "description": f"Place the {color + ' ' if color else ''}{obj} in the {target}"
            }
        ]

        return steps

    # ========================================================
    # 9. FALLBACK BASED ON ACTIONS
    # ========================================================

    if isinstance(actions, list):

        if "PICK" in actions and "PLACE" in actions:

            if obj and target:

                return [
                    {
                        "step": 1,
                        "task": "DETECT_OBJECT",
                        "description": f"Detect {obj}"
                    },
                    {
                        "step": 2,
                        "task": "MOVE_TO_OBJECT",
                        "description": f"Move to {obj}"
                    },
                    {
                        "step": 3,
                        "task": "PICK",
                        "description": f"Pick {obj}"
                    },
                    {
                        "step": 4,
                        "task": "MOVE_TO_TARGET",
                        "description": f"Move to {target}"
                    },
                    {
                        "step": 5,
                        "task": "PLACE",
                        "description": f"Place {obj} in {target}"
                    }
                ]

    return []


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_cases = [

        {
            "intent": "GREETING",
            "actions": ["GREET"],
            "object": "",
            "target": ""
        },

        {
            "intent": "MENU",
            "actions": ["SHOW_MENU"],
            "object": "menu",
            "target": ""
        },

        {
            "intent": "GUIDE",
            "actions": ["GUIDE"],
            "object": "customer",
            "target": "table 3"
        },

        {
            "intent": "NAVIGATE",
            "actions": ["NAVIGATE"],
            "object": "",
            "target": "table 2"
        },

        {
            "intent": "ORDER",
            "actions": ["ORDER"],
            "object": "pizza",
            "target": ""
        },

        {
            "intent": "DELIVERY",
            "actions": ["PICK", "PLACE"],
            "object": "water bottle",
            "target": "table 3"
        },

        {
            "intent": "RETURN",
            "actions": ["RETURN"],
            "object": "",
            "target": "counter"
        },

        {
            "intent": "PICK_AND_PLACE",
            "actions": ["PICK", "PLACE"],
            "color": "red",
            "object": "block",
            "target": "box"
        }
    ]

    print("=" * 70)
    print("🤖 TASK DECOMPOSER TEST")
    print("=" * 70)

    for i, test in enumerate(test_cases, 1):

        print(f"\nTEST {i}")
        print("-" * 70)

        result = decompose_task(test)

        print("Intent:", test.get("intent"))
        print("Object:", test.get("object"))
        print("Target:", test.get("target"))

        print("\nTask Decomposition:")

        for step in result:
            print(
                f"{step['step']}. "
                f"{step['task']} → "
                f"{step['description']}"
            )

    print("\n" + "=" * 70)
    print("✅ TASK DECOMPOSER TEST COMPLETED")
    print("=" * 70)