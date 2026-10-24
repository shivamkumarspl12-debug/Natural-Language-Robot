import os
import json
import re
import uuid

from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Existing dataset values
COLORS = ["red", "green", "blue", "yellow"]

OBJECTS = [
    "block",
    "cube",
    "ball",
    "bottle"
]

TARGETS = [
    "box",
    "container",
    "basket",
    "bin",
    "table"
]

# Restaurant objects/items
RESTAURANT_OBJECTS = [
    "water",
    "water bottle",
    "pizza",
    "burger",
    "pasta",
    "coffee",
    "cold drink",
    "drink",
    "food",
    "menu",
    "plate",
    "glass",
    "order"
]

# Restaurant intents
RESTAURANT_INTENTS = [
    "GREETING",
    "MENU",
    "GUIDE",
    "NAVIGATE",
    "ORDER",
    "DELIVERY",
    "RETURN"
]


# ============================================================
# UTILITY
# ============================================================

def find_word(text, words):
    """
    Find the first matching word/phrase.
    """

    text = text.lower()

    # Longer phrases first
    words = sorted(words, key=len, reverse=True)

    for word in words:
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            return word

    return None


def extract_table(text):
    """
    Extract table number.

    Examples:
    table 3
    Table 2
    table number 4
    """

    match = re.search(
        r"\btable\s*(?:number\s*)?(\d+)\b",
        text.lower()
    )

    if match:
        return f"table {match.group(1)}"

    return None


def extract_quantity(text):
    """
    Extract simple quantity from restaurant instruction.
    """

    match = re.search(
        r"\b(\d+)\s*(?:pizza|burger|pasta|coffee|drink|water|bottle)\b",
        text.lower()
    )

    if match:
        return int(match.group(1))

    return 1


DELIVERY_ITEM_PATTERNS = [
    ("plate of food", r"plates?\s+of\s+food"),
    ("water bottle", r"water\s+bottles?"),
    ("cold drink", r"cold\s+drinks?"),
    ("burger", r"burgers?"),
    ("pizza", r"pizzas?"),
    ("pasta", r"pastas?"),
    ("coffee", r"coffees?"),
    ("water", r"water"),
    ("menu", r"menus?"),
    ("food", r"food"),
    ("plate", r"plates?"),
    ("glass", r"glass(?:es)?"),
    ("drink", r"drinks?"),
]

QUANTITY_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_delivery_orders(instruction):
    """Parse delivery items and associate each with a destination table."""
    lower_text = instruction.lower()
    if not re.search(r"\b(deliver|bring|serve|send|take)\b", lower_text):
        return None
    if re.search(r"\btake\s+me\s+to\b", lower_text):
        return None

    item_alternatives = "|".join(
        f"(?P<item_{index}>{pattern})"
        for index, (_, pattern) in enumerate(DELIVERY_ITEM_PATTERNS)
    )
    item_pattern = re.compile(
        rf"(?<!\w)(?:(?P<quantity>\d+|{'|'.join(QUANTITY_WORDS)})\s+)?"
        rf"(?:of\s+)?(?:the\s+)?(?P<item>{item_alternatives})(?!\w)",
        re.IGNORECASE,
    )
    item_matches = []
    for match in item_pattern.finditer(instruction):
        item_index = next(
            index
            for index in range(len(DELIVERY_ITEM_PATTERNS))
            if match.group(f"item_{index}") is not None
        )
        item_name = DELIVERY_ITEM_PATTERNS[item_index][0]
        quantity_text = (match.group("quantity") or "").lower()
        quantity = (
            int(quantity_text)
            if quantity_text.isdigit()
            else QUANTITY_WORDS.get(quantity_text, 1)
        )
        item_matches.append({
            "start": match.start(),
            "name": item_name,
            "quantity": quantity,
        })

    if not item_matches:
        return None

    table_matches = list(re.finditer(
        r"\btable\s*(?:number\s*)?(\d+)\b",
        instruction,
        re.IGNORECASE,
    ))

    grouped_orders = {}
    undestined_items = []
    for table_match in table_matches:
        table_number = int(table_match.group(1))
        grouped_orders.setdefault(table_number, [])

    for item_match in item_matches:
        next_table = next(
            (
                table_match
                for table_match in table_matches
                if table_match.start() > item_match["start"]
            ),
            None,
        )
        if next_table is not None:
            table_number = int(next_table.group(1))
        else:
            previous_tables = [
                table_match
                for table_match in table_matches
                if table_match.start() <= item_match["start"]
            ]
            if (
                not previous_tables
                or item_match["start"] > previous_tables[-1].end()
            ):
                undestined_items.append(item_match)
                continue
            table_number = int(previous_tables[-1].group(1))

        grouped_orders[table_number].append({
            "name": item_match["name"],
            "quantity": item_match["quantity"],
            "status": "VALIDATED",
            "delivery_status": "PENDING",
            "delivered_quantity": 0,
        })

    orders = [
        {
            "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}-{index:03d}",
            "table": table_number,
            "items": items,
            "status": "VALIDATED" if items else "MISSING_ITEMS",
            "delivery_status": "PENDING",
        }
        for index, (table_number, items) in enumerate(
            grouped_orders.items(),
            start=1,
        )
    ]

    if undestined_items:
        orders.append({
            "order_id": (
                f"ORD-{uuid.uuid4().hex[:8].upper()}-"
                f"{len(orders) + 1:03d}"
            ),
            "table": None,
            "items": [
                {
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "status": "VALIDATED",
                    "delivery_status": "PENDING",
                    "delivered_quantity": 0,
                }
                for item in undestined_items
            ],
            "status": "MISSING_DESTINATION",
            "delivery_status": "PENDING",
        })

    if not table_matches:
        orders = [{
            "order_id": f"ORD-{uuid.uuid4().hex[:8].upper()}-001",
            "table": None,
            "items": [
                {
                    "name": item["name"],
                    "quantity": item["quantity"],
                    "status": "VALIDATED",
                    "delivery_status": "PENDING",
                    "delivered_quantity": 0,
                }
                for item in item_matches
            ],
            "status": "MISSING_DESTINATION",
            "delivery_status": "PENDING",
        }]

    if not orders:
        return None

    flattened_items = [
        item
        for order in orders
        for item in order["items"]
    ]
    return {
        "intent": "DELIVERY",
        "actions": ["PICK", "PLACE"],
        "color": "",
        "object": flattened_items[0]["name"] if flattened_items else "",
        "item": flattened_items[0]["name"] if flattened_items else "",
        "quantity": flattened_items[0]["quantity"] if flattened_items else 1,
        "original_instruction": instruction,
        "target": (
            f"table {orders[0]['table']}"
            if len(orders) == 1 and orders[0]["table"] is not None
            else ""
        ),
        "orders": orders,
    }


# ============================================================
# RESTAURANT INTENT DETECTION
# ============================================================

def detect_restaurant_intent(text):

    lower_text = text.lower()

    # --------------------------------------------------------
    # GREETING
    # --------------------------------------------------------

    greeting_words = [
        "hello",
        "hi",
        "hey",
        "greet",
        "welcome",
        "say hello",
        "greet customer",
        "welcome customer"
    ]

    if any(word in lower_text for word in greeting_words):
        return "GREETING"

    # --------------------------------------------------------
    # MENU
    # --------------------------------------------------------

    menu_words = [
        "menu",
        "show menu",
        "show me the menu",
        "view menu",
        "display menu"
    ]

    if any(word in lower_text for word in menu_words):
        return "MENU"

    # --------------------------------------------------------
    # GUIDE CUSTOMER
    # --------------------------------------------------------

    guide_words = [
        "guide",
        "seat me",
        "take me to",
        "lead me",
        "show me to",
        "escort",
        "guide customer"
    ]

    if any(word in lower_text for word in guide_words):
        return "GUIDE"

    # --------------------------------------------------------
    # NAVIGATION
    # --------------------------------------------------------

    navigation_words = [
        "go to table",
        "move to table",
        "navigate to table",
        "travel to table",
        "reach table"
    ]

    if any(word in lower_text for word in navigation_words):
        return "NAVIGATE"

    # --------------------------------------------------------
    # DELIVERY
    # --------------------------------------------------------

    delivery_words = [
        "deliver",
        "delivery",
        "bring",
        "serve",
        "take the",
        "send",
        "deliver food",
        "deliver order"
    ]

    if any(word in lower_text for word in delivery_words):
        return "DELIVERY"

    # --------------------------------------------------------
    # ORDER
    # --------------------------------------------------------

    order_words = [
        "order",
        "i want",
        "i would like",
        "give me",
        "can i have",
        "i need"
    ]

    restaurant_items = [
        "pizza",
        "burger",
        "pasta",
        "coffee",
        "water",
        "drink",
        "cold drink",
        "food"
    ]

    if any(word in lower_text for word in order_words):
        if any(item in lower_text for item in restaurant_items):
            return "ORDER"

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return_words = [
        "return",
        "go back",
        "come back",
        "return to counter",
        "go to counter"
    ]

    if any(word in lower_text for word in return_words):
        return "RETURN"

    return None


# ============================================================
# RESTAURANT ITEM EXTRACTION
# ============================================================

def extract_restaurant_object(text):

    lower_text = text.lower()

    # Check longer names first
    restaurant_objects_sorted = sorted(
        RESTAURANT_OBJECTS,
        key=len,
        reverse=True
    )

    for item in restaurant_objects_sorted:

        if re.search(
            r"\b" + re.escape(item) + r"\b",
            lower_text
        ):
            return item

    return None


# ============================================================
# RULE-BASED FALLBACK PARSER
# ============================================================

def rule_based_parser(instruction):

    text = instruction.strip()
    lower_text = text.lower()

    # --------------------------------------------------------
    # Check restaurant intent first
    # --------------------------------------------------------

    restaurant_intent = detect_restaurant_intent(lower_text)

    if restaurant_intent:

        table = extract_table(lower_text)
        restaurant_object = extract_restaurant_object(lower_text)
        quantity = extract_quantity(lower_text)

        # GREETING
        if restaurant_intent == "GREETING":

            return {
                "intent": "GREETING",
                "actions": ["GREET"],
                "color": "",
                "object": "",
                "item": "",
                "quantity": 1,
                "original_instruction": text,
                "target": ""
            }

        # MENU
        if restaurant_intent == "MENU":

            return {
                "intent": "MENU",
                "actions": ["SHOW_MENU"],
                "color": "",
                "object": "menu",
                "item": "menu",
                "quantity": 1,
                "original_instruction": text,
                "target": ""
            }

        # GUIDE
        if restaurant_intent == "GUIDE":

            return {
                "intent": "GUIDE",
                "actions": ["GUIDE"],
                "color": "",
                "object": "customer",
                "item": "",
                "quantity": 1,
                "original_instruction": text,
                "target": table or ""
            }

        # NAVIGATE
        if restaurant_intent == "NAVIGATE":

            return {
                "intent": "NAVIGATE",
                "actions": ["NAVIGATE"],
                "color": "",
                "object": "",
                "item": "",
                "quantity": 1,
                "original_instruction": text,
                "target": table or ""
            }

        # ORDER
        if restaurant_intent == "ORDER":

            return {
                "intent": "ORDER",
                "actions": ["ORDER"],
                "color": "",
                "object": restaurant_object or "",
                "item": restaurant_object or "",
                "quantity": quantity,
                "original_instruction": text,
                "target": table or ""
            }

        # DELIVERY
        if restaurant_intent == "DELIVERY":

            return {
                "intent": "DELIVERY",
                "actions": ["PICK", "PLACE"],
                "color": "",
                "object": restaurant_object or "",
                "item": restaurant_object or "",
                "quantity": quantity,
                "original_instruction": text,
                "target": table or ""
            }

        # RETURN
        if restaurant_intent == "RETURN":

            return {
                "intent": "RETURN",
                "actions": ["RETURN"],
                "color": "",
                "object": "",
                "item": "",
                "quantity": 1,
                "original_instruction": text,
                "target": "counter"
            }

    # ========================================================
    # EXISTING ROBOT DATASET PARSER
    # ========================================================

    color = find_word(lower_text, COLORS)

    obj = find_word(
        lower_text,
        OBJECTS
    )

    target = find_word(
        lower_text,
        TARGETS
    )

    pick_words = [
        "pick",
        "pick up",
        "grab",
        "take",
        "lift",
        "get"
    ]

    place_words = [
        "place",
        "put",
        "move",
        "transfer",
        "drop"
    ]

    has_pick = any(
        word in lower_text
        for word in pick_words
    )

    has_place = any(
        word in lower_text
        for word in place_words
    )

    actions = []

    if has_pick:
        actions.append("PICK")

    if has_place:
        actions.append("PLACE")

    if obj and target and (has_pick or has_place):

        actions = [
            "PICK",
            "PLACE"
        ]

    return {
        "intent": "PICK_AND_PLACE",
        "actions": actions,
        "color": color,
        "object": obj,
        "item": obj or "",
        "quantity": 1,
        "original_instruction": text,
        "target": target
    }


# ============================================================
# VALIDATION
# ============================================================

def validate_result(result, instruction):

    if not isinstance(result, dict):
        return False

    # These fields must always exist
    required_fields = [
        "intent",
        "actions",
        "color",
        "object",
        "original_instruction",
        "target"
    ]

    for field in required_fields:

        if field not in result:
            return False

    # Actions must be a list
    if not isinstance(result["actions"], list):
        return False

    # Must contain at least one action
    if not result["actions"]:
        return False

    # Intent must be known
    valid_intents = [
        "PICK_AND_PLACE",
        "GREETING",
        "MENU",
        "GUIDE",
        "NAVIGATE",
        "ORDER",
        "DELIVERY",
        "RETURN"
    ]

    if result["intent"] not in valid_intents:
        return False

    # --------------------------------------------------------
    # Restaurant validation
    # --------------------------------------------------------

    if result["intent"] in RESTAURANT_INTENTS:

        return True

    # --------------------------------------------------------
    # Legacy robot validation
    # --------------------------------------------------------

    if result["color"] not in COLORS:
        return False

    if result["object"] not in OBJECTS:
        return False

    if result["target"] not in TARGETS:
        return False

    return True


# ============================================================
# GEMINI LLM PARSER
# ============================================================

def gemini_parser(instruction):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY not found in .env"
        )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    prompt = f"""
You are an AI instruction parser for a restaurant service robot.

The robot can:
1. Detect and greet customers
2. Show the restaurant menu
3. Guide customers to tables
4. Navigate to tables
5. Take food orders
6. Deliver food or drinks
7. Return to the counter
8. Pick and place physical objects

Convert the user's natural-language instruction into JSON.

============================================================
SUPPORTED RESTAURANT INTENTS
============================================================

GREETING
MENU
GUIDE
NAVIGATE
ORDER
DELIVERY
RETURN
PICK_AND_PLACE

============================================================
SUPPORTED LEGACY ROBOT OBJECTS
============================================================

block
cube
ball
bottle

============================================================
SUPPORTED COLORS
============================================================

red
green
blue
yellow

============================================================
RESTAURANT ITEMS
============================================================

water
water bottle
pizza
burger
pasta
coffee
cold drink
drink
food
menu
plate
glass
order

============================================================
RULES
============================================================

1. "hello", "hi", "welcome", "greet customer"
   -> GREETING

2. "show menu", "show me the menu", "view menu"
   -> MENU

3. "guide me", "guide customer", "take me to table 3",
   "seat the customer"
   -> GUIDE

4. "go to table 3", "move to table 3",
   "navigate to table 3"
   -> NAVIGATE

5. "I want pizza", "I want a burger",
   "order coffee"
   -> ORDER

6. "deliver the water bottle to table 3",
   "bring pizza to table 2",
   "serve food at table 4"
   -> DELIVERY

7. "return to counter", "go back to counter"
   -> RETURN

8. Traditional robot instructions such as:
   "Pick up the red block and put it in the box"
   -> PICK_AND_PLACE

9. For restaurant commands, color can be an empty string.

10. If a table number exists, return it as:
    "table 3"

11. If a restaurant item exists, return it in both:
    "object" and "item"

12. quantity should be an integer.
    Default quantity is 1.

13. Return ONLY valid JSON.

14. Do not return markdown.

15. Do not return explanations.

============================================================
OUTPUT FORMAT
============================================================

Return exactly:

{{
    "intent": "DELIVERY",
    "actions": ["PICK", "PLACE"],
    "color": "",
    "object": "water bottle",
    "item": "water bottle",
    "quantity": 1,
    "original_instruction": "{instruction}",
    "target": "table 3"
}}

User instruction:
{instruction}
"""

    response = client.interactions.create(
        model="gemini-3.6-flash",
        input=prompt
    )

    text = response.output_text.strip()

    # --------------------------------------------------------
    # Remove markdown code fences
    # --------------------------------------------------------

    text = re.sub(
        r"```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```\s*",
        "",
        text
    )

    text = text.strip()

    # --------------------------------------------------------
    # Extract JSON if Gemini adds extra text
    # --------------------------------------------------------

    if not text.startswith("{"):

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1:

            text = text[start:end + 1]

    result = json.loads(text)

    # --------------------------------------------------------
    # Add missing optional fields
    # --------------------------------------------------------

    result.setdefault("intent", "PICK_AND_PLACE")
    result.setdefault("item", result.get("object", ""))
    result.setdefault("quantity", 1)

    result.setdefault("color", "")
    result.setdefault("object", "")
    result.setdefault("target", "")

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if not validate_result(
        result,
        instruction
    ):

        raise ValueError(
            "Gemini returned invalid parser output."
        )

    # Always preserve original instruction
    result["original_instruction"] = instruction.strip()

    return result


# ============================================================
# MAIN PARSER
# ============================================================

def parse_instruction(instruction):

    if not isinstance(instruction, str):

        raise TypeError(
            "Instruction must be a string."
        )

    text = instruction.strip()

    if not text:

        raise ValueError(
            "Instruction cannot be empty."
        )

    delivery_result = parse_delivery_orders(text)
    if delivery_result is not None:
        print("Parser used: Rule-Based Delivery Orders")
        return delivery_result

    # ========================================================
    # USE THE LOCAL PARSER FOR RECOGNIZED INSTRUCTIONS
    # ========================================================

    rule_result = rule_based_parser(text)

    has_required_restaurant_item = (
        rule_result.get("intent") not in {
            "DELIVERY",
            "ORDER"
        }
        or bool(rule_result.get("item"))
    )

    if (
        validate_result(rule_result, text)
        and has_required_restaurant_item
    ):

        print(
            "Parser used: Rule-Based"
        )

        return rule_result

    # ========================================================
    # USE GEMINI FOR INSTRUCTIONS THE LOCAL PARSER CANNOT HANDLE
    # ========================================================

    try:

        result = gemini_parser(text)

        print(
            "Parser used: Gemini LLM"
        )

        return result

    except Exception as error:

        print(
            "Gemini parser unavailable:",
            error
        )

        print(
            "Using rule-based fallback parser..."
        )

        print(
            "Parser used: Rule-Based Fallback"
        )

        return rule_result


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test_instructions = [

        # ----------------------------------------------------
        # OLD ROBOT TESTS
        # ----------------------------------------------------

        "Pick up the red block and put it in the box.",

        "Grab the green cube and place it in the container.",

        "Take the blue ball to the basket.",

        "Move the yellow bottle into the bin.",

        "Please transfer the red cube to the basket.",

        # ----------------------------------------------------
        # RESTAURANT TESTS
        # ----------------------------------------------------

        "Greet the customer.",

        "Show me the menu.",

        "Guide the customer to table 3.",

        "Go to table 2.",

        "I want a pizza.",

        "Order a burger.",

        "Deliver the water bottle to table 3.",

        "Bring the coffee to table 4.",

        "Return to the counter."
    ]

    print("=" * 70)

    print(
        "🤖 RESTAURANT ROBOT INSTRUCTION PARSER TEST"
    )

    print("=" * 70)

    for i, instruction in enumerate(
        test_instructions,
        1
    ):

        print(f"\n{'=' * 70}")

        print(
            f"TEST {i}"
        )

        print(
            "Instruction:",
            instruction
        )

        try:

            result = parse_instruction(
                instruction
            )

            print(
                "\nParsed Result:"
            )

            print(
                json.dumps(
                    result,
                    indent=4
                )
            )

        except Exception as error:

            print(
                "❌ Error:",
                error
            )

    print(
        "\n" + "=" * 70
    )

    print(
        "✅ PARSER TEST COMPLETED"
    )

    print(
        "=" * 70
    )