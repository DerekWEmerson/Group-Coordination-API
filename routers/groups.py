import classes as cl
import database
import helper_functions as hp

import sqlite3
from fastapi import APIRouter, HTTPException, status, Response, Depends

router = APIRouter()


# ==========================================
# GROUPS
# ==========================================

@router.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(requesting_participant_id: int, group: cl.GroupCreate, db_conn = Depends(database.get_db)):
    if group.is_hidden: 
        group.invite_only = True # Don't forget to force invite_only = true if is_hidden = true on the front end.
    # invite_code = (hp.generate_invite_code(db_conn) if group.invite_only else None) # Generates a random invite code
    cursor = db_conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO groups (
                name,
                description,
                owner_id,
                invite_only,
                is_hidden,
                members_can_invite,
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                group.name,
                group.description,
                requesting_participant_id,
                group.invite_only,
                group.is_hidden,
                group.members_can_invite,
            )
        )

        cursor.execute("""
            INSERT INTO group_members (group_id, participant_id)
            VALUES (?, ?)
        """, (group_id, requesting_participant_id)
        )

        if group.invite_only == True:

            cursor.execute("""
                INSERT INTO group_invites (
                    name,
                    description,
                    owner_id,
                    invite_only,
                    is_hidden,
                    members_can_invite,
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    group.name,
                    group.description,
                    requesting_participant_id,
                    group.invite_only,
                    group.is_hidden,
                    group.members_can_invite,
                )
            )

        db_conn.commit()

    except sqlite3.IntegrityError:
        db_conn.rollback()

        raise HTTPException(
            status_code=409,
            detail="The group could not be created because its data conflicts with the database."
        )

    group_id = cursor.lastrowid

    return {
        "id": group_id,
        "name": group.name,
        "description": group.description,
        "owner_id": requesting_participant_id,
        "invite_only": group.invite_only,
        "is_hidden": group.is_hidden,
        "members_can_invite": group.members_can_invite,
    }
    # Don't forget to force invite_only = true if is_hidden = true on the front end.
# Must update "invite_code" function to "create_invite_link" function.
# NOT DONE


@router.get("/groups")
def get_groups(requesting_participant_id: int, db_conn = Depends(database.get_db)):
    cursor = db_conn.cursor()
    if hp.is_admin(db_conn, requesting_participant_id):
        cursor.execute("""
            SELECT g.name, g.description, p.name 
            FROM groups AS g 
            JOIN participants AS p 
                ON g.owner_id = p.id
        """)
    else:
        cursor.execute("""
            SELECT g.name, g.description, p.name 
            FROM groups AS g 
            JOIN participants AS p 
                ON g.owner_id = p.id
            WHERE g.deleted_at IS NULL
                AND (
                    g.is_hidden = 0
                    OR EXISTS (
                        SELECT 1
                        FROM group_members AS gm
                        WHERE gm.group_id = g.id
                            AND gm.participant_id = ?
                            AND (
                                gm.left_at IS NULL
                                OR gm.pending_invite = 1
                            )
                    )
                )
            """, 
            (requesting_participant_id,)
        ) # This is going through each group and checking if they're not hidden or if you're a member of or invited to said group.
    rows = cursor.fetchall()
    return [{"name": row[0], "description": row[1], "owner": row[2]} for row in rows]
# Done!


@router.get("/groups/{group_id}")
def get_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    # cursor = db_conn.cursor()
    # if hp.is_owner_or_admin(db_conn, group_id, requesting_participant_id):
    #     # Cannot use normal "status_check" as this allows previous owners and admin to view deleted groups.
    #     cursor.execute("""
    #         SELECT 1 
    #         FROM groups 
    #         WHERE id = ?
    #         """, (group_id,)
    #     )
    #     if cursor.fetchone() is None:
    #         raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
    #     cursor.execute("""
    #         SELECT g.name, g.description, p.name, g.invite_only, g.is_hidden, g.members_can_invite, g.archived_at
    #         FROM groups AS g 
    #         JOIN participants AS p 
    #             ON g.owner_id = p.id
    #     """, (group_id,)
    #     )
    #     row = cursor.fetchone()
    #     result = {
    #         "name": row[0],
    #         "description": row[1],
    #         "owner": row[2],
    #         "invite_only": row[3],
    #         "is_hidden": row[4],
    #         "members_can_invite": row[5],
    #         "archived_at": row[6]
    #     }

    #     if row[7] is not None:
    #         result["deleted_at"] = row[7]

    #     return result


    #     return {"name": row[0], "description": row[1], "owner": row[2]}
    # else:
    #     hp.status_check(
    #         db_conn,
    #         group_id=group_id,
    #         can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
    #     )
    #     cursor.execute("""
    #         SELECT g.name, g.description, p.name, g.invite_only, g.is_hidden, g.members_can_invite, g.archived_at
    #         FROM groups AS g 
    #         JOIN participants AS p 
    #             ON g.owner_id = p.id
    #     """, (group_id,)
    #     )
    pass
        
# Also select "archived_at"
# NOT DONE


@router.patch("/groups/{group_id}")
def edit_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    cursor = db_conn.cursor()
    pass
    # Needs Authentication (Either admin or requesting_participant_id = owner_id)

    # What are you editing? Need separate ones for name, description, hidden, invite?
# NOT DONE


@router.post("/groups/{group_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
            db_conn,
            group_id=group_id,
            can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
        )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    if hp.is_group_archived(db_conn, group_id):
        raise HTTPException(
            status_code=409,
            detail=f"Group with ID {group_id} is already archived."
        )
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE groups
        SET archived_at = CURRENT_TIMESTAMP
        WHERE id = ?
            AND archived_at IS NULL
        """,
        (group_id,),
    )

    

    db_conn.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Done!


@router.post("/groups/{group_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
def unarchive_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
            db_conn,
            group_id=group_id,
            can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
        )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    if not hp.is_group_archived(db_conn, group_id):
        raise HTTPException(
            status_code=409,
            detail=f"Group with ID {group_id} is already unarchived."
        )
    cursor = db_conn.cursor()
    cursor.execute(
        """
        UPDATE groups
        SET archived_at = NULL
        WHERE id = ?
            AND archived_at IS NOT NULL
        """,
        (group_id,),
    )
    db_conn.commit()
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)
# Done!


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    hp.status_check(
        db_conn,
        group_id=group_id,
        can_view_group=hp.is_member_invited_or_admin(db_conn, group_id, requesting_participant_id)
    )
    hp.require_owner_or_admin(db_conn, group_id, requesting_participant_id)
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            """
            UPDATE groups
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = ?
                AND deleted_at IS NULL
            """,
            (group_id,),
        )

        db_conn.commit()
    
    except sqlite3.Error:
        db_conn.rollback()
        raise

    return Response(status_code=status.HTTP_204_NO_CONTENT)
    # Need a 2 step process for this on the front end ("are you sure" button)
# Done!


# ==========================================
# INVITE LINKS
# ==========================================

@router.post("/groups/{group_id}/invite-links")
def create_invite_link(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    if hp.is_group_archived(db_conn, group_id):
        raise HTTPException(status_code=404, detail="Invite link not found.")
    pass

    # Make sure only owners and admin (or members if allowed) can make links for a group, do not let invited or banned members do so.
    # How to have specific times for each link, like set amount of uses, set amount of time, or infinite? (Class?)
    # Cannot create if group is deleted or archived.
    # generate_invite_token() (How to make this into a link?)

@router.get("/participant/{participant_id}/invite-links") # Lists all owner's groups' links.
def get_owner_invite_links(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    pass
    # Cannot get if group is deleted or archived.

@router.get("/groups/{group_id}/invite-links") # Lists all of a single groups' links.
def get_group_invite_links(requesting_participant_id: int, group_id: int, db_conn = Depends(database.get_db)):
    pass

@router.get("/groups/{group_id}/invite-links/{invite_link_id}") # Lists a specific invite links.
def get_invite_link(requesting_participant_id: int, group_id: int, invite_link_id: str, db_conn = Depends(database.get_db)):
    pass

@router.patch("/groups/{group_id}/invite-links/{invite_link_id}") # Change your main group-invite link.
def edit_invite_link(requesting_participant_id: int, group_id: int, invite_link_id: str, db_conn = Depends(database.get_db)):
    pass
    # Cannot edit if group is deleted or archived.
    # Don't need a class, just re-run the same helper function.
    # generate_invite_token()


@router.delete("/groups/{group_id}/invite-links/{invite_link_id}")
def delete_invite_link(requesting_participant_id: int, group_id: int, invite_link_id: str, db_conn = Depends(database.get_db)):
    pass