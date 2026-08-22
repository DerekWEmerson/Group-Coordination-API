from fastapi import HTTPException
import secrets
import string

# ==========================================
# CHECKS AND REQUIREMENTS FUNCTIONS
# ==========================================

# Status Checks
def status_check(
        db_conn, 
        group_id: int = None, 
        participant_id: int = None,
        recurring_availability_id: int = None,
        specific_availability_id: int = None,
        can_view_group: bool = False, 
        can_view_participant: bool = False
    ) -> None:
    if group_id is not None:
        group_exists(db_conn, group_id)
        if (is_group_hidden(db_conn, group_id) and not can_view_group) or is_group_deleted(db_conn, group_id):
            raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
    if participant_id is not None:
        participant_exists(db_conn, participant_id)
        if (is_participant_hidden(db_conn, participant_id) and not can_view_participant) or is_participant_deleted(db_conn, participant_id):
            raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found.")
    if recurring_availability_id is not None:
        recurring_availability_exists(db_conn, recurring_availability_id)
    if specific_availability_id is not None:
        specific_availability_exists(db_conn, specific_availability_id)


def require_can_join_group(db_conn, requesting_participant_id: int, group_id: int) -> None:
    group_exists(db_conn, group_id)
    if is_member(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is already a member of this group.")
    if is_group_hidden(db_conn, group_id):
        if (is_banned(db_conn, group_id, requesting_participant_id) or is_group_archived(db_conn, group_id)):
            raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
        if not has_invite_pending(db_conn, group_id, requesting_participant_id):
            raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")
        return
    if is_group_archived(db_conn, group_id):
        raise HTTPException(status_code=404, detail=f"Group with ID {group_id} has been archived.")
    if is_banned(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is banned from this group.")
    if is_invite_only(db_conn, group_id):
        if not has_invite_pending(db_conn, group_id, requesting_participant_id):
            raise HTTPException(status_code=403, detail="Invalid invite code.")


# Participants
def participant_exists(db_conn, participant_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM participants 
        WHERE id = ?
            AND deleted_at IS NULL
        """, (participant_id,)
    )

    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found.")


def is_participant_hidden(db_conn, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT is_hidden FROM participants WHERE id = ?", (participant_id,))
    row = cursor.fetchone()
    
    return bool(row[0])


def is_participant_deleted(db_conn, participant_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT deleted_at FROM participants WHERE id = ?", (participant_id,))
    row = cursor.fetchone()

    return row[0] is not None


def participant_record_exists(db_conn, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT 1 FROM participants WHERE id = ?", (participant_id,))

    return cursor.fetchone() is not None


# Self
def is_self(requesting_participant_id: int, participant_id: int) -> bool:
    return requesting_participant_id == participant_id


def is_self_or_admin(db_conn, requesting_participant_id: int, participant_id: int) -> bool:
    return (requesting_participant_id == participant_id or is_admin(db_conn, requesting_participant_id))


def is_self_friend_or_admin(db_conn, requesting_participant_id: int, participant_id: int) -> bool:
    return (are_friends(db_conn, requesting_participant_id, participant_id) or is_self_or_admin(db_conn, requesting_participant_id, participant_id))


# def is_self_member_friend_or_admin(db_conn, group_id: int, requesting_participant_id: int, participant_id: int) -> bool:
#     if (is_self_or_admin(db_conn, requesting_participant_id) or are_friends(db_conn, requesting_participant_id, participant_id)):
#         return True
#     return (is_member(db_conn, group_id, requesting_participant_id) and is_member(db_conn, group_id, participant_id))
# Meant for checking Group Participants. Checks if the requester is a friend or admin, or if BOTH participants are members of the same group.


def is_self_friend_sharedgroup_or_admin(db_conn, requesting_participant_id: int, participant_id: int) -> bool:
    return (is_self_or_admin(db_conn, requesting_participant_id) or are_friends(db_conn, requesting_participant_id, participant_id) or is_sharedgroup(db_conn, requesting_participant_id, participant_id))
# Checks if the requester is a friend or admin, or if BOTH participants are members of the same group (any group).


def is_self_owner_or_admin(db_conn, group_id: int, requesting_participant_id: int, participant_id: int) -> bool:
    return (is_owner(db_conn, group_id, requesting_participant_id) or is_self_or_admin(db_conn, requesting_participant_id, participant_id))


def require_self_or_admin(db_conn, requesting_participant_id: int, participant_id: int) -> None:
    if not is_self_or_admin(db_conn, requesting_participant_id, participant_id):
        raise HTTPException(status_code=403, detail="You may only perform this action on your own account.")


def require_self_friend_or_admin(db_conn, requesting_participant_id, participant_id):
    if not is_self_or_admin(db_conn, requesting_participant_id, participant_id):
        if not are_friends(db_conn, requesting_participant_id, participant_id):
            raise HTTPException(status_code=403, detail="You may only perform this action on your own account or a friend's account.")


# Friends
def are_friends(db_conn, requesting_participant_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1
        FROM friends
        WHERE pending = 0
            AND (
                (requester_id = ? AND recipient_id = ?)
                OR
                (requester_id = ? AND recipient_id = ?)
            )
    """, (requesting_participant_id, participant_id, participant_id, requesting_participant_id)
    )

    return cursor.fetchone() is not None


# Groups
def group_exists(db_conn, group_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM groups 
        WHERE id = ?
            AND deleted_at IS NULL
        """, (group_id,)
        )

    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Group with ID {group_id} not found.")


def is_group_hidden(db_conn, group_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT is_hidden FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()

    return bool(row[0])


def is_group_archived(db_conn, group_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT archived_at FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()

    return row[0] is not None


def is_group_deleted(db_conn, group_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT deleted_at FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()

    return row[0] is not None


# Member
def is_member(db_conn, group_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM group_members 
        WHERE group_id = ? 
            AND participant_id = ?
            AND pending_invite = 0
            AND joined_at IS NOT NULL
            AND left_at IS NULL
    """, (group_id, participant_id)
    )

    return cursor.fetchone() is not None


def has_member_left(db_conn, group_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT left_at FROM group_members WHERE group_id = ? AND participant_id = ?", (group_id, participant_id))
    row = cursor.fetchone()

    return row[0] is not None


def member_record_exists(db_conn, group_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM group_members 
        WHERE group_id = ? 
            AND participant_id = ?
        """, (group_id, participant_id)
    )

    return cursor.fetchone() is not None


def is_member_or_admin(db_conn, group_id: int, participant_id: int) -> bool:
    return (is_admin(db_conn, participant_id) or is_member(db_conn, group_id, participant_id))
# Meant for checking Groups.


def is_member_invited_or_admin(db_conn, group_id: int, participant_id: int) -> bool:
    return (
        is_admin(db_conn, participant_id) 
        or has_invite_pending(db_conn, group_id, participant_id) 
        or is_member(db_conn, group_id, participant_id)
    )
# Meant for checking Groups, including invited members.


def require_member_or_admin(db_conn, group_id: int, requesting_participant_id: int) -> None:
    if not is_member_or_admin(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is not a member of this group.")



# SharedGroup
def is_sharedgroup(db_conn, requesting_participant_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM group_members AS gm1
            JOIN group_members AS gm2
                ON gm1.group_id = gm2.group_id
            WHERE gm1.participant_id = ?
                AND gm2.participant_id = ?
                AND gm1.left_at IS NULL
                AND gm2.left_at IS NULL
        )
    """, (requesting_participant_id, participant_id))

    return bool(cursor.fetchone()[0])
    # Specifically doesn't filter out hidden members to advise and protect new members from joining someone they avoid.



# Owner
def is_owner(db_conn, group_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT owner_id FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()
    
    return row[0] == participant_id


def is_owner_or_admin(db_conn, group_id: int, participant_id: int) -> bool:
    return (is_admin(db_conn, participant_id) or is_owner(db_conn, group_id, participant_id))


def require_owner_or_admin(db_conn, group_id: int, requesting_participant_id: int) -> None:
    if not is_owner_or_admin(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Only the group owner or an administrator may perform this action.")


# Banned
def is_banned(db_conn, group_id: int, participant_id: int) -> bool:
    participant_exists(db_conn, participant_id)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM banned_participants
        WHERE group_id = ? 
            AND participant_id = ?
            AND unbanned_at IS NULL
        """, (group_id, participant_id)
    )

    return cursor.fetchone() is not None


def require_not_banned(db_conn, group_id: int, requesting_participant_id: int) -> None:
    if is_banned(db_conn, group_id, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Participant is banned from this group.")


# Admin
def is_admin(db_conn, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT is_admin FROM participants WHERE id = ?", (participant_id,))
    row = cursor.fetchone()

    return bool(row[0])


def require_admin(db_conn, requesting_participant_id: int) -> None:
    if not is_admin(db_conn, requesting_participant_id):
        raise HTTPException(status_code=403, detail="Administrator permission required.")


# Availability
def recurring_availability_exists(db_conn, availability_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT 1 FROM recurring_availability WHERE id = ?", (availability_id,))

    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Recurring Availability with ID {availability_id} not found.")
    

def specific_availability_exists(db_conn, availability_id: int) -> None:
    cursor = db_conn.cursor()
    cursor.execute("SELECT 1 FROM specific_availability WHERE id = ?", (availability_id,))

    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Specific Availability with ID {availability_id} not found.")


# Invites
def is_invite_only(db_conn, group_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT invite_only FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()

    return bool(row[0])


def is_members_can_invite(db_conn, group_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("SELECT members_can_invite FROM groups WHERE id = ?", (group_id,))
    row = cursor.fetchone()

    return bool(row[0])


# def check_invite_code(db_conn, group_id: int, invite_code: str) -> bool:
#     cursor = db_conn.cursor()
#     cursor.execute("SELECT invite_code FROM groups WHERE id = ?", (group_id,))
#     row = cursor.fetchone()

#     return row[0] == invite_code


def has_invite_pending(db_conn, group_id: int, participant_id: int):
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT 1 
        FROM group_members 
        WHERE group_id = ?
            AND participant_id = ?
            AND pending_invite = 1
        """, (group_id, participant_id)
    )

    return cursor.fetchone() is not None


def is_inviter(db_conn, requesting_participant_id: int, group_id: int, participant_id: int) -> bool:
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT invited_by 
        FROM group_members 
        WHERE group_id = ?
            AND participant_id = ?
    """, (group_id, participant_id,))
    row = cursor.fetchone()

    return row is not None and row[0] == requesting_participant_id


# ==========================================
# AVAILABILITY HELPER FUNCTIONS
# ==========================================


"""
fetch_participant_recurring_availability
fetch_participant_specific_availability

fetch_participant_group_recurring_availability
fetch_participant_group_specific_availability

fetch_group_recurring_availability
fetch_group_specific_availability
"""

# @app.get("/participants/{participant_id}/recurring-availability") # See all recurring availability or unavailability for self or friend across all groups.
# def get_general_recurring_availability(requesting_participant_id: int, participant_id: int):
#     hp.status_check(
#         db_conn, 
#         participant_id=participant_id, 
#         can_view_participant=hp.is_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
#     )
#     hp.require_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
#     cursor = db_conn.cursor()
#     cursor.execute("""

#         """
#     )
#     rows = cursor.fetchall()
#     pass
# # Need query to exclude group info if friend and not self or admin.
# ?

# @app.get("/participants/{participant_id}/specific-availability") # See all specific availability or unavailability for self or friend across all groups.
# def get_general_specific_availability(requesting_participant_id: int, participant_id: int):
#     hp.require_self_friend_or_admin(db_conn, requesting_participant_id, participant_id)
#     pass
# # Need query to exclude group info if friend and not self or admin.





# @app.get("/groups/{group_id}/participants/{participant_id}/recurring-availability") # See all recurring availability or unavailability for self or another member in one group.
# def get_participant_group_recurring_availability(requesting_participant_id: int, group_id: int, participant_id: int):
#     hp.status_check(
#         db_conn,
#         group_id=group_id,
#         participant_id=participant_id,
#         can_view_group=hp.is_member_or_admin(db_conn, group_id, requesting_participant_id), 
#         can_view_participant=hp.is_member_friend_or_admin(db_conn, requesting_participant_id, participant_id)
#     )
#     hp.is_member_or_admin(db_conn, group_id, requesting_participant_id)
#     if not hp.is_member(db_conn, group_id, participant_id): # Checks if participant is in group.
#         raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not in group with ID {group_id}")
#     cursor = db_conn.cursor()
#     cursor.execute("""
#         SELECT 
#             g.name, 
#             p.name, 
#             ga.weekday, 
#             ga.start_time, 
#             ga.end_time, 
#             ga.end_day_offset, 
#             ga.is_available, 
#             ga.group_id
#         FROM recurring_availability as ga
#         LEFT JOIN groups AS g
#             ON ga.group_id = g.id
#         JOIN participants AS p
#             ON ga.participant_id = p.id
#         WHERE ga.participant_id = ?
#             AND (ga.group_id = ? OR ga.group_id IS NULL)
#     """, (participant_id, group_id)
#     )
#     rows = cursor.fetchall()
#     return [
#         {
#         "group": row[0], 
#         "participant": row[1], 
#         "day": row[2], 
#         "start_time": row[3], 
#         "end_time": row[4], 
#         "end_day_offset": row[5], 
#         "is_available": row[6], 
#         "scope": "all_groups" if row[7] is None else "group" # For distinguishing between group-avail and general-avail (will show both in this query)
#         } for row in rows
#     ]





# @app.get("/groups/{group_id}/participants/{participant_id}/specific-availability") # See all specific availability or unavailability for self or another member in one group.
# def get_participant_group_specific_availability(requesting_participant_id: int, group_id: int, participant_id: int):
#     hp.status_check(
#         db_conn,
#         group_id=None,
#         participant_id=None,
#         recurring_availability_id=None,
#         specific_availability_id=None,
#         can_view_group=False,
#         can_view_participant=False
#     )
#     hp.require_member_or_admin(db_conn, group_id, requesting_participant_id)
#     hp.participant_exists(db_conn, participant_id)
#     if hp.is_participant_hidden(db_conn, participant_id):
#         if not (
#             hp.is_self_or_admin(db_conn, requesting_participant_id, participant_id)
#             or hp.is_owner(db_conn, group_id, requesting_participant_id)
#         ):
#             raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not found")
#     if not hp.is_member(db_conn, group_id, participant_id):
#         raise HTTPException(status_code=404, detail=f"Participant with ID {participant_id} not in group with ID {group_id}")
#     cursor = db_conn.cursor()
#     cursor.execute("""
#         SELECT g.name, p.name, sa.start_datetime, sa.end_datetime, sa.is_available
#         FROM specific_availability as sa
#         LEFT JOIN groups AS g
#             ON sa.group_id = g.id
#         JOIN participants AS p
#             ON sa.participant_id = p.id
#         WHERE sa.participant_id = ?
#             AND (sa.group_id = ? OR sa.group_id IS NULL)
#     """, (participant_id, group_id)
#     )
#     rows = cursor.fetchall()
#     return [{"group": row[0], "participant": row[1], "start_datetime": row[2], "end_datetime": row[3], "is_available": row[4]} for row in rows]







# @app.get("/groups/{group_id}/recurring-availability") # See all recurring availability or unavailability for all group members.
# def get_group_recurring_availability(requesting_participant_id: int, group_id: int):
#     hp.status_check(
#         db_conn,
#         group_id=group_id,
#         can_view_group=hp.is_member_or_admin(db_conn, group_id, requesting_participant_id),
#     )
#     hp.require_member_or_admin(db_conn, group_id, requesting_participant_id)
#     pass
# ?



# @app.get("/groups/{group_id}/specific-availability") # See all specific availability or unavailability for all group members.
# def get_group_specific_availability(requesting_participant_id: int, group_id: int):
#     hp.status_check(
#         db_conn,
#         group_id=group_id,
#         participant_id=participant_id,
#         specific_availability_id=availability_id,
#         can_view_group=hp.is_member_or_admin(db_conn, group_id, requesting_participant_id),
#         can_view_participant=hp.is_member_friend_or_admin(db_conn, requesting_participant_id, participant_id)
#     )
#     hp.require_member_or_admin(db_conn, requesting_participant_id, participant_id)
#     pass


# ==========================================
# USERNAMES
# ==========================================

def convert_username_to_id(db_conn, username):
    check_username(db_conn, username)
    cursor = db_conn.cursor()
    cursor.execute("SELECT id FROM participants WHERE username = ?", (username,))
    row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Participant with username {username} not found.")

    return {"username": row[0]}

# Checks for username existing at the same time.
# Convert all "participant_exists" function calls and "participant_id" parameters in main.py to this function and "username".



# ==========================================
# INVITE LINKS
# ==========================================


def generate_invite_token() -> str:
    return secrets.token_urlsafe(24)


# def is_invite_expired(db_conn, invite_token: str) -> bool:
#     cursor = db_conn.cursor()
#     cursor.execute("""
#         SELECT 1
#         FROM group_invite_links
#         WHERE invite_token = ?
#         AND expires_at IS NOT NULL
#         AND expires_at <= CURRENT_TIMESTAMP
#     """, (invite_token,))

#     return cursor.fetchone() is not None


def delete_invite_tokens(db_conn, group_id: int, participant_id: int) -> None:
        cursor = db_conn.cursor()
        cursor.execute("""
            DELETE FROM group_invite_links
            WHERE group_id = ?
            AND created_by = ?
        """, (group_id, participant_id)
        )


def delete_all_participant_invite_tokens(db_conn, participant_id: int) -> None:
        cursor = db_conn.cursor()
        cursor.execute("""
            DELETE FROM group_invite_links
            WHERE created_by = ?
        """, (participant_id,)
        )


def delete_all_group_invite_tokens(db_conn, group_id: int) -> None:
        cursor = db_conn.cursor()
        cursor.execute("""
            DELETE FROM group_invite_links
            WHERE group_id = ?
        """, (group_id,)
        )






# def generate_invite_code(db_conn, length: int = 6):
#     characters = string.ascii_uppercase + string.digits
#     cursor = db_conn.cursor()
#     while True:
#         invite_code = "".join(secrets.choice(characters) for _ in range(length))
#         cursor.execute("""
#                 SELECT 1
#                 FROM groups
#                 WHERE invite_code = ?
#             """, (invite_code,)
#         )
#         if cursor.fetchone() is None:
#             return invite_code
