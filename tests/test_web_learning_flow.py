from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import zhidao_web as web


class LearningWebFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        web.DB_PATH = root / "test.db"
        web.UPLOAD_ROOT = root / "uploads"
        web.UPLOAD_ROOT.mkdir(parents=True)
        web.LOGIN_FAILURES.clear()
        web.init_db()
        web.create_or_update_user("architect", "Марк Альбертович", "teacher", "teacher-pass")
        web.create_or_update_user("operator", "Юный оператор", "student", "2468")
        self.client = TestClient(web.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp_dir.cleanup()

    def login(self, username: str, secret: str) -> str:
        response = self.client.post("/api/auth/login", json={"username": username, "secret": secret})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def answer_auto_tasks(self, mission_id: str, mission: dict, csrf: str) -> None:
        for task in mission["content"]["tasks"]:
            if task["type"] not in {"choice", "order"}:
                continue
            response = self.client.post(
                f"/api/student/missions/{mission_id}/answer",
                headers={"X-CSRF-Token": csrf},
                json={"step_id": task["id"], "answer": task["correct"]},
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["is_correct"])

    def test_two_lesson_reward_and_unlock_flow(self):
        student_csrf = self.login("operator", "2468")
        dashboard = self.client.get("/api/student/dashboard").json()
        self.assertEqual(dashboard["missions"][0]["status"], "assigned")
        self.assertEqual(dashboard["missions"][1]["status"], "locked")
        self.assertEqual(dashboard["missions"][0]["focus_words"][0]["pinyin"], "Nǐ hǎo")

        mission_id = "mission-first-contact"
        mission_data = self.client.get(f"/api/student/missions/{mission_id}").json()
        self.answer_auto_tasks(mission_id, mission_data["mission"], student_csrf)
        draft = self.client.post(
            f"/api/student/missions/{mission_id}/answer",
            headers={"X-CSRF-Token": student_csrf},
            json={"step_id": "m1-write", "answer": "我叫Лёша"},
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        reopened = self.client.get(f"/api/student/missions/{mission_id}").json()
        self.assertEqual(reopened["attempts"]["m1-write"]["answer"], "我叫Лёша")
        submit = self.client.post(
            f"/api/student/missions/{mission_id}/submit",
            headers={"X-CSRF-Token": student_csrf},
            json={"written_answer": "我叫Лёша"},
        )
        self.assertEqual(submit.status_code, 200, submit.text)
        self.assertEqual(submit.json()["auto_score"], 100)

        self.client.cookies.clear()
        teacher_csrf = self.login("architect", "teacher-pass")
        overview = self.client.get("/api/teacher/overview").json()
        first = next(item for item in overview["submissions"] if item["mission_id"] == mission_id)
        review = self.client.post(
            f"/api/teacher/assignments/{first['assignment_id']}/review",
            headers={"X-CSRF-Token": teacher_csrf},
            json={"decision": "approve", "feedback": "Отличный первый сигнал!", "unlock_next": True},
        )
        self.assertEqual(review.status_code, 200, review.text)
        self.assertEqual(review.json()["xp"], 80)
        self.assertEqual(review.json()["stars"], 15)

        duplicate = self.client.post(
            f"/api/teacher/assignments/{first['assignment_id']}/review",
            headers={"X-CSRF-Token": teacher_csrf},
            json={"decision": "approve", "feedback": "Повтор", "unlock_next": True},
        )
        self.assertTrue(duplicate.json()["already_awarded"])

        self.client.cookies.clear()
        student_csrf = self.login("operator", "2468")
        dashboard = self.client.get("/api/student/dashboard").json()
        self.assertEqual(dashboard["profile"]["xp"], 80)
        self.assertEqual(dashboard["user"]["stars"], 15)
        self.assertEqual(dashboard["profile"]["lesson_streak"], 1)
        self.assertEqual(dashboard["missions"][1]["status"], "assigned")

        mission_id = "mission-handshake"
        mission_data = self.client.get(f"/api/student/missions/{mission_id}").json()
        self.answer_auto_tasks(mission_id, mission_data["mission"], student_csrf)
        voice = self.client.post(
            f"/api/student/missions/{mission_id}/voice",
            headers={
                "X-CSRF-Token": student_csrf,
                "X-Audio-Mime": "audio/webm",
                "Content-Type": "audio/webm",
            },
            content=b"fake-webm-audio-for-test",
        )
        self.assertEqual(voice.status_code, 200, voice.text)
        submit = self.client.post(
            f"/api/student/missions/{mission_id}/submit",
            headers={"X-CSRF-Token": student_csrf},
            json={"written_answer": ""},
        )
        self.assertEqual(submit.status_code, 200, submit.text)

        self.client.cookies.clear()
        teacher_csrf = self.login("architect", "teacher-pass")
        overview = self.client.get("/api/teacher/overview").json()
        second = next(item for item in overview["submissions"] if item["mission_id"] == mission_id)
        audio = self.client.get(f"/api/teacher/audio/{second['voice_filename']}")
        self.assertEqual(audio.status_code, 200)
        review = self.client.post(
            f"/api/teacher/assignments/{second['assignment_id']}/review",
            headers={"X-CSRF-Token": teacher_csrf},
            json={"decision": "approve", "feedback": "Рукопожатие завершено!", "unlock_next": True},
        )
        self.assertEqual(review.status_code, 200, review.text)

        self.client.cookies.clear()
        self.login("operator", "2468")
        dashboard = self.client.get("/api/student/dashboard").json()
        self.assertEqual(dashboard["profile"]["xp"], 200)
        self.assertEqual(dashboard["profile"]["level"], 2)
        self.assertEqual(dashboard["profile"]["lesson_streak"], 2)
        self.assertEqual(dashboard["user"]["stars"], 35)
        self.assertEqual(len(dashboard["rewards"]), 2)

    def test_student_cannot_open_teacher_console_api(self):
        self.login("operator", "2468")
        response = self.client.get("/api/teacher/overview")
        self.assertEqual(response.status_code, 403)

    def test_newest_assigned_chapter_becomes_active(self):
        teacher_csrf = self.login("architect", "teacher-pass")
        overview = self.client.get("/api/teacher/overview").json()
        student_id = overview["students"][0]["id"]
        mission = next(item for item in overview["missions"] if item["id"] == "mission-scale-protocol")
        self.assertEqual(mission["content"]["words"][0]["pinyin"], "xiǎo")

        assigned = self.client.post(
            "/api/teacher/missions/mission-scale-protocol/assign",
            headers={"X-CSRF-Token": teacher_csrf},
            json={"student_id": student_id},
        )
        self.assertEqual(assigned.status_code, 200, assigned.text)

        self.client.cookies.clear()
        self.login("operator", "2468")
        dashboard = self.client.get("/api/student/dashboard").json()
        self.assertEqual(dashboard["chapter"]["id"], "chapter-form-scan")
        self.assertEqual(dashboard["missions"][0]["id"], "mission-scale-protocol")
        self.assertEqual(dashboard["missions"][0]["status"], "assigned")
        self.assertEqual(dashboard["missions"][1]["status"], "locked")
        self.assertEqual(dashboard["missions"][0]["glyph"], "尺")

    def test_csrf_is_required_for_mutations(self):
        self.login("operator", "2468")
        response = self.client.post("/api/student/missions/mission-first-contact/start")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
