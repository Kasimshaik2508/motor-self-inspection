"""
policies.py - the DEMO policy database.

WHY: in real life the customer does not type their own chassis number. The insurer already has the plate and the
chassis number from the RC (registration certificate) when the policy was sold. So the customer enters only the
policy number; we look the car up here and check the photos against what WE have on file. A cheater cannot just
type numbers that match their photos.
HOW: a small fixed table (no database server; it fits the free Render plan). Every entry is SYNTHETIC: made-up
policy numbers, owners, plates and chassis numbers. The demo photos in web/public/demo-photos/ show plate
KA 01 AB 1234 and a synthetic chassis label ending 654321, so PN-DEMO-001 is the "right car" for them.
The chassis number is never sent to the customer's screen: the server compares it, so it cannot be copied.
"""

POLICIES = {
    "PN-DEMO-001": {"owner": "Asha Rao (demo)", "make_model": "Tata Nexon XZA+", "colour": "Blue",
                    "plate": "KA 01 AB 1234", "chassis": "MAT62DMX5PA654321", "note": "matches the demo photos"},
    "PN-DEMO-002": {"owner": "Rohit Verma (demo)", "make_model": "Maruti Suzuki Swift VXi", "colour": "Red",
                    "plate": "DL 3C AB 5678", "chassis": "MA3EWDE1S00123456", "note": "a different car: demo of a wrong-car claim"},
    "PN-DEMO-003": {"owner": "Meera Iyer (demo)", "make_model": "Hyundai Creta SX", "colour": "White",
                    "plate": "22 BH 1234 AA", "chassis": "MALC381CLPM778899", "note": "Bharat-series plate example"},
}


def normalise(policy_no):
    return str(policy_no or "").strip().upper().replace(" ", "")


def lookup(policy_no):
    """-> the policy dict with its number, or raises KeyError."""
    p = POLICIES[normalise(policy_no)]
    return {"policy_no": normalise(policy_no), **p}


def customer_view(p):
    """What the customer's screen may show: the car to photograph. NOT the chassis number."""
    return {"policy_no": p["policy_no"], "owner": p["owner"], "make_model": p["make_model"], "colour": p["colour"],
            "plate": p["plate"]}


def demo_list():
    """For the demo screen: the policy numbers to try, with what each one demonstrates."""
    return [{**customer_view(lookup(k)), "note": v["note"]} for k, v in POLICIES.items()]
