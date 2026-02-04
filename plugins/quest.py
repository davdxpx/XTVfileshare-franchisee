import random
from db import db
from config import Config
from log import get_logger

logger = get_logger(__name__)

class QuestEngine:
    @staticmethod
    async def generate_quest(user_id, bundle, client):
        # 1. Calculate Goal
        file_count = len(bundle["file_ids"])
        # Goal: 6 + (files // 3), clamped 6-12
        # Example: 5 files -> 6 + 1 = 7.
        # Example: 20 files -> 6 + 6 = 12.
        goal_points = min(max(6, 6 + (file_count // 3)), 12)

        current_points = 0
        steps = []
        counts = {"task": 0, "sub": 0, "share": 0}

        # 2. Force Share (Priority: Low? User said order: Task -> Sub -> Share)
        # But we allocate slots now.
        share_enabled = await db.get_config("force_share_enabled", False)
        if share_enabled and current_points < goal_points:
            # Add Share Step
            # Value: 2 points
            steps.append({"type": "share", "points": 2})
            counts["share"] += 1
            current_points += 2

        # 3. Force Subs
        fs_enabled = await db.get_config("force_sub_enabled", False)
        if fs_enabled and current_points < goal_points:
            # Get missing channels
            all_fs = await db.get_force_sub_channels()
            missing = []

            # Check membership
            for ch in all_fs:
                try:
                    # We need to check if user is ALREADY in it.
                    # If already in, we DON'T add it as a quest step (because it's already done).
                    # Logic: "pool aussucht welchen kanälen der nutzer erstmal halt noch nicht folgt"
                    member = await client.get_chat_member(ch["chat_id"], user_id)
                    if member.status in ["left", "kicked", "banned"]:
                        missing.append(ch)
                except Exception:
                    # Can't check? Assume missing/add to pool so they get the link
                    missing.append(ch)

            # Select channels to fill points
            # 1 Sub = 2 points
            # Max Subs? Let's say up to 3 subs (6 points) or until goal filled.
            random.shuffle(missing)

            for ch in missing:
                if current_points >= goal_points: break
                steps.append({
                    "type": "sub",
                    "points": 2,
                    "channel": {"id": ch["chat_id"], "title": ch.get("title"), "link": ch.get("invite_link")}
                })
                counts["sub"] += 1
                current_points += 2

        # 4. Tasks (Fill remainder)
        remaining = goal_points - current_points
        if remaining > 0:
            # 1 Task = 1 Point
            task_count = remaining
            # Fetch tasks
            tasks_db = await db.get_random_tasks(task_count)
            # If not enough tasks in DB, loop them?
            if len(tasks_db) < task_count and tasks_db:
                while len(tasks_db) < task_count:
                    tasks_db.append(random.choice(tasks_db))
            elif not tasks_db:
                # No tasks? Fallback dummy
                tasks_db = [{"question": "1+1?", "answer": "2", "type": "text"}] * task_count

            for t in tasks_db:
                steps.append({"type": "task", "points": 1, "data": t})
                counts["task"] += 1
                current_points += 1

        # 5. Sort Order: Task -> Sub -> Share
        def sort_key(s):
            if s["type"] == "task": return 0
            if s["type"] == "sub": return 1
            if s["type"] == "share": return 2
            return 3

        steps.sort(key=sort_key)

        return {
            "steps": steps,
            "current_index": 0,
            "counts": counts,
            "total_steps": len(steps)
        }
