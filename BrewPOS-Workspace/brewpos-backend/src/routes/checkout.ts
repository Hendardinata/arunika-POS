import { Router } from 'express';
import { prisma } from '../db';
import { processGamificationAsync } from '../services/gamificationService';

const router = Router();

router.get('/history', async (req, res) => {
  try {
    const history = await prisma.transaction.findMany({
      orderBy: { createdAt: 'desc' },
      include: {
        customer: true,
        items: {
          include: {
            menu: true,
          }
        },
      },
      take: 50,
    });
    res.json(history);
  } catch (error) {
    console.error('Error fetching history:', error);
    res.status(500).json({ error: 'Failed to fetch history' });
  }
});

router.post('/', async (req, res) => {
  try {
    const { nickname, totalAmount, items, rewardId, paymentMethod = "CASH" } = req.body;

    if (!nickname) {
      return res.status(400).json({ error: 'Nickname is required' });
    }

    // 1 Poin & 1 XP untuk setiap Rp 1.000
    let pointsEarned = Math.floor(totalAmount / 1000);
    let isLuckyDrop = false;
    let bonusPoints = 0;

    // 20% Chance for Surprise Drop (Gamification)
    if (Math.random() < 0.20) {
      isLuckyDrop = true;
      bonusPoints = 50; // Bonus poin
      pointsEarned += bonusPoints;
    }

    if (nickname === 'Guest') {
      pointsEarned = 0;
      isLuckyDrop = false;
      bonusPoints = 0;
    }

    // Cari atau Buat Pelanggan
    let customer = await prisma.customer.findUnique({
      where: { nickname },
    });

    let pointsToDeduct = 0;

    if (rewardId) {
      const reward = await prisma.reward.findUnique({ where: { id: parseInt(rewardId) } });
      if (!reward || !reward.active) {
        return res.status(400).json({ error: 'Reward not available or inactive' });
      }
      if (!customer || customer.points < reward.pointsRequired) {
        return res.status(400).json({ error: 'Insufficient points to redeem this reward' });
      }
      pointsToDeduct = reward.pointsRequired;
    }

    if (!customer) {
      customer = await prisma.customer.create({
        data: { nickname, points: 0, xp: 0, level: 1, streakCount: 0 },
      });
    }

    // Update Poin & XP (Kurangi dengan pointsToDeduct)
    const newPoints = customer.points + pointsEarned - pointsToDeduct;
    const newXp = customer.xp + pointsEarned;
    // Logika Level Up sederhana (tiap kelipatan 100 XP naik 1 level)
    const newLevel = Math.floor(newXp / 100) + 1;

    // Ambil setting kedaluwarsa poin
    const expirationSetting = await prisma.systemSettings.findUnique({ where: { key: 'POINT_EXPIRATION_DAYS' } });
    const expirationDays = expirationSetting ? parseInt(expirationSetting.value) || 90 : 90;
    const now = new Date();
    const expiryDate = new Date(now);
    expiryDate.setDate(now.getDate() + expirationDays);

    let newStreak = customer.streakCount || 0;
    if (customer.lastVisitDate) {
      const lastVisit = new Date(customer.lastVisitDate);
      lastVisit.setHours(0, 0, 0, 0);
      const today = new Date(now);
      today.setHours(0, 0, 0, 0);
      const diffTime = Math.abs(today.getTime() - lastVisit.getTime());
      const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
      
      if (diffDays === 1) {
        newStreak += 1;
      } else if (diffDays > 1) {
        newStreak = 1;
      }
    } else {
      newStreak = 1; // First visit
    }

    customer = await prisma.customer.update({
      where: { id: customer.id },
      data: {
        points: newPoints,
        xp: newXp,
        level: newLevel,
        lastVisitDate: now,
        pointsExpiryDate: expiryDate,
        streakCount: newStreak,
      },
    });

    // Simpan Transaksi beserta Items
    const transaction = await prisma.transaction.create({
      data: {
        totalAmount,
        pointsEarned,
        paymentMethod,
        customerId: customer.id,
        items: items && items.length > 0 ? {
          create: items.map((item: any) => ({
            menuId: item.menuId,
            quantity: item.quantity,
            price: item.price,
          }))
        } : undefined
      },
      include: {
        items: true
      }
    });

    // Panggil Gamifikasi secara Asynchronous
    // Sengaja tidak di-await agar tidak memblokir respon kasir
    if (nickname !== 'Guest') {
      processGamificationAsync(customer.id, transaction.id);
    }

    res.status(201).json({
      message: 'Checkout successful',
      customer,
      transaction,
      luckyDrop: isLuckyDrop ? { bonusPoints } : null,
    });
  } catch (error) {
    console.error('Error during checkout:', error);
    res.status(500).json({ error: 'Failed to process checkout', details: error instanceof Error ? error.message : String(error) });
  }
});

router.post('/sync', async (req, res) => {
  try {
    const { transactions } = req.body;
    if (!transactions || !Array.isArray(transactions)) {
      return res.status(400).json({ error: 'Invalid transactions data' });
    }

    const results = [];
    for (const tx of transactions) {
      const { nickname, totalAmount, items, rewardId, paymentMethod = "CASH", createdAt } = tx;

      if (!nickname) continue;

      const pointsEarned = Math.floor(totalAmount / 1000);

      let customer = await prisma.customer.findUnique({
        where: { nickname },
      });

      let pointsToDeduct = 0;
      if (rewardId) {
        const reward = await prisma.reward.findUnique({ where: { id: parseInt(rewardId) } });
        if (reward && reward.active && customer && customer.points >= reward.pointsRequired) {
          pointsToDeduct = reward.pointsRequired;
        }
      }

      if (!customer) {
        customer = await prisma.customer.create({
          data: { nickname, points: 0, xp: 0, level: 1, streakCount: 0 },
        });
      }

      const newPoints = customer.points + pointsEarned - pointsToDeduct;
      const newXp = customer.xp + pointsEarned;
      const newLevel = Math.floor(newXp / 100) + 1;

      const txDate = createdAt ? new Date(createdAt) : new Date();
      const expirationSetting = await prisma.systemSettings.findUnique({ where: { key: 'POINT_EXPIRATION_DAYS' } });
      const expirationDays = expirationSetting ? parseInt(expirationSetting.value) || 90 : 90;
      const expiryDate = new Date(txDate);
      expiryDate.setDate(txDate.getDate() + expirationDays);

      let newStreak = customer.streakCount || 0;
      if (customer.lastVisitDate) {
        const lastVisit = new Date(customer.lastVisitDate);
        lastVisit.setHours(0, 0, 0, 0);
        const today = new Date(txDate);
        today.setHours(0, 0, 0, 0);
        const diffTime = Math.abs(today.getTime() - lastVisit.getTime());
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        if (diffDays === 1) {
          newStreak += 1;
        } else if (diffDays > 1) {
          newStreak = 1;
        }
      } else {
        newStreak = 1;
      }

      customer = await prisma.customer.update({
        where: { id: customer.id },
        data: { 
          points: newPoints, 
          xp: newXp, 
          level: newLevel,
          lastVisitDate: txDate,
          pointsExpiryDate: expiryDate,
          streakCount: newStreak
        },
      });

      const transaction = await prisma.transaction.create({
        data: {
          totalAmount,
          pointsEarned,
          paymentMethod,
          customerId: customer.id,
          createdAt: createdAt ? new Date(createdAt) : undefined,
          items: items && items.length > 0 ? {
            create: items.map((item: any) => ({
              menuId: item.menuId,
              quantity: item.quantity,
              price: item.price,
            }))
          } : undefined
        },
        include: { items: true }
      });

      processGamificationAsync(customer.id, transaction.id);
      results.push(transaction);
    }

    res.status(201).json({ message: 'Sync successful', syncedCount: results.length });
  } catch (error) {
    console.error('Error during checkout sync:', error);
    res.status(500).json({ error: 'Failed to process checkout sync' });
  }
});

export default router;
