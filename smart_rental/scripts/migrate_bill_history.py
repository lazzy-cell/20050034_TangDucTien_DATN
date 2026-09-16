"""One-time migration of terminal room bills into bill_history.

Run from the project root after Firebase credentials are configured:
    python scripts/migrate_bill_history.py

Only paid/cancelled bills are moved. Unpaid bills remain under rooms/{room_id}/bills.
"""
from datetime import datetime

from services.firebase_service import get_firestore
from services.id_service import new_document_ref


db = get_firestore()


def main():
    moved = 0
    rooms = list(db.collection("rooms").stream())

    for room_doc in rooms:
        room = room_doc.to_dict() or {}
        room_name = room.get("room_name") or room_doc.id

        for bill_doc in room_doc.reference.collection("bills").stream():
            bill = bill_doc.to_dict() or {}
            status = bill.get("status")

            if status not in ("paid", "cancelled"):
                continue

            # Avoid creating duplicates when the script is run again.
            existing = False
            for history_doc in db.collection("bill_history").stream():
                history = history_doc.to_dict() or {}
                if (
                    history.get("room_id") == room_doc.id
                    and history.get("period") == bill.get("period")
                ):
                    existing = True
                    break
            if existing:
                bill_doc.reference.delete()
                continue

            now = datetime.now()
            archived = dict(bill)
            archived.update({
                "original_bill_id": bill_doc.id,
                "room_id": room_doc.id,
                "room_name": room_name,
                "status": status,
                "status_changed_at": bill.get("status_changed_at") or bill.get("paid_at") or bill.get("updated_at") or now,
                "archived_at": now,
                "archive_reason": status,
            })

            new_document_ref("bill_history").set(archived)
            bill_doc.reference.delete()
            moved += 1

    print(f"Migration complete. Archived {moved} terminal invoice(s).")


if __name__ == "__main__":
    main()
