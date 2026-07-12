import cron from 'node-cron';
import { prisma } from './db';

// Jalankan setiap jam 00:00
cron.schedule('0 0 * * *', async () => {
  console.log('[CRON] Menjalankan reset misi harian...');
  try {
    const dailyQuests = await prisma.quest.findMany({
      where: { active: true, isDaily: true },
    });

    for (const quest of dailyQuests) {
      // Reset semua progress untuk quest ini menjadi 0
      await prisma.customerQuest.updateMany({
        where: { questId: quest.id },
        data: {
          progress: 0,
          isCompleted: false,
        },
      });
      console.log(`[CRON] Quest harian '${quest.name}' berhasil di-reset.`);
    }
  } catch (error) {
    console.error('[CRON] Gagal melakukan reset misi harian:', error);
  }
});
