import classes as cl
import database
import helper_functions as hp

import sqlite3
from fastapi import APIRouter, HTTPException, Depends

router = APIRouter()


# ==========================================
# MODERATION
# ==========================================

@router.post("/groups/{group_id}/bans/{participant_id}")
def ban_participant(requesting_participant_id: int, group_id: int, participant_id: int, ban: cl.BanCreate, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    if hp.is_banned(db_conn, group_id, participant_id):
        raise HTTPException(status_code=409, detail="Participant already banned from this group.")
    cursor = db_conn.cursor()
    try:
        cursor.execute("""
                INSERT INTO banned_participants (
                    group_id,
                    participant_id,
                    banned_by,
                    reason_for_ban
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    group_id,
                    participant_id,
                    requesting_participant_id,
                    ban.reason_for_ban,
                ),
            )

        ban_id = cursor.lastrowid

        # Set participant as having "left" group.
        cursor.execute("""
            UPDATE group_members
            SET left_at = CURRENT_TIMESTAMP
            WHERE group_id = ?
            AND participant_id = ?
            AND left_at IS NULL
        """, (
            group_id,
            participant_id
            )
        )

        # Delete all invite links created by the banned participant for this group.
        hp.delete_invite_tokens(db_conn, group_id, participant_id)

        db_conn.commit()
        
    except sqlite3.IntegrityError:
        db_conn.rollback()
        
        raise HTTPException(
            status_code=409,
            detail="Participant is already banned from this group."
        )

    return {
        "id": ban_id,
        "group_id": group_id,
        "banned_participant": participant_id,
        "banned_by": requesting_participant_id,
        "reason_for_ban": ban.reason_for_ban
    }
# Done!


# Participant Ban Endpoints
@router.get("/bans/{participant_id}")
def get_current_self_bans(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE p.id = ?
            AND unbanned_at IS NULL
    """, (participant_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4]} for row in rows]
# Done!


@router.get("/bans/{participant_id}/all-time")
def get_all_self_bans(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE p.id = ?
    """, (participant_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]} for row in rows]
# Done!


# Owner Ban Endpoints (See all bans for all groups you own)
@router.get("/bans/owned-groups/{participant_id}")
def get_current_owners_bans(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE g.owner_id = ?
            AND unbanned_at IS NULL
    """, (participant_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4]} for row in rows]
# Done!


@router.get("/bans/owned-groups/{participant_id}/all-time")
def get_all_owners_bans(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_self_or_admin(db_conn, requesting_participant_id, participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE g.owner_id = ?
    """, (participant_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]} for row in rows]
# Done!


# (Group-Specific Bans)
@router.get("/groups/{group_id}/bans")
def get_current_group_bans(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE 
            g.id = ?
            AND unbanned_at IS NULL
    """, (group_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4]} for row in rows]
# Done!


@router.get("/groups/{group_id}/bans/all-time")
def get_all_group_bans(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE 
            g.id = ?
    """, (group_id,)
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]} for row in rows]
# Done!


# (Member-Specific Bans)
@router.get("/groups/{group_id}/bans/{participant_id}")
def get_current_single_member_ban(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    if not hp.is_self_owner_or_admin(db_conn, group_id, requesting_participant_id, participant_id):
        raise HTTPException(status_code=403, detail="You may not perform this action on this participant's account.")
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE 
            g.id = ?
            AND p.id = ?
            AND unbanned_at IS NULL
    """, (group_id, participant_id)
    )
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No active ban found for this participant in this group."
        )

    return {"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4]}
# Done!


@router.get("/groups/{group_id}/participants/{participant_id}/bans/{ban_id}")
def get_any_single_member_ban(requesting_participant_id: int, group_id: int, participant_id: int, ban_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    if not hp.is_self_owner_or_admin(db_conn, group_id, requesting_participant_id, participant_id):
        raise HTTPException(status_code=403, detail="You may not perform this action on this participant's account.")
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban 
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE 
            b.id = ?
            AND g.id = ?
            AND p.id = ?
    """, (ban_id, group_id, participant_id)
    )
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Ban with ID {ban_id} not found."
        )

    return {"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]}


@router.get("/groups/{group_id}/bans/{participant_id}/all-time")
def get_all_single_member_bans(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    if not hp.is_self_owner_or_admin(db_conn, group_id, requesting_participant_id, participant_id):
        raise HTTPException(status_code=403, detail="You may not perform this action on this participant's account.")
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban 
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE 
            g.id = ?
            AND p.id = ?
        """, (group_id, participant_id)
    )
    rows = cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No bans found for this participant in this group."
        )

    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]} for row in rows]
# Done!


# Admin Ban Endpoints
@router.get("/bans")
def get_current_bans(requesting_participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_admin(db_conn, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        JOIN groups AS g
            ON b.group_id = g.id
        WHERE unbanned_at IS NULL
        """
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4]} for row in rows]
# Done!


@router.get("/bans/all-time")
def get_all_bans(requesting_participant_id: int, db_conn = Depends(database.get_db)):
    hp.require_admin(db_conn, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT g.name, p.username, banner.username, b.banned_at, b.reason_for_ban, unbanner.username, b.unbanned_at, b.reason_for_unban
        FROM banned_participants AS b
        JOIN participants AS p
            ON b.participant_id = p.id
        LEFT JOIN participants AS banner
            ON b.banned_by = banner.id
        LEFT JOIN participants AS unbanner
            ON b.unbanned_by = unbanner.id
        JOIN groups AS g
            ON b.group_id = g.id
        """
    )
    rows = cursor.fetchall()
    return [{"group": row[0], "banned_participant": row[1], "banned_by": row[2], "banned_at": row[3], "reason_for_ban": row[4], "unbanned_by": row[5], "unbanned_at": row[6], "reason_for_unban": row[7]} for row in rows]
# Done!


@router.patch("/groups/{group_id}/participants/{participant_id}/bans/{ban_id}")
def edit_ban_message(requesting_participant_id: int, group_id: int, participant_id: int, ban_id: int, ban: cl.BanEdit, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT unbanned_at
        FROM banned_participants
        WHERE id = ?
            AND group_id = ?
            AND participant_id = ?
    """, (
        ban_id,
        group_id,
        participant_id
        )
    )

    row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Ban with ID {ban_id} not found.")
    if ban.is_unban_reason:
        if row[0] is None:
            raise HTTPException(status_code=409, detail="This ban has not been unbanned.")
        cursor.execute("""
            UPDATE banned_participants
            SET reason_for_unban = ?
            WHERE id = ?
        """, (
            ban.reason,
            ban_id
            )
        )
    else:
        cursor.execute("""
            UPDATE banned_participants
            SET reason_for_ban = ?
            WHERE id = ?
        """, (
            ban.reason,
            ban_id
            )
        )

    db_conn.commit()

    return get_any_single_member_ban(requesting_participant_id, group_id, participant_id, ban_id, db_conn)
# Done!


@router.delete("/groups/{group_id}/participants/{participant_id}/bans/{ban_id}")
def unban_participant(
    requesting_participant_id: int, group_id: int, participant_id: int, ban_id: int, ban: cl.BanRemove, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        UPDATE banned_participants
        SET unbanned_by = ?,
            unbanned_at = CURRENT_TIMESTAMP,
            reason_for_unban = ?
        WHERE id = ?
            AND group_id = ?
            AND participant_id = ?
            AND unbanned_at IS NULL
    """, (
        requesting_participant_id,
        ban.reason_for_unban,
        ban_id,
        group_id,
        participant_id
    ))

    if cursor.rowcount == 0:
        db_conn.rollback()
        raise HTTPException(
            status_code=404,
            detail=f"Active ban with ID {ban_id} not found."
        )

    db_conn.commit()

    return get_any_single_member_ban(requesting_participant_id, group_id, participant_id, ban_id, db_conn)
