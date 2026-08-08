import { Router } from 'express';
import { prisma } from '../db';
import { logActivity } from '../services/systemLogger';
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
    const { nickname, totalAmount, items, rewardId, paymentMethod = "CASH", shiftId } = req.body;

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

    // Ambil pengaturan pajak dan parkir
    const taxSetting = await prisma.systemSettings.findUnique({ where: { key: 'TAX_PERCENTAGE' } });
    const parkingSetting = await prisma.systemSettings.findUnique({ where: { key: 'PARKING_FEE' } });
    const taxPercentage = taxSetting ? parseFloat(taxSetting.value) || 11 : 11;
    const configuredParkingFee = parkingSetting ? parseInt(parkingSetting.value) || 2000 : 2000;

    // Hitung alokasi pajak dan parkir (Opsi B: Harga final sudah termasuk)
    const parkingFee = totalAmount > configuredParkingFee ? configuredParkingFee : 0;
    const amountWithoutParking = totalAmount - parkingFee;
    const taxMultiplier = 1 + (taxPercentage / 100);
    const subTotal = Math.round(amountWithoutParking / taxMultiplier);
    const taxAmount = amountWithoutParking - subTotal;

    // Fetch HPP untuk items
    const menuIds = items ? items.map((item: any) => item.menuId) : [];
    const menus = await prisma.menu.findMany({
      where: { id: { in: menuIds } },
      select: { id: true, hpp: true }
    });
    const hppMap = new Map(menus.map(m => [m.id, m.hpp]));

    // Simpan Transaksi beserta Items
    const transaction = await prisma.transaction.create({
      data: {
        totalAmount,
        subTotal,
        taxAmount,
        parkingFee,
        pointsEarned,
        paymentMethod,
        customerId: customer.id,
        shiftId: shiftId ? parseInt(shiftId) : undefined,
        items: items && items.length > 0 ? {
          create: items.map((item: any) => ({
            menuId: item.menuId,
            quantity: item.quantity,
            price: item.price,
            hpp: hppMap.get(item.menuId) || 0,
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

    // Log Transaction
    const shiftInfo = shiftId ? await prisma.shift.findUnique({ where: { id: parseInt(shiftId) } }) : null;
    await logActivity('TRANSACTION', shiftInfo?.userId, `Total: Rp ${totalAmount.toLocaleString('id-ID')} via ${paymentMethod}`, 'Transaction', transaction.id);

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
    
    // Ambil pengaturan umum (sekali saja untuk semua transaksi dalam batch)
    const taxSetting = await prisma.systemSettings.findUnique({ where: { key: 'TAX_PERCENTAGE' } });
    const parkingSetting = await prisma.systemSettings.findUnique({ where: { key: 'PARKING_FEE' } });
    const expirationSetting = await prisma.systemSettings.findUnique({ where: { key: 'POINT_EXPIRATION_DAYS' } });
    
    const taxPercentage = taxSetting ? parseFloat(taxSetting.value) || 11 : 11;
    const configuredParkingFee = parkingSetting ? parseInt(parkingSetting.value) || 2000 : 2000;
    const expirationDays = expirationSetting ? parseInt(expirationSetting.value) || 90 : 90;
    const taxMultiplier = 1 + (taxPercentage / 100);

    for (const tx of transactions) {
      const { nickname, totalAmount, items, rewardId, paymentMethod = "CASH", shiftId, createdAt } = tx;

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

      // Hitung alokasi pajak dan parkir
      const parkingFee = totalAmount > configuredParkingFee ? configuredParkingFee : 0;
      const amountWithoutParking = totalAmount - parkingFee;
      const subTotal = Math.round(amountWithoutParking / taxMultiplier);
      const taxAmount = amountWithoutParking - subTotal;

      // Fetch HPP untuk items
      const menuIds = items ? items.map((item: any) => item.menuId) : [];
      const menus = await prisma.menu.findMany({
        where: { id: { in: menuIds } },
        select: { id: true, hpp: true }
      });
      const hppMap = new Map(menus.map(m => [m.id, m.hpp]));

      const transaction = await prisma.transaction.create({
        data: {
          totalAmount,
          subTotal,
          taxAmount,
          parkingFee,
          pointsEarned,
          paymentMethod,
          customerId: customer.id,
          shiftId: shiftId ? parseInt(shiftId) : undefined,
          createdAt: createdAt ? new Date(createdAt) : undefined,
          items: items && items.length > 0 ? {
            create: items.map((item: any) => ({
              menuId: item.menuId,
              quantity: item.quantity,
              price: item.price,
              hpp: hppMap.get(item.menuId) || 0,
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

router.post('/history/:id/void', async (req, res) => {
  try {
    const { id } = req.params;
    const { voidReason, voidedBy } = req.body;

    const transaction = await prisma.transaction.findUnique({
      where: { id: Number(id) }
    });

    if (!transaction) return res.status(404).json({ error: 'Transaction not found' });
    if (transaction.status === 'VOID') return res.status(400).json({ error: 'Transaction already voided' });

    // Update status
    const updatedTx = await prisma.transaction.update({
      where: { id: Number(id) },
      data: {
        status: 'VOID',
        voidReason,
        voidedAt: new Date(),
        voidedBy: voidedBy ? Number(voidedBy) : undefined
      }
    });

    // Revert points earned
    if (transaction.pointsEarned > 0 && transaction.customerId) {
      const customer = await prisma.customer.findUnique({ where: { id: transaction.customerId } });
      if (customer) {
        await prisma.customer.update({
          where: { id: customer.id },
          data: {
            points: Math.max(0, customer.points - transaction.pointsEarned),
            xp: Math.max(0, customer.xp - transaction.pointsEarned)
          }
        });
      }
    }

    // Log the action
    await logActivity('VOID_TRANSACTION', voidedBy ? Number(voidedBy) : undefined, voidReason, 'Transaction', transaction.id);

    res.json(updatedTx);
  } catch (error) {
    console.error('Error voiding transaction:', error);
    res.status(500).json({ error: 'Failed to void transaction' });
  }
});

export default router;
