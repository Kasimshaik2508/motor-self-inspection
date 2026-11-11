"""
vehicles.py - the DEMO registration (RC) records: a stand-in for the government VAHAN lookup.

WHY: in real life the customer types only their CAR NUMBER (as on InsuranceDekho's start screen). The insurer then
fetches the car's RC (registration certificate) record from VAHAN, which includes the chassis number. So the "truth"
comes from the government record, not from the customer, and the photos must match it: the plate in the photos must
be this car number, and the chassis label in the photo must match the chassis on the RC. A cheater cannot just type
numbers that match their photos. (Self-inspection happens BEFORE a policy is issued, so there is no policy number yet.)
HOW: a small fixed table (we cannot call the real VAHAN). Every entry is SYNTHETIC: made-up car numbers, owners and
chassis numbers. The demo photos in web/public/demo-photos/ show plate KA 01 AB 1234 and a synthetic chassis label
ending 654321, so KA01AB1234 is the "right car" for them.
The chassis number is never sent to the customer's screen: the server compares it, so it cannot be copied.
"""

VEHICLES = {
    "KA01AB1234": {"owner": "Asha Rao (demo)", "make_model": "Tata Nexon XZA+", "colour": "Blue",
                   "plate": "KA 01 AB 1234", "chassis": "MAT62DMX5PA654321", "note": "matches the demo photos"},
    "DL3CAB5678": {"owner": "Rohit Verma (demo)", "make_model": "Maruti Suzuki Swift VXi", "colour": "Red",
                   "plate": "DL 3C AB 5678", "chassis": "MA3EWDE1S00123456",
                   "note": "a different car: demo photos of another car are sent for it"},
    "22BH1234AA": {"owner": "Meera Iyer (demo)", "make_model": "Hyundai Creta SX", "colour": "White",
                   "plate": "22 BH 1234 AA", "chassis": "MALC381CLPM778899", "note": "Bharat-series plate example"},
}


def normalise(car_no):
    """'ka 01 ab-1234' -> 'KA01AB1234' (people type spaces and dashes in different places)."""
    return "".join(ch for ch in str(car_no or "").upper() if ch.isalnum())


def lookup(car_no):
    """-> the RC record, or raises KeyError."""
    return {"car_no": normalise(car_no), **VEHICLES[normalise(car_no)]}


def customer_view(v):
    """What the customer's screen may show: the car to photograph. NOT the chassis number."""
    return {"car_no": v["car_no"], "owner": v["owner"], "make_model": v["make_model"], "colour": v["colour"],
            "plate": v["plate"]}


def demo_list():
    """For the demo screen: the car numbers to try, with what each one demonstrates."""
    return [{**customer_view(lookup(k)), "note": v["note"]} for k, v in VEHICLES.items()]
