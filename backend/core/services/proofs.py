"""Fulfilment proof policy.

Photos are never mandatory for every order type. The policy below is explicit:
parcels and logistics need a delivery code and a photo, store deliveries accept
an optional photo and recipient name, rides need neither.
"""

OTP_SERVICES = {"parcel", "logistics"}
PHOTO_REQUIRED_SERVICES = {"parcel", "logistics"}


def proof_policy(order):
    service = order.resolved_service()
    return {
        "otp_required": service in OTP_SERVICES,
        "photo_required": service in PHOTO_REQUIRED_SERVICES,
        "recipient_required": service in OTP_SERVICES,
    }


def proof_complete(order, kind="delivery"):
    proof = order.proofs.filter(kind=kind).first()
    if proof is None:
        return False
    policy = proof_policy(order)
    if kind != "delivery":
        return True
    if policy["otp_required"] and not proof.otp_verified:
        return False
    if policy["photo_required"] and not proof.photo:
        return False
    return True
