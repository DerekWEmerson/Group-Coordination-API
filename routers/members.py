import classes as cl
import database
import helper_functions as hp

import sqlite3
from fastapi import APIRouter, HTTPException, status, Response, Depends

router = APIRouter()


# ==========================================
# MEMBERS
# ==========================================

@router.post("/groups/{group_id}/join")
def join_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.require_can_join_group(db_conn, requesting_participant_id, group_id)
    cursor = db_conn.cursor()
    try:
        if (hp.has_member_left(db_conn, group_id, requesting_participant_id) or hp.has_invite_pending(db_conn, group_id, requesting_participant_id)):
            cursor.execute("""
                UPDATE group_members
                SET pending_invite = 0,
                    joined_at = CURRENT_TIMESTAMP,
                    left_at = NULL
                WHERE group_id = ?
                    AND participant_id = ?
            """, (group_id, requesting_participant_id)
            )
        else:
            cursor.execute(
                """
                INSERT INTO group_members (group_id, participant_id, joined_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (group_id, requesting_participant_id)
            )

        db_conn.commit()

    except sqlite3.Error:
        db_conn.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Does not take invite code, remove else statement.
# Remember public groups, may keep this.
# NOT DONE

@router.post("/invite-links/{invite_token}/join", status_code=status.HTTP_201_CREATED)
def join_group_with_link(requesting_participant_id: int, invite_token: str, db_conn = Depends(database.get_db)):
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT
            id,
            group_id,
            created_by,
            expires_at IS NOT NULL
                AND expires_at <= CURRENT_TIMESTAMP AS is_expired,
            max_uses IS NOT NULL
                AND uses >= max_uses AS is_out_of_uses,
            max_uses IS NOT NULL
                AND uses + 1 >= max_uses AS is_final_use
        FROM group_invite_links
        WHERE invite_token = ?
    """, (invite_token,)
    )
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Invite link not found.")

    invite_link_id = row[0]
    group_id = row[1]
    created_by = row[2]
    is_expired = row[3]
    is_out_of_uses = row[4]
    is_final_use = row[5]

    if (is_expired or is_out_of_uses):
        try:
            cursor.execute("""
                DELETE FROM group_invite_links
                WHERE id = ?
            """, (invite_link_id,)
            )
            db_conn.commit()

        except sqlite3.Error:
            db_conn.rollback()
            raise

        if is_expired:
            raise HTTPException(status_code=404, detail="Invite link expired.")
        if is_out_of_uses:
            raise HTTPException(status_code=403, detail="Invite link has reached its maximum uses.")
    if hp.is_group_deleted(db_conn, group_id):
        raise HTTPException(status_code=404, detail=f"Group not found.")
    if hp.is_member(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is already a member of this group.")
    if hp.is_banned(db_conn, group_id, requesting_participant_id):
        if hp.is_group_hidden(db_conn, group_id):
            raise HTTPException(status_code=404, detail="Invite link not found.")
        raise HTTPException(status_code=403, detail="Participant is banned from this group.")
    if hp.is_group_archived(db_conn, group_id):
        raise HTTPException(status_code=404, detail="Invite link not found.")

    try:
        if hp.member_record_exists(db_conn, group_id, requesting_participant_id):
            cursor.execute("""
                UPDATE group_members
                SET invited_by = ?,
                    invited_at = CURRENT_TIMESTAMP,
                    pending_invite = 0,
                    joined_at = CURRENT_TIMESTAMP,
                    left_at = NULL
                WHERE group_id = ?
                    AND participant_id = ?
            """, (created_by, group_id, requesting_participant_id)
            )
        else:
            cursor.execute("""
                INSERT INTO group_members (
                    group_id,
                    participant_id,
                    invited_by,
                    invited_at,
                    joined_at
                )
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (group_id, requesting_participant_id, created_by)
            )

        # Increment uses by 1 or remove.
        if is_final_use:
            cursor.execute("""
                DELETE FROM group_invite_links
                WHERE id = ?
            """, (invite_link_id,)
            )
        else:
            cursor.execute("""
                UPDATE group_invite_links
                SET uses = uses + 1
                WHERE id = ?
            """, (invite_link_id,)
            )

        db_conn.commit()

    except sqlite3.Error:
        db_conn.rollback()
        raise

    return {"group_id": group_id, "participant_id": requesting_participant_id, "invited_by": created_by}
# NOT DONE


@router.post("/groups/{group_id}/invitations/{participant_id}", status_code=status.HTTP_201_CREATED)
def invite_group_participant(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    cursor = db_conn.cursor()
    if not hp.is_members_can_invite(db_conn, group_id):
        hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    if hp.is_member(db_conn, group_id, participant_id):
        raise HTTPException(status_code=403, detail="Participant is already a member of this group.")
    if hp.has_invite_pending(db_conn, group_id, participant_id):
        raise HTTPException(status_code=403, detail="Participant has already been invited to this group.")
    if hp.is_banned(db_conn, group_id, participant_id):
        if not hp.is_owner_or_admin(db_conn, group_id, requesting_participant_id):
            raise HTTPException(status_code=403, detail="Participant can not be invited to this group.")
        else:
            cursor.execute("""
                UPDATE banned_participants
                SET unbanned_by = ?,
                    unbanned_at = CURRENT_TIMESTAMP,
                    reason_for_unban = ?
                WHERE group_id = ?
                    AND participant_id = ?
                    AND unbanned_at IS NULL
            """, (
                requesting_participant_id,
                "Re-invited to group.",
                group_id,
                participant_id
                )
            )
    hp.require_member_or_admin(db_conn, group_id, requesting_participant_id)
    if hp.has_member_left(db_conn, group_id, participant_id):
        cursor.execute("""
            UPDATE group_members
            SET invited_at = CURRENT_TIMESTAMP,
                invited_by = ?,
                pending_invite = 1
            WHERE group_id = ?
                AND participant_id = ?
                AND left_at IS NOT NULL
        """, (requesting_participant_id, group_id, participant_id)
        )
    else:
        cursor.execute("""
            INSERT INTO group_members (
                group_id,
                participant_id,
                invited_at,
                invited_by,
                pending_invite
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, ?, 1)
        """, (group_id, participant_id, requesting_participant_id)
        )

    db_conn.commit()

    return {"group_id": group_id, "participant_id": participant_id, "invited_by": requesting_participant_id, "pending_invite": True}
# Done!


@router.post("/groups/{group_id}/members/{participant_id}")
def add_group_member(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    hp.require_admin(db_conn, requesting_participant_id)
    hp.require_not_banned(db_conn, group_id, participant_id)
    if hp.is_member(db_conn, group_id, participant_id):
        raise HTTPException(status_code=409, detail="Participant is already a member of this group.")
    
    cursor = db_conn.cursor()
    if hp.member_record_exists(db_conn, group_id, participant_id):
        cursor.execute("""
            UPDATE group_members
            SET pending_invite = 0,
                joined_at = CURRENT_TIMESTAMP,
                left_at = NULL
            WHERE group_id = ?
                AND participant_id = ?
        """, (group_id, participant_id)
        )
    else:
        cursor.execute("""
            INSERT INTO group_members (
                group_id,
                participant_id,
                joined_at
            )
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (group_id, participant_id)
        )

    db_conn.commit()
        
    return {"group_id": group_id, "participant_id": participant_id}
# Done!


@router.post("/groups/{group_id}/invitations/{participant_id}/accept")
def accept_group_invite(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    if not hp.is_self(requesting_participant_id, participant_id):
        raise HTTPException(status_code=403, detail="You may only perform this action on your own account.")
    if hp.is_member(db_conn, group_id, participant_id):
        raise HTTPException(status_code=409, detail="Participant is already a member of this group.")
    if not hp.has_invite_pending(db_conn, group_id, participant_id):
        raise HTTPException(status_code=404, detail="Pending invitation not found.")
    cursor = db_conn.cursor()
    cursor.execute("""
        UPDATE group_members
        SET pending_invite = 0,
            joined_at = CURRENT_TIMESTAMP,
            left_at = NULL
        WHERE group_id = ?
            AND participant_id = ?
            AND pending_invite = 1
    """, (group_id, participant_id)
    )

    db_conn.commit()
    return {"group_id": group_id, "participant_id": participant_id}
# Done!


@router.post("/groups/{group_id}/invitations/{participant_id}/reject")
def reject_group_invite(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    pass
    


@router.get("/groups/{group_id}/members")
def get_group_members(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
    )
    if hp.is_banned(db_conn, group_id, requesting_participant_id):
        if hp.is_group_hidden(db_conn, group_id):
            raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
        raise HTTPException(status_code=403, detail="Participant is banned from viewing this group.")
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT p.name
        FROM group_members AS gm
        JOIN participants AS p 
            ON gm.participant_id = p.id
        WHERE gm.group_id = ?
            AND gm.left_at IS NULL
            AND gm.pending_invite = 0
        """,
        (group_id,)
    )
    rows = cursor.fetchall()

    return [{"name": row[0]} for row in rows]
    # Could eventually return "joined_at" time as well for this.
# Done!


@router.get("/participants/{participant_id}/groups")
def get_participant_groups(requesting_participant_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        participant_id=participant_id, 
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    cursor = db_conn.cursor()
    if hp.is_admin(db_conn, requesting_participant_id):
        cursor.execute("""
            SELECT g.name, g.description, p.name
            FROM groups AS g 
            JOIN participants AS p 
                ON g.owner_id = p.id
            JOIN group_members AS gm
                ON g.id = gm.group_id 
            WHERE gm.participant_id = ?
                AND gm.left_at IS NULL
                AND gm.pending_invite = 0
            """,
            (participant_id,)
        )
    else:
        cursor.execute("""
            SELECT g.name, g.description, p.name
            FROM groups AS g 
            JOIN participants AS p 
                ON g.owner_id = p.id
            JOIN group_members AS gm
                ON g.id = gm.group_id 
            WHERE gm.participant_id = ?
                AND gm.left_at IS NULL
                AND gm.pending_invite = 0
                AND (
                    g.is_hidden = 0
                    OR EXISTS (
                        SELECT 1
                        FROM group_members AS requester_gm
                        WHERE requester_gm.group_id = g.id
                            AND requester_gm.participant_id = ?
                            AND requester_gm.left_at IS NULL
                    )
                )
            """,
            (participant_id, requesting_participant_id)
        )
    rows = cursor.fetchall()

    return [{"name": row[0], "description": row[1], "owner": row[2]} for row in rows]
# Done!



@router.delete("/groups/{group_id}/invitations/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
def uninvite_group_participant(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
    )
    if hp.is_member(db_conn, group_id, participant_id):
        raise HTTPException(status_code=404, detail="Participant does not have a pending invitation to this group.")
    if not hp.has_invite_pending(db_conn, group_id, participant_id):
        raise HTTPException(status_code=404, detail="Pending invitation not found.")
    if (not hp.is_inviter(db_conn, requesting_participant_id, group_id, participant_id) and not hp.is_owner_or_admin(db_conn, group_id, requesting_participant_id)):
        raise HTTPException(status_code=403, detail="Participant does not have permission to cancel this invitation.")
    cursor = db_conn.cursor()
    try:
        if hp.has_member_left(db_conn, group_id, participant_id):
            # Preserve the participant's old membership record.
            cursor.execute(
                """
                UPDATE group_members
                SET invited_at = NULL,
                    invited_by = NULL,
                    pending_invite = 0
                WHERE group_id = ?
                    AND participant_id = ?
                    AND pending_invite = 1
                """,
                (group_id, participant_id),
            )

        else:
            # This row exists because of the pending invitation so it can be removed completely.
            cursor.execute(
                """
                DELETE FROM group_members
                WHERE group_id = ?
                    AND participant_id = ?
                    AND pending_invite = 1
                """,
                (group_id, participant_id),
            )

        db_conn.commit()

    except sqlite3.Error:
        db_conn.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Done!


@router.delete("/groups/{group_id}/leave")
def leave_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id, 
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
    )
    if hp.has_member_left(db_conn, group_id, requesting_participant_id):
        if hp.is_group_hidden(db_conn, group_id):
            raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
        raise HTTPException(status_code=403, detail="Participant is not a member of this group.")
    if not hp.is_member(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is not a member of this group.")
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE group_members
        SET left_at = CURRENT_TIMESTAMP
        WHERE group_id = ?
            AND participant_id = ?
            AND left_at IS NULL
        """,
        (group_id, requesting_participant_id),
    )

    hp.delete_invite_tokens(db_conn, group_id, requesting_participant_id)

    db_conn.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Done!


@router.delete("/groups/{group_id}/members/{participant_id}")
def remove_group_participant(requesting_participant_id: int, group_id: int, participant_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        participant_id=participant_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id),
        can_view_participant=hp.is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id, participant_id),
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    if (hp.has_member_left(db_conn, group_id, participant_id) or not hp.is_member(db_conn, group_id, participant_id)):
        raise HTTPException(status_code=403, detail="Participant is not a member of this group.")
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE group_members
        SET left_at = CURRENT_TIMESTAMP
        WHERE group_id = ?
            AND participant_id = ?
            AND left_at IS NULL
        """,
        (group_id, participant_id),
    )

    hp.delete_invite_tokens(db_conn, group_id, participant_id)
    
    db_conn.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Done!
