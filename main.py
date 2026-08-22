import database

from fastapi import FastAPI
from routers import participants, groups, members, availability, events, moderation, friends

app = FastAPI(title="Group Coordination API")

app.include_router(participants.router)
app.include_router(groups.router)
app.include_router(members.router)
app.include_router(availability.router)
app.include_router(events.router)
app.include_router(moderation.router)
# app.include_router(friends.router)

database.init_db()

# ==========================================
# HOME
# ==========================================

@app.get("/")
def home():
    return {
        "message": "Group Coordination API",
        "description": "An API for coordinating groups, events, and availability.",
        "docs": "/docs"
    }
