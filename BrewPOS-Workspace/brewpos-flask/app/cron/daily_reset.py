from app.extensions import db
from app.models.quest import Quest
from app.models.customer import CustomerQuest

def reset_daily_quests(app):
    with app.app_context():
        try:
            print("[CRON] Menjalankan reset misi harian...")
            daily_quests = Quest.query.filter_by(active=True, isDaily=True).all()
            daily_quest_ids = [q.id for q in daily_quests]

            if daily_quest_ids:
                CustomerQuest.query.filter(CustomerQuest.questId.in_(daily_quest_ids)).update(
                    {CustomerQuest.progress: 0, CustomerQuest.isCompleted: False},
                    synchronize_session=False
                )
                db.session.commit()
                print(f"[CRON] Reset {len(daily_quest_ids)} misi harian berhasil.")
        except Exception as e:
            db.session.rollback()
            print(f"[CRON] Gagal melakukan reset misi harian: {e}")
