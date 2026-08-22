import classes as cl
import database
import helper_functions as hp

import sqlite3
from fastapi import APIRouter, HTTPException, status, Response, Depends

router = APIRouter()


# ==========================================
# PARTICIPANTS
# ==========================================

@router.post("/participants", status_code=status.HTTP_201_CREATED)
def create_participant(participant: cl.ParticipantCreate, db_conn = Depends(database.get_db)):
    cursor = db_conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO participants (
                username,
                name,
                bio,
                timezone,
                is_hidden
            )
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                participant.username,
                participant.name,
                participant.bio,
                participant.timezone,
                participant.is_hidden,
            ),
        )
        db_conn.commit()

    except sqlite3.IntegrityError:
        db_conn.rollback()
        
        raise HTTPException(
            status_code=409,
            detail="That username is already in use or the participant data is invalid."
        )

    participant_id = cursor.lastrowid

    return {
        "id": participant_id,
        "username": participant.username,
        "name": participant.name,
        "timezone": participant.timezone,
        "is_hidden": participant.is_hidden,
        "is_admin": False,
    }
# Eventually need to require length of username to be more than 3 characters long.
# Need password


@router.get("/participants")
def get_participants(requesting_participant_id: int, db_conn = Depends(database.get_db)):
    cursor = db_conn.cursor()
    if hp.is_admin(db_conn, requesting_participant_id):
        cursor.execute("""
            SELECT
                username,
                name, 
                timezone, 
                is_hidden,
                is_admin,
                deleted_at
            FROM participants
            """
        )
        rows = cursor.fetchall()
        return [{"username": row[0], "name": row[1], "timezone": row[2], "is_hidden": row[3], "is_admin": row[4], "deleted_at": row[5]} for row in rows]
    else:
        cursor.execute("""
            SELECT name, timezone
            FROM participants AS p
            WHERE p.deleted_at IS NULL
                AND (
                    p.is_hidden = 0
                    OR p.id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM friends AS f
                        WHERE f.pending = 0
                            AND (
                                (f.requester_id = ? AND f.recipient_id = p.id)
                                OR (f.recipient_id = ? AND f.requester_id = p.id)
                            )
                    )
                )
        """, (
            requesting_participant_id,
            requesting_participant_id,
            requesting_participant_id
        ))
        rows = cursor.fetchall()
        return [{"name": row[0], "timezone": row[1]} for row in rows]
# Remove/alter if making this a public web app.


@router.get("/participants/{participant_id}")
def get_participant(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn, 
        participant_id=participant_id, 
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    cursor = db_conn.cursor()
    cursor.execute("SELECT name, timezone FROM participants WHERE id = ?", (participant_id,))
    row = cursor.fetchone()

    return {"name": row[0], "timezone": row[1]}
    

@router.patch("/participants/{participant_id}") # Used because any column could be changed, not specified like Post.
def edit_participant(requesting_participant_id: int, participant_id: int, changes: cl.ParticipantEdit, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        participant_id=participant_id, 
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    provided_changes = changes.model_dump(exclude_unset=True)

    cursor = db_conn.cursor()

    if not provided_changes:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    if "is_hidden" in provided_changes:
        provided_changes["is_hidden"] = int(provided_changes["is_hidden"])

    set_statements = []
    values = []

    for field, value in provided_changes.items():
        set_statements.append(f"{field} = ?")
        values.append(value)

    values.append(participant_id)

    query = (f"""
        UPDATE participants
        SET {", ".join(set_statements)}
        WHERE id = ?
    """)

    try:
        cursor.execute(query, values)
        db_conn.commit()

    except sqlite3.IntegrityError:
        db_conn.rollback()
        raise HTTPException(
            status_code=409,
            detail="That username is already in use."
        )

    cursor.execute(
        """
        SELECT
            id,
            username,
            name,
            timezone,
            is_hidden,
            is_admin
        FROM participants
        WHERE id = ?
        """,
        (participant_id,),
    )

    row = cursor.fetchone()

    return {
        "id": row[0],
        "username": row[1],
        "name": row[2],
        "timezone": row[3],
        "is_hidden": bool(row[4]),
        "is_admin": bool(row[5]),
    }


@router.delete("/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_participant(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        participant_id=participant_id, 
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE participants
        SET deleted_at = CURRENT_TIMESTAMP
        WHERE id = ?
            AND deleted_at IS NULL
        """,
        (participant_id,),
    )
    cursor.execute(
        """
        UPDATE groups
        SET deleted_at = CURRENT_TIMESTAMP,
            deleted_by_owner_deletion = 1
        WHERE owner_id = ?
            AND deleted_at IS NULL
        """,
        (participant_id,),
    )

    # Remove all invite tokens made by participant for all groups.
    hp.delete_all_participant_invite_tokens(db_conn, participant_id)

    db_conn.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Will require password.


@router.post("/participants/{participant_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_participant(participant_id: int, db_conn = Depends(database.get_db)): # Eventually require a username and password input.
    if not hp.participant_record_exists(db_conn, participant_id):
        raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found.")
    if not hp.is_participant_deleted(db_conn, participant_id):
        if hp.is_participant_hidden(db_conn, participant_id):
            raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found.")
        raise HTTPException(status_code=409, detail=f"Participant with ID {participant_id} is already active.")
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE participants
        SET deleted_at = NULL
        WHERE id = ?
            AND deleted_at IS NOT NULL
        """,
        (participant_id,),
    )
    cursor.execute(
        """
        UPDATE groups
        SET deleted_at = NULL,
            deleted_by_owner_deletion = 0
        WHERE owner_id = ?
            AND deleted_at IS NOT NULL
            AND deleted_by_owner_deletion = 1
        """,
        (participant_id,),
    )

    db_conn.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Will require password.

