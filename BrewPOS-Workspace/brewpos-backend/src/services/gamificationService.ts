import { prisma } from '../db';

/**
 * Memproses Gamifikasi (Quest & Badges) secara asynchronous.
 * Dipanggil setelah proses checkout selesai agar tidak memblokir response ke kasir.
 */
export async function processGamificationAsync(customerId: number, transactionId: number) {
  try {
    const transaction = await prisma.transaction.findUnique({
      where: { id: transactionId },
      include: { items: true },
    });

    if (!transaction) return;

    // --- 1. EVALUASI QUESTS ---
    const quests = await prisma.quest.findMany({ where: { active: true } });
    
    for (const quest of quests) {
      let customerQuest = await prisma.customerQuest.findUnique({
        where: { customerId_questId: { customerId, questId: quest.id } }
      });

      if (!customerQuest) {
        customerQuest = await prisma.customerQuest.create({
          data: { customerId, questId: quest.id }
        });
      }

      if (!customerQuest.isCompleted) {
        let addedProgress = 0;

        if (quest.type === 'TOTAL_TRANSACTIONS') {
          addedProgress = 1;
        } else if (quest.type === 'TOTAL_SPEND') {
          addedProgress = transaction.totalAmount;
        } else if (quest.type === 'BUY_ITEM' && quest.targetEntityId) {
          const matchingItems = transaction.items.filter((item: any) => item.menuId === quest.targetEntityId);
          addedProgress = matchingItems.reduce((acc: number, curr: any) => acc + curr.quantity, 0);
        }

        if (addedProgress > 0) {
          const newProgress = customerQuest.progress + addedProgress;
          const isCompleted = newProgress >= quest.targetValue;

          await prisma.customerQuest.update({
            where: { id: customerQuest.id },
            data: { progress: newProgress, isCompleted }
          });

          if (isCompleted) {
            // Berikan reward karena quest selesai
            await prisma.customer.update({
              where: { id: customerId },
              data: {
                points: { increment: quest.rewardPoints },
                xp: { increment: quest.rewardXp }
              }
            });
            console.log(`[Gamification] Customer ${customerId} completed quest: ${quest.name}`);
          }
        }
      }
    }

    // --- 2. EVALUASI BADGES ---
    const badges = await prisma.badge.findMany();
    const count = await prisma.transaction.count({ where: { customerId } });

    for (const badge of badges) {
      const hasBadge = await prisma.customerBadge.findUnique({
        where: { customerId_badgeId: { customerId, badgeId: badge.id } }
      });
      
      if (!hasBadge) {
        if (badge.requiredTransactions > 0 && count >= badge.requiredTransactions) {
          await prisma.customerBadge.create({
            data: { customerId, badgeId: badge.id }
          });
          console.log(`[Gamification] Customer ${customerId} unlocked badge: ${badge.name}`);
        }
      }
    }

  } catch (error) {
    console.error("[Gamification] Error processing gamification asynchronously:", error);
  }
}
